"""Four demo-reliable agents: ScenarioComposer, LogGenerator, ValidatorRepair, TSTRCopilot."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from synthcompliance_agents.feedback import update_feedback_state
from synthcompliance_generators.corpus import generate_corpus
from synthcompliance_generators.io_atomic import write_dataset_bundle, write_json
from synthcompliance_generators.provider import get_provider, get_retrain_provider
from synthcompliance_generators.scenario_engine import (
    EVAL_TARGETS,
    TRAIN_TARGETS,
    ScenarioEngine,
)
from synthcompliance_taxonomy.controls import TAXONOMY
from synthcompliance_taxonomy.roster import ASSET_LIST, USER_ROSTER
from synthcompliance_validators.report import build_validation_report
from synthcompliance_validators.retrain_model import load_latest_retrain_model_snapshot
from synthcompliance_validators.tstr import load_latest_retrain_snapshot, retrain_persisted_model, run_tstr

EventCb = Callable[[dict[str, Any]], None]


def _emit(cb: EventCb | None, event: dict[str, Any]) -> None:
    if cb:
        cb(event)


def _emit_stage(
    cb: EventCb | None,
    pipeline_stage: str,
    status: str,
    duration_ms: int = 0,
) -> None:
    """Structured stage-transition event, parallel to the free-text `_emit` messages above —
    lets the frontend drive a live version of the Pipeline Flow stepper (normally sourced from
    the on-disk validation_report.json, which only exists once a run finishes) without
    colliding with subscribeJobEvents()'s `stage === 'complete'/'failed'` completion check."""
    _emit(
        cb,
        {
            "stage": "stage_update",
            "pipeline_stage": pipeline_stage,
            "status": status,
            "duration_ms": duration_ms,
        },
    )


def _bool_env(name: str, default: bool = False) -> bool:
    """Matches provider.py's helper of the same name — no central config module in this repo,
    env vars are read ad hoc at point of use."""
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _merge_transformer_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Fold offline cluster-trained transformer metrics into tstr_metrics.

    The transformer scorers (DistilBERT, DeBERTa) are trained out-of-band on the
    H100 cluster via `scripts/train_transformers.py` against a leakage-safe
    pack split (SOX train / GDPR eval). That job writes
    `transformer_metrics.json`; the live API never imports torch — it just reads
    the JSON and merges it here so the dashboard can show a 4-way recall
    comparison (rule / LR / DistilBERT / DeBERTa). Missing file => no-op.
    """
    ckpt_dir = os.getenv("SYNTH_TRANSFORMER_DIR", "")
    if not ckpt_dir:
        ckpt_dir = str(Path(os.getenv("SYNTH_DATA_DIR", "public/data")) / "checkpoints")
    path = Path(ckpt_dir) / "transformer_metrics.json"
    if not path.exists():
        return metrics
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return metrics
    models = bundle.get("models") or {}
    if not models:
        return metrics
    out = dict(metrics)
    out["transformer_models"] = list(models.values())
    out["transformer_best_model"] = bundle.get("best_model")
    # Flatten the best model's fields onto the top-level dict for the UI.
    best = models.get(out["transformer_best_model"] or "") or {}
    for k, v in best.items():
        if k not in out:
            out[k] = v
    return out


class ScenarioComposerAgent:
    """Reads coverage gaps and produces a generation plan."""

    def run(
        self,
        *,
        packs: list[str],
        control_classes: list[str] | None,
        scenario_mix: dict[str, float] | None,
        n_logs: int,
        industry: str,
        prior_coverage: dict[str, int] | None = None,
        on_event: EventCb | None = None,
    ) -> dict[str, Any]:
        _emit(on_event, {"stage": "composing", "message": "Script: analyzing class-balance gaps"})
        mix = scenario_mix or dict(TRAIN_TARGETS)
        if prior_coverage:
            total = sum(prior_coverage.values()) or 1
            # Close gaps vs train targets
            adjusted = dict(mix)
            for k, target in TRAIN_TARGETS.items():
                actual = prior_coverage.get(k, 0) / total
                if actual < target - 0.03:
                    adjusted[k] = mix.get(k, target) + (target - actual)
            s = sum(adjusted.values()) or 1
            mix = {k: v / s for k, v in adjusted.items()}

        engine = ScenarioEngine(
            packs=packs,
            control_classes=control_classes,
            scenario_mix=mix,
            n_logs=n_logs,
            industry=industry,
            seed=f"job-{uuid.uuid4().hex[:8]}",
            mode="train",
        )
        plan = engine.compose_plan()
        plan["engine"] = engine
        _emit(
            on_event,
            {
                "stage": "composing",
                "message": f"Script: plan ready: {plan['scenario_counts']}",
                "plan": {k: v for k, v in plan.items() if k != "engine"},
            },
        )
        return plan


POLISH_BATCH_SIZE = 12
# Smaller than POLISH_BATCH_SIZE and given a bigger max_tokens budget below: this call's
# response can have up to 5 fields per item (vs. 1 for the explanation write), plus each item
# carries its own candidate shortlists, and the configured model spends a chunk of its token
# budget on internal reasoning before the final JSON — a larger batch here reliably truncates
# mid-response (verified: 25 items @ 3 fields/2048 tokens hit finish_reason="length").
SELECTION_BATCH_SIZE = 8
SELECTION_MAX_TOKENS = 6000
SHORTLIST_SIZE = 4
VALID_ACTIONS = ("CREATE", "UPDATE", "DELETE", "APPROVE", "EXPORT", "READ")
VALID_OUTCOMES = ("success", "denied")
VALID_SENSITIVITIES = ("low", "medium", "high", "critical")
# late_dsar / breach_notification_late force a specific action AND resource, tied to the
# day/hour count encoded in `resource` (see corpus.py) — leave both alone regardless of LLM
# availability.
ACTION_FORCED_TYPES = ("late_dsar", "breach_notification_late")


class LogGeneratorAgent:
    """Generates audit_logs → violations/QAs from the plan. `log_id`/`timestamp` (and, for
    violations, `violation_id`/`control_id`/`severity`/`violation_type`) stay deterministic —
    referential keys and taxonomy ground-truth other rows depend on. Everything else that reads
    as *content* — `user_id`/`role`, `resource`/`system`, `action`, `outcome`, `sensitivity`, and
    violation `explanation` — is written by the LLM when a provider is configured, batched for
    speed with a deterministic fallback per batch on failure. `user_id`/`resource` are picked
    from a per-log candidate shortlist (never invented) so roster/asset referential integrity
    always holds; `role`/`system` are then derived deterministically from whichever candidate
    was picked, never asked of the LLM directly. Rows where a field is forced by business logic
    (e.g. every violation's outcome is "success") are never handed to the LLM for that field."""

    def run(self, plan: dict[str, Any], on_event: EventCb | None = None) -> dict[str, Any]:
        engine: ScenarioEngine = plan["engine"]
        _emit(on_event, {"stage": "generating", "message": "Script: building ID pool", "count": 0})
        corpus = generate_corpus(plan, engine)
        n = len(corpus["audit_logs"])
        # generate_corpus() is deterministic and already complete at this point — this is a
        # single real "done" event, not a simulated live tick (previously this faked a
        # progress-bar animation over already-finished data, which read as if it were doing
        # LLM work here; it wasn't — the real LLM steps are the two blocks below).
        _emit(
            on_event,
            {
                "stage": "generating",
                "message": f"Script: assigned {n} log IDs (deterministic scaffold — IDs, timestamps, taxonomy keys)",
                "count": n,
                "total": n,
            },
        )

        provider = get_provider()
        _emit(
            on_event,
            {
                "stage": "generating",
                "message": f"LLM ({provider.model}): provider ready" if provider.available else "Script: no LLM provider configured — remaining fields use deterministic fallback",
                "model": provider.model if provider.available else None,
                "provider_available": provider.available,
            },
        )
        violations = corpus["violations"]
        log_by_id = {row["log_id"]: row for row in corpus["audit_logs"]}

        vtype_by_log = {v["log_id"]: v["violation_type"] for v in violations}
        labels = corpus["scenario_labels"]
        # Business-logic forced subsets — these encode what the scenario *is*, not a
        # stylistic choice, so the LLM never touches them regardless of availability:
        #  - action/resource: late_dsar/breach_notification_late must keep their forced
        #    action ("EXPORT") and synthetic resource path (day/hour count encoded in it)
        #  - outcome: every violation log must stay "success" — that's what makes it one
        #  - sensitivity: violations use taxonomy severity; false_positive stays "high"
        action_and_resource_forced = {
            v["log_id"] for v in violations if v["violation_type"] in ACTION_FORCED_TYPES
        }
        outcome_forced = {v["log_id"] for v in violations}
        sensitivity_forced = {
            lid for lid, label in labels.items() if label in ("violation", "false_positive")
        }

        def needed_fields(log_id: str) -> list[str]:
            fields = ["user_id"]
            if log_id not in action_and_resource_forced:
                fields += ["action", "resource"]
            if log_id not in outcome_forced:
                fields.append("outcome")
            if log_id not in sensitivity_forced:
                fields.append("sensitivity")
            return fields

        # Eligible field count is a property of dataset composition, not of whether a provider
        # is configured — always compute it so "Fields LLM-generated" is honest about "0
        # written" (no provider) vs. "nothing to write" (dataset genuinely has none eligible).
        llm_fields_target = sum(len(needed_fields(row["log_id"])) for row in corpus["audit_logs"])
        llm_fields_target += len(violations)  # one explanation each
        llm_fields_actual = 0

        if provider.available and corpus["audit_logs"]:
            eligible = corpus["audit_logs"]
            total = len(eligible)
            counts = {"user_id": 0, "resource": 0, "action": 0, "outcome": 0, "sensitivity": 0}
            for start in range(0, total, SELECTION_BATCH_SIZE):
                batch = eligible[start : start + SELECTION_BATCH_SIZE]
                done = min(start + SELECTION_BATCH_SIZE, total)
                _emit(
                    on_event,
                    {
                        "stage": "generating",
                        "message": f"LLM ({provider.model}): writing log content {done}/{total}",
                        "count": done,
                        "total": total,
                    },
                )
                # Each log gets its own small candidate shortlist for user_id/resource so the
                # LLM is choosing, not inventing — this preserves roster/asset referential
                # integrity no matter what it picks. role/system are never asked of the LLM;
                # they're derived below from whichever candidate it picked.
                row_candidates: dict[str, dict[str, list[dict[str, str]]]] = {}
                items_payload = []
                for row in batch:
                    lid = row["log_id"]
                    user_cands = engine.rng.sample(USER_ROSTER, min(SHORTLIST_SIZE, len(USER_ROSTER)))
                    asset_cands = engine.rng.sample(ASSET_LIST, min(SHORTLIST_SIZE, len(ASSET_LIST)))
                    row_candidates[lid] = {"users": user_cands, "assets": asset_cands}
                    items_payload.append(
                        {
                            "log_id": lid,
                            "context": vtype_by_log.get(lid, "routine access"),
                            "fields_needed": needed_fields(lid),
                            "user_candidates": [u["user_id"] for u in user_cands],
                            "resource_candidates": [a["resource"] for a in asset_cands],
                        }
                    )
                # LLM picks only from the fixed vocabularies/candidates below, and only for the
                # fields listed in each item's fields_needed. Re-validated again on apply
                # (belt-and-suspenders): any batch that fails, returns malformed JSON, picks
                # outside the vocabulary/candidates, or answers an unrequested field is ignored
                # for that field, keeping the log's deterministic scaffold value as a fallback.
                chosen_fields = provider.complete_json(
                    system=(
                        "For each audit-log entry, choose values ONLY for the fields listed in "
                        "its fields_needed. `user_id` must be exactly one of that item's "
                        "user_candidates. `resource` must be exactly one of that item's "
                        "resource_candidates. Valid action values: "
                        f"{', '.join(VALID_ACTIONS)}. Valid outcome values: "
                        f"{', '.join(VALID_OUTCOMES)}. Valid sensitivity values: "
                        f"{', '.join(VALID_SENSITIVITIES)}. Never invent a value outside these "
                        "lists/candidates, and never include a field not in fields_needed. "
                        "Return strict JSON {items:[{log_id, user_id?, resource?, action?, "
                        "outcome?, sensitivity?}]} with exactly one item per input log_id, no "
                        "extra commentary."
                    ),
                    user=str(items_payload),
                    max_tokens=SELECTION_MAX_TOKENS,
                )
                if not isinstance(chosen_fields, dict) or "items" not in chosen_fields:
                    continue
                by_id = {row["log_id"]: row for row in batch}
                for item in chosen_fields["items"]:
                    lid = item.get("log_id")
                    if lid not in by_id:
                        continue
                    row = by_id[lid]
                    cands = row_candidates[lid]

                    picked_user = item.get("user_id")
                    # Resolve against this row's own candidate objects, not a global id->object
                    # map — ASSET_LIST has 200 entries but only 168 unique `resource` strings (8
                    # duplicated across different assets with different `system`s), so a global
                    # resource->asset map can silently resolve to a *different* asset than the
                    # one actually offered/picked.
                    user = next((u for u in cands["users"] if u["user_id"] == picked_user), None)
                    if user is not None:
                        row["user_id"] = user["user_id"]
                        row["role"] = user["role"]
                        counts["user_id"] += 1

                    if lid not in action_and_resource_forced:
                        picked_resource = item.get("resource")
                        asset = next((a for a in cands["assets"] if a["resource"] == picked_resource), None)
                        if asset is not None:
                            old_resource = row["resource"]
                            row["resource"] = asset["resource"]
                            row["system"] = asset["system"]
                            counts["resource"] += 1
                            # Keep the QA-pair question (built from the original scaffolded
                            # resource, before this pass ran) grounded in the new one.
                            vtype = vtype_by_log.get(lid)
                            if vtype:
                                old_q = f"Which logs show a {vtype.replace('_', ' ')} involving {old_resource}?"
                                new_q = f"Which logs show a {vtype.replace('_', ' ')} involving {asset['resource']}?"
                                for qa in corpus["qa_pairs"]:
                                    if qa.get("question") == old_q:
                                        qa["question"] = new_q

                        action = item.get("action")
                        if action in VALID_ACTIONS:
                            row["action"] = action
                            counts["action"] += 1

                    outcome = item.get("outcome")
                    if lid not in outcome_forced and outcome in VALID_OUTCOMES:
                        row["outcome"] = outcome
                        counts["outcome"] += 1

                    sensitivity = item.get("sensitivity")
                    if lid not in sensitivity_forced and sensitivity in VALID_SENSITIVITIES:
                        row["sensitivity"] = sensitivity
                        counts["sensitivity"] += 1
            _emit(
                on_event,
                {
                    "stage": "generating",
                    "message": (
                        f"LLM ({provider.model}): log content complete: {counts['user_id']} users, "
                        f"{counts['resource']} resources, {counts['action']} actions, "
                        f"{counts['outcome']} outcomes, {counts['sensitivity']} sensitivities "
                        f"({total} logs)"
                    ),
                },
            )
            llm_fields_actual += sum(counts.values())

        if provider.available and violations:
            total = len(violations)
            written = 0
            for start in range(0, total, POLISH_BATCH_SIZE):
                batch = violations[start : start + POLISH_BATCH_SIZE]
                done = min(start + POLISH_BATCH_SIZE, total)
                _emit(
                    on_event,
                    {
                        "stage": "generating",
                        "message": f"LLM ({provider.model}): writing violation explanations {done}/{total}",
                        "count": done,
                        "total": total,
                    },
                )
                # Written fresh from the *current* (possibly LLM-reassigned above) user_id/role/
                # resource on each violation's log, not polished from the deterministic seed
                # text — otherwise a reassigned user/resource would leave the explanation
                # describing someone/something else. control_id/violation_id/violation_type
                # stay ground-truth; never invented or changed. Any batch that fails or returns
                # malformed JSON just keeps its deterministic template explanation.
                written_fields = provider.complete_json(
                    system=(
                        "You write compliance-violation explanations that read like a real audit "
                        "note: one concise sentence each, strictly grounded in the given "
                        "user_id, role, and resource — never reference any other identifiers. "
                        "Keep control_id and violation_id exactly as given — never invent or "
                        "change them. Return strict JSON {items:[{violation_id, explanation}]} "
                        "with exactly one item per input violation_id, no extra commentary."
                    ),
                    user=str(
                        [
                            {
                                "violation_id": v["violation_id"],
                                "control_id": v["control_id"],
                                "violation_type": v["violation_type"],
                                "user_id": log_by_id[v["log_id"]]["user_id"],
                                "role": log_by_id[v["log_id"]]["role"],
                                "resource": log_by_id[v["log_id"]]["resource"],
                            }
                            for v in batch
                        ]
                    ),
                )
                if not isinstance(written_fields, dict) or "items" not in written_fields:
                    continue
                by_id = {v["violation_id"]: v for v in batch}
                for item in written_fields["items"]:
                    vid = item.get("violation_id")
                    new_explanation = item.get("explanation")
                    if vid not in by_id or not new_explanation:
                        continue
                    v = by_id[vid]
                    old_answer_prefix = f"{v['log_id']} — {v['explanation']}"
                    v["explanation"] = new_explanation
                    written += 1
                    # Keep any QA pair answer grounded in the same (now written) explanation.
                    for qa in corpus["qa_pairs"]:
                        if qa.get("answer") == old_answer_prefix:
                            qa["answer"] = f"{v['log_id']} — {new_explanation}"
            _emit(
                on_event,
                {
                    "stage": "generating",
                    "message": f"LLM ({provider.model}): explanations complete: {written}/{total} written",
                },
            )
            llm_fields_actual += written

        _emit(
            on_event,
            {
                "stage": "generating",
                "message": f"Script: complete: {n} logs, {len(corpus['violations'])} violations",
                "count": n,
                "total": n,
            },
        )
        corpus["llm_fields_target"] = llm_fields_target
        corpus["llm_fields_actual"] = llm_fields_actual
        return corpus


class ValidatorRepairAgent:
    """Run validators; repair failing rows up to 3 iterations."""

    MAX_ITERS = 3

    def run(
        self,
        corpus: dict[str, Any],
        *,
        run_id: str,
        targets: dict[str, int],
        llm_fields_actual: int = 0,
        scope_types: list[str] | None = None,
        on_event: EventCb | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        audit_logs = list(corpus["audit_logs"])
        violations = list(corpus["violations"])
        qa_pairs = list(corpus["qa_pairs"])
        labels = dict(corpus["scenario_labels"])
        repaired_ids: list[str] = []

        # Composer/Log Generator durations are filled in by PipelineOrchestrator after this
        # method returns (it's the one that actually times those calls) — these are overwritten
        # before anything reads them; 0 rather than a guessed number so it's obviously a
        # placeholder if ever inspected mid-run.
        stages = [
            {"stage": "Scenario Composer", "status": "completed", "duration_ms": 0},
            {"stage": "Log Generator", "status": "completed", "duration_ms": 0},
            {"stage": "Validator", "status": "running", "duration_ms": 0},
            {"stage": "Repair Loop", "status": "skipped", "duration_ms": 0},
            {"stage": "TSTR Copilot", "status": "skipped", "duration_ms": 0},
            # "skipped" unless RETRAIN_MODEL=true and this run's recall regressed — see
            # PipelineOrchestrator.run(). Always present so downstream stages[N] indices stay
            # stable regardless of whether the retrain actually fires.
            {"stage": "Model Retraining", "status": "skipped", "duration_ms": 0},
            {"stage": "Output Datasets", "status": "skipped", "duration_ms": 0},
        ]

        _emit_stage(on_event, "Validator", "running")

        for iteration in range(1, self.MAX_ITERS + 1):
            t0 = time.time()
            _emit(on_event, {"stage": "validating", "message": f"Script: validation pass {iteration}"})
            report = build_validation_report(
                run_id=run_id,
                audit_logs=audit_logs,
                violations=violations,
                qa_pairs=qa_pairs,
                targets=targets,
                scenario_labels=labels,
                pipeline_stages=stages,
                llm_fields_actual=llm_fields_actual,
                scope_types=scope_types,
            )
            internal = report.pop("_internal", {})
    # Only repair schema / PII / label failures — not duplicate warnings
            schema_fail_ids = set()
            for f in report["validators"]["schema_validity"].get("flagged", []):
                schema_fail_ids.add(f["log_id"])
            pii_fail_ids = {f["log_id"] for f in report["validators"]["pii_leakage"].get("flagged", [])}
            failing_logs = schema_fail_ids | pii_fail_ids
            failing_violations = set(internal.get("failing_violation_ids", []))
            duration = int((time.time() - t0) * 1000)
            stages[2] = {"stage": "Validator", "status": "completed", "duration_ms": duration}
            _emit_stage(on_event, "Validator", "completed", duration)

            schema_ok = report["validators"]["schema_validity"]["status"] != "fail"
            label_ok = report["validators"]["label_alignment"]["status"] != "fail"
            pii_ok = report["validators"]["pii_leakage"]["status"] != "fail"

            if not failing_logs and not failing_violations and schema_ok and label_ok and pii_ok:
                _emit(on_event, {"stage": "validating", "message": "Script: all validators passed", "failures": 0})
                break

            n_fail = len(failing_logs) + len(failing_violations)
            _emit(
                on_event,
                {
                    "stage": "repairing",
                    "message": f"Script: {n_fail} failures detected — repairing (iter {iteration})",
                    "failures": n_fail,
                },
            )
            stages[3] = {"stage": "Repair Loop", "status": "running", "duration_ms": 0}
            _emit_stage(on_event, "Repair Loop", "running")
            t1 = time.time()

            # Repair logs: fix enums / timestamps / strip PII-like substrings
            by_id = {r["log_id"]: r for r in audit_logs}
            for lid in failing_logs:
                row = by_id.get(lid)
                if not row:
                    continue
                repaired_ids.append(lid)
                if row.get("action") not in ("CREATE", "UPDATE", "DELETE", "APPROVE", "EXPORT", "READ"):
                    row["action"] = "READ"
                if row.get("outcome") not in ("success", "denied"):
                    row["outcome"] = "success"
                if row.get("sensitivity") not in ("low", "medium", "high", "critical"):
                    row["sensitivity"] = "medium"
                ts = str(row.get("timestamp", ""))
                if "T" not in ts or not ts.endswith("Z"):
                    row["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                # scrub obvious emails/ssn from resource
                res = str(row.get("resource", ""))
                if "@" in res:
                    row["resource"] = res.split("/contact/")[0] + "/contact/redacted"
                if any(c.isdigit() for c in res) and "-" in res and len(res) > 20:
                    import re

                    row["resource"] = re.sub(r"\d{3}-\d{2}-\d{4}", "REDACTED", res)

            # Repair violations: force taxonomy triple
            for v in violations:
                if v["violation_id"] in failing_violations or v.get("violation_type") not in TAXONOMY:
                    vtype = v.get("violation_type")
                    if vtype not in TAXONOMY:
                        vtype = next(iter(TAXONOMY))
                        v["violation_type"] = vtype
                    meta = TAXONOMY[vtype]
                    if v.get("control_id") not in meta["control_ids"]:
                        v["control_id"] = meta["control_ids"][0]
                    v["severity"] = meta["severity"]

            stages[3] = {
                "stage": "Repair Loop",
                "status": "completed",
                "duration_ms": int((time.time() - t1) * 1000),
            }
            _emit_stage(on_event, "Repair Loop", "completed", stages[3]["duration_ms"])
            _emit(on_event, {"stage": "validating", "message": "Script: re-validating after repair"})
        else:
            _emit(
                on_event,
                {
                    "stage": "validating",
                    "message": "Script: max repair iterations reached — writing best-effort report",
                    "failures": len(failing_logs) + len(failing_violations),
                },
            )

        # Repair Loop never ran (clean first pass) — emit its still-"skipped" state once so the
        # frontend live stepper isn't left waiting on a status that will never otherwise arrive.
        if stages[3]["status"] == "skipped":
            _emit_stage(on_event, "Repair Loop", "skipped")

        report = build_validation_report(
            run_id=run_id,
            audit_logs=audit_logs,
            violations=violations,
            qa_pairs=qa_pairs,
            targets=targets,
            scenario_labels=labels,
            pipeline_stages=stages,
            llm_fields_actual=llm_fields_actual,
            scope_types=scope_types,
        )
        report.pop("_internal", None)
        report["repair_log"] = {"repaired_log_ids": repaired_ids[:50], "iterations": min(iteration, self.MAX_ITERS)}
        corpus_out = {
            "audit_logs": audit_logs,
            "violations": violations,
            "qa_pairs": qa_pairs,
            "scenario_labels": labels,
        }
        return corpus_out, report


class TSTRCopilotAgent:
    """Train/eval logistic regression + rule-grounded corpus Q&A."""

    def run_tstr(
        self,
        train_corpus: dict[str, Any],
        *,
        packs: list[str],
        control_classes: list[str] | None,
        n_eval: int = 400,
        on_event: EventCb | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[int], list[dict[str, Any]], list[int]]:
        """Returns (metrics, train_logs, train_labels, eval_logs, eval_labels) — the raw
        logs/labels are needed by the caller for a possible persisted-model retrain step
        (see PipelineOrchestrator.run) but are never embedded in `metrics` itself, since that
        dict is written verbatim into validation_report.json."""
        _emit(on_event, {"stage": "tstr", "message": "Script: building realistic-ratio EVAL set"})
        engine = ScenarioEngine(
            packs=packs,
            control_classes=control_classes,
            scenario_mix=EVAL_TARGETS,
            n_logs=n_eval,
            industry="financial_services",
            seed="eval-holdout",
            mode="eval",
        )
        eval_plan = engine.compose_plan()
        eval_plan["engine"] = engine
        eval_corpus = generate_corpus(eval_plan, engine)

        train_logs = train_corpus["audit_logs"]
        train_labels = [
            1 if train_corpus["scenario_labels"].get(r["log_id"]) == "violation" else 0
            for r in train_logs
        ]
        eval_logs = eval_corpus["audit_logs"]
        eval_labels = [
            1 if eval_corpus["scenario_labels"].get(r["log_id"]) == "violation" else 0
            for r in eval_logs
        ]
        metrics = run_tstr(train_logs, train_labels, eval_logs, eval_labels)
        metrics = _merge_transformer_metrics(metrics)
        _emit(
            on_event,
            {
                "stage": "tstr",
                "message": f"Script (sklearn LogisticRegression): rare-class recall {metrics['baseline_rare_recall']:.2f} → {metrics['synthetic_trained_rare_recall']:.2f}",
                "tstr": metrics,
            },
        )
        return metrics, train_logs, train_labels, eval_logs, eval_labels

    def answer(
        self,
        query: str,
        *,
        audit_logs: list[dict[str, Any]],
        violations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        q = query.lower().strip()
        # Keyword → violation_type map covering full taxonomy
        keyword_map = [
            ("segregation of duties", "segregation_of_duties"),
            ("segregation", "segregation_of_duties"),
            ("sod", "segregation_of_duties"),
            ("invoice approval", "segregation_of_duties"),
            ("privileged", "privileged_access_misuse"),
            ("pam", "privileged_access_misuse"),
            ("without approval", "change_without_approval"),
            ("change", "change_without_approval"),
            ("journal", "journal_entry_override"),
            ("period close", "period_close_breach"),
            ("quarter", "period_close_breach"),
            ("vendor", "vendor_master_tamper"),
            ("audit trail", "audit_trail_gap"),
            ("access lifecycle", "access_lifecycle_breach"),
            ("unauthorized", "access_lifecycle_breach"),
            ("late dsar", "late_dsar"),
            ("dsar", "late_dsar"),
            ("erasure", "erasure_failure"),
            ("lawful basis", "unlawful_basis"),
            ("purpose", "purpose_limitation_breach"),
            ("minimisation", "data_minimisation_breach"),
            ("minimization", "data_minimisation_breach"),
            ("cross border", "cross_border_transfer"),
            ("transfer", "cross_border_transfer"),
            ("breach notification", "breach_notification_late"),
            ("consent", "consent_lifecycle_breach"),
            ("sox", None),
            ("gdpr", None),
        ]
        matched_types: set[str] = set()
        pack_filter: str | None = None
        for kw, vtype in keyword_map:
            if kw in q:
                if kw == "sox":
                    pack_filter = "SOX"
                elif kw == "gdpr":
                    pack_filter = "GDPR"
                elif vtype:
                    matched_types.add(vtype)

        results = violations
        if matched_types:
            results = [v for v in results if v["violation_type"] in matched_types]
        if pack_filter:
            results = [
                v
                for v in results
                if TAXONOMY.get(v["violation_type"], {}).get("pack") == pack_filter
            ]
        if not matched_types and pack_filter is None:
            results = [
                v
                for v in results
                if v["violation_type"].replace("_", " ") in q
                or q in v["explanation"].lower()
                or q in v["control_id"].lower()
            ]

        results = results[:8]
        log_by_id = {r["log_id"]: r for r in audit_logs}
        citations = []
        for v in results:
            log = log_by_id.get(v["log_id"])
            citations.append(
                {
                    "violation_id": v["violation_id"],
                    "log_id": v["log_id"],
                    "control_id": v["control_id"],
                    "violation_type": v["violation_type"],
                    "severity": v["severity"],
                    "explanation": v["explanation"],
                    "evidence": log,
                }
            )

        if not citations:
            answer = "No matching violations found in the current corpus. Try SoD, late DSAR, or a control id like SOD-04."
        else:
            lines = [
                f"- {c['log_id']} / {c['control_id']} ({c['severity']}): {c['explanation']}"
                for c in citations
            ]
            answer = f"Found {len(citations)} matching violation(s) with cited evidence_log_ids:\n" + "\n".join(lines)

        return {
            "answer": answer,
            "evidence_log_ids": [c["log_id"] for c in citations],
            "citations": citations,
            "grounding": "high" if citations else "low",
        }

    def answer_with_rephrase(
        self,
        query: str,
        *,
        audit_logs: list[dict[str, Any]],
        violations: list[dict[str, Any]],
        checkpoint_dir: Path,
    ) -> dict[str, Any]:
        """Same grounding/citations as answer() — that logic is unchanged and stays the sole
        source of truth for which violations match and what gets cited. If (and only if) an
        "active" retrain-target checkpoint exists, asks it to rewrite the answer text in more
        natural language, never touching citations. Falls back to the untouched rule-based answer
        on any failure, unavailable provider, or no active checkpoint — same discipline
        LogGeneratorAgent already uses for per-batch fallback to deterministic content."""
        result = self.answer(query, audit_logs=audit_logs, violations=violations)
        result["model_backend"] = "rule_based"

        snapshot = load_latest_retrain_model_snapshot(checkpoint_dir)
        if not snapshot or snapshot.get("status") != "active":
            return result

        provider = get_retrain_provider()
        if not provider.available:
            return result

        rephrased = provider.complete_json(
            system=(
                "Rewrite the given compliance answer in clear natural language. Keep every "
                "log_id, control_id, and cited fact exactly as given — do not add, remove, or "
                "invent any citation. Return strict JSON {\"answer\": \"...\"}, no extra "
                "commentary."
            ),
            user=json.dumps({"answer": result["answer"], "citations": result["citations"]}),
        )
        if isinstance(rephrased, dict) and isinstance(rephrased.get("answer"), str) and rephrased["answer"].strip():
            result["answer"] = rephrased["answer"]
            result["model_backend"] = f"retrain-model-v{snapshot.get('model_version')}"
        return result


class PipelineOrchestrator:
    """Wires the 4 agents end-to-end and writes the output contract."""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)
        self.composer = ScenarioComposerAgent()
        self.generator = LogGeneratorAgent()
        self.validator = ValidatorRepairAgent()
        self.tstr = TSTRCopilotAgent()

    def run(
        self,
        *,
        packs: list[str],
        control_classes: list[str] | None = None,
        scenario_mix: dict[str, float] | None = None,
        n_logs: int = 200,
        industry: str = "financial_services",
        on_event: EventCb | None = None,
    ) -> dict[str, Any]:
        run_id = f"run_{datetime.now(timezone.utc).strftime('%Y_%m_%d_%H%M')}"
        job_id = f"job_{uuid.uuid4().hex[:10]}"

        previous_feedback = None
        feedback_state_path = self.out_dir / "feedback_state.json"
        if feedback_state_path.exists():
            import json
            previous_feedback = json.loads(feedback_state_path.read_text(encoding="utf-8"))

        _emit_stage(on_event, "Scenario Composer", "running")
        t_compose0 = time.time()
        plan = self.composer.run(
            packs=packs,
            control_classes=control_classes,
            scenario_mix=scenario_mix,
            n_logs=n_logs,
            industry=industry,
            on_event=on_event,
        )
        compose_duration_ms = int((time.time() - t_compose0) * 1000)
        _emit_stage(on_event, "Scenario Composer", "completed", compose_duration_ms)
        if previous_feedback:
            weights = previous_feedback.get("violation_type_weights", {})
            if weights and plan.get("violation_type_counts"):
                counts = plan["violation_type_counts"]
                boosted = {
                    vtype: max(1, int(round(count * weights.get(vtype, 1.0))))
                    for vtype, count in counts.items()
                }
                total = sum(boosted.values()) or 1
                if total != sum(counts.values()):
                    scale = sum(counts.values()) / total
                    boosted = {vtype: max(1, int(round(count * scale))) for vtype, count in boosted.items()}
                plan["violation_type_counts"] = boosted
                plan["feedback_weights"] = weights
        _emit_stage(on_event, "Log Generator", "running")
        t_gen0 = time.time()
        corpus = self.generator.run(plan, on_event=on_event)
        gen_duration_ms = int((time.time() - t_gen0) * 1000)
        _emit_stage(on_event, "Log Generator", "completed", gen_duration_ms)
        # ScenarioEngine floors n_logs to a minimum of 20 (see scenario_engine.py's
        # `self.n_logs = max(n_logs, 20)`) — targets must be derived from plan["n_logs"] (what
        # actually got generated), not the raw request, or a small n_logs request shows a
        # target that never matches dataset_actual (e.g. "20 / 1" on the dashboard).
        actual_n_logs = plan["n_logs"]
        targets = {
            "audit_logs": actual_n_logs,
            "violations": sum(plan["violation_type_counts"].values()),
            "qa_pairs": max(20, actual_n_logs // 10),
            "llm_fields": corpus.get("llm_fields_target", 0),
        }
        corpus, report = self.validator.run(
            corpus,
            run_id=run_id,
            targets=targets,
            llm_fields_actual=corpus.get("llm_fields_actual", 0),
            scope_types=control_classes or list({v["violation_type"] for v in corpus["violations"]}),
            on_event=on_event,
        )

        _emit_stage(on_event, "TSTR Copilot", "running")
        t_tstr0 = time.time()
        tstr_metrics, tstr_train_logs, tstr_train_labels, tstr_eval_logs, tstr_eval_labels = self.tstr.run_tstr(
            corpus,
            packs=packs,
            control_classes=control_classes,
            n_eval=min(1000, max(400, n_logs * 2)),
            on_event=on_event,
        )
        tstr_duration_ms = int((time.time() - t_tstr0) * 1000)
        _emit_stage(on_event, "TSTR Copilot", "completed", tstr_duration_ms)
        previous_lift = float(previous_feedback.get("last_recall_lift", 0.0)) if previous_feedback else 0.0
        current_lift = float(tstr_metrics.get("recall_lift", 0.0))
        feedback_update = update_feedback_state(
            self.out_dir,
            run_id=run_id,
            violation_types=list({v["violation_type"] for v in corpus["violations"]}),
            label_counts={k: int(v) for k, v in {"violation": sum(1 for r in corpus["audit_logs"] if corpus["scenario_labels"].get(r["log_id"]) == "violation"), "normal": sum(1 for r in corpus["audit_logs"] if corpus["scenario_labels"].get(r["log_id"]) == "normal")}.items()},
            previous_recall_lift=previous_lift,
            current_recall_lift=current_lift,
            status="completed",
            previous_state=previous_feedback,
        )

        # Persisted retraining: only when explicitly opted in AND this run's recall regressed
        # or failed to improve vs. the last run (same `improved` comparison feedback.py already
        # makes for scenario-mix reweighting). Unlike run_tstr()'s from-scratch fit-and-discard
        # model above, this refits over the *cumulative* on-disk training history so the
        # persisted model actually grows with more data across runs — see tstr.py's
        # retrain_persisted_model() docstring for why that (not warm_start) is what makes this
        # "learn" (logistic regression's loss is convex: warm_start only affects solver
        # iteration count, not the fitted result for a given dataset).
        checkpoint_dir = self.out_dir / "checkpoints"
        retrain_enabled = _bool_env("RETRAIN_MODEL", False)
        improved = feedback_update["history_entry"]["improved"]
        # Exposed unconditionally so the UI can explain *why* this stage is skipped — "the
        # feature is off" reads very differently from "it's on, but recall didn't regress."
        tstr_metrics["retrain_enabled"] = retrain_enabled
        if retrain_enabled and not improved:
            _emit_stage(on_event, "Model Retraining", "running")
            t_retrain0 = time.time()
            retrain_result = retrain_persisted_model(
                checkpoint_dir,
                tstr_train_logs,
                tstr_train_labels,
                tstr_eval_logs,
                tstr_eval_labels,
            )
            retrain_duration_ms = int((time.time() - t_retrain0) * 1000)
            tstr_metrics.update(retrain_result)
            retrain_stage_status = "completed"
            _emit_stage(on_event, "Model Retraining", "completed", retrain_duration_ms)
        else:
            tstr_metrics["retrained"] = False
            # Even when this run didn't retrain, surface the persisted model's last-known state
            # (confusion matrix, metrics, version, trend history) from disk — otherwise the
            # whole "Retrain Impact" panel would vanish from the dashboard the moment a single
            # run's recall holds steady, even though a persisted model still exists.
            # `confusion_matrix_before`/`metrics_before` stay unset: those describe "the model
            # right before THIS retrain," which doesn't apply when no retrain happened this run.
            snapshot = load_latest_retrain_snapshot(checkpoint_dir)
            if snapshot:
                tstr_metrics["retrain_history"] = snapshot.get("history", [])
                tstr_metrics["model_version"] = snapshot.get("model_version")
                tstr_metrics["cumulative_train_size"] = snapshot.get("cumulative_train_size")
                tstr_metrics["trained_at"] = snapshot.get("trained_at")
                tstr_metrics["confusion_matrix_after"] = snapshot.get("confusion_matrix_after")
                tstr_metrics["metrics_after"] = snapshot.get("metrics_after")
                tstr_metrics["post_retrain_recall"] = (snapshot.get("metrics_after") or {}).get("recall")
            else:
                tstr_metrics["retrain_history"] = []
            retrain_stage_status = "skipped"
            retrain_duration_ms = 0
            _emit_stage(on_event, "Model Retraining", "skipped")

        report["tstr_metrics"] = tstr_metrics
        report["feedback_loop"] = {
            "new_violation_patterns": feedback_update["new_violation_patterns"],
            "next_violation_type_weights": feedback_update["next_violation_type_weights"],
            "improved": feedback_update["history_entry"]["improved"],
        }
        # Fill in the stages this orchestrator itself timed — build_validation_report() can't
        # measure these since it doesn't call composer/generator/tstr; only Validator/Repair
        # Loop are timed inside ValidatorRepairAgent, where they actually run.
        stages = report.get("pipeline_stages", [])
        while len(stages) < 7:
            stages.append({"stage": "Output Datasets", "status": "completed", "duration_ms": 0})
        if len(stages) >= 2:
            stages[0] = {"stage": "Scenario Composer", "status": "completed", "duration_ms": compose_duration_ms}
            stages[1] = {"stage": "Log Generator", "status": "completed", "duration_ms": gen_duration_ms}
        if len(stages) >= 5:
            stages[4] = {"stage": "TSTR Copilot", "status": "completed", "duration_ms": tstr_duration_ms}
        if len(stages) >= 6:
            stages[5] = {"stage": "Model Retraining", "status": retrain_stage_status, "duration_ms": retrain_duration_ms}
        report["pipeline_stages"] = stages

        provider = get_provider()
        manifest = {
            "version": "1.0.0",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "job_id": job_id,
            "total_records": len(corpus["audit_logs"]),
            "regulation_packs": packs,
            "control_classes": control_classes or [c["violation_type"] for c in []],
            "scenario_mix": plan["scenario_counts"],
            "model_used": provider.model if provider.available else "deterministic-scenario-engine",
            "curator_version": "0.1.0",
        }
        if not control_classes:
            manifest["control_classes"] = list({v["violation_type"] for v in corpus["violations"]})

        _emit_stage(on_event, "Output Datasets", "running")
        t_write0 = time.time()
        write_dataset_bundle(
            self.out_dir,
            audit_logs=corpus["audit_logs"],
            violations=corpus["violations"],
            qa_pairs=corpus["qa_pairs"],
            validation_report=report,
            dataset_manifest=manifest,
        )
        write_duration_ms = int((time.time() - t_write0) * 1000)
        # The report written above necessarily still has this stage's *previous* duration —
        # it can't know its own write time before the write happens. Correct it with one small
        # follow-up atomic write of just the report (audit_logs/violations/qa_pairs/manifest are
        # already correct and untouched — this doesn't re-write them).
        stages[6] = {"stage": "Output Datasets", "status": "completed", "duration_ms": write_duration_ms}
        report["pipeline_stages"] = stages
        write_json(self.out_dir / "validation_report.json", {k: v for k, v in report.items() if not k.startswith("_")})
        _emit_stage(on_event, "Output Datasets", "completed", write_duration_ms)
        _emit(on_event, {"stage": "complete", "message": "Pipeline complete", "run_id": run_id, "job_id": job_id})
        return {
            "run_id": run_id,
            "job_id": job_id,
            "report": report,
            "manifest": manifest,
            "counts": {
                "audit_logs": len(corpus["audit_logs"]),
                "violations": len(corpus["violations"]),
                "qa_pairs": len(corpus["qa_pairs"]),
            },
            "mode": "live",
        }
