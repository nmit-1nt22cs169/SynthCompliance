"""Log / violation / QA generators with closed enums and ID pool discipline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from synthcompliance_taxonomy.controls import TAXONOMY
from synthcompliance_taxonomy.roster import ASSET_LIST, USER_ROSTER

from .scenario_engine import ACTION_FOR_TYPE, EXPLANATIONS, ScenarioEngine, _iso, _quarter_end


def generate_corpus(plan: dict[str, Any], rng_seed_engine: ScenarioEngine) -> dict[str, Any]:
    """Deterministic scaffold pass: consumes the plan's id pool to build audit_logs/violations/
    qa_pairs with taxonomy-correct fields (LogGeneratorAgent overwrites the LLM-eligible content
    fields afterward). Fill order matters — violations claim log_ids first, then false_positive/
    suspicious/normal fill the remainder — so every violation_type gets its requested count before
    the pool can run out."""
    rng = rng_seed_engine.rng
    n = plan["n_logs"]
    counts = plan["scenario_counts"]
    type_counts = plan["violation_type_counts"]

    # Build ID pool first
    id_pool = [f"log_{10000 + i}" for i in range(n)]
    cursor = 0
    labels: dict[str, str] = {}
    audit_logs: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    qa_pairs: list[dict[str, Any]] = []

    base_ts = datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc)
    seq = 0

    def next_ts(force_q_end: bool = False) -> str:
        nonlocal seq
        seq += 1
        if force_q_end:
            return _iso(_quarter_end(rng))
        return _iso(base_ts + timedelta(seconds=seq * 47 + rng.randint(0, 20)))

    def mk_log(log_id: str, *, action: str | None = None, user=None, asset=None, **overrides) -> dict[str, Any]:
        user = user or rng.choice(USER_ROSTER)
        asset = asset or rng.choice(ASSET_LIST)
        row = {
            "log_id": log_id,
            "timestamp": next_ts(),
            "user_id": user["user_id"],
            "action": action or rng.choice(["CREATE", "UPDATE", "DELETE", "APPROVE", "EXPORT", "READ"]),
            "resource": asset["resource"],
            "outcome": "success" if rng.random() > 0.08 else "denied",
            "role": user["role"],
            "sensitivity": rng.choice(["low", "medium", "high", "critical"]),
            "system": asset["system"],
        }
        row.update(overrides)
        return row

    # --- violations first (consume from pool) ---
    v_num = 1
    for vtype, count in type_counts.items():
        if count <= 0:
            continue
        meta = TAXONOMY[vtype]
        for i in range(count):
            if cursor >= n:
                break
            log_id = id_pool[cursor]
            cursor += 1
            labels[log_id] = "violation"
            user = rng.choice(USER_ROSTER)
            asset = rng.choice(ASSET_LIST)
            cid = meta["control_ids"][i % len(meta["control_ids"])]
            pack = meta["pack"]
            force_q = pack == "SOX" and vtype in (
                "period_close_breach",
                "journal_entry_override",
                "segregation_of_duties",
            )
            ts = next_ts(force_q_end=force_q or (pack == "SOX" and rng.random() < 0.35))
            # GDPR DSAR realism: mark late
            sens = "critical" if meta["severity"] == "critical" else "high"
            log = mk_log(
                log_id,
                action=ACTION_FOR_TYPE.get(vtype, "UPDATE"),
                user=user,
                asset=asset,
                timestamp=ts,
                sensitivity=sens,
                outcome="success",
            )
            # late_dsar: encode day>30 in resource suffix narrative only (no PII)
            if vtype == "late_dsar":
                day = rng.randint(31, 55)
                log["resource"] = f"dsar/requests/{10000 + i}/day_{day}"
                log["system"] = "privacy-hub"
                log["action"] = "EXPORT"
            if vtype == "breach_notification_late":
                hours = rng.randint(73, 120)
                log["resource"] = f"breach/incidents/{20000 + i}/notify_{hours}h"
                log["system"] = "privacy-hub"
            audit_logs.append(log)
            explanation = EXPLANATIONS[vtype].format(
                uid=user["user_id"],
                role=user["role"],
                resource=log["resource"],
                cid=cid,
            )
            violations.append(
                {
                    "violation_id": f"V-{1000 + v_num}",
                    "log_id": log_id,
                    "violation_type": vtype,
                    "control_id": cid,
                    "severity": meta["severity"],
                    "explanation": explanation,
                }
            )
            if len(qa_pairs) < max(20, n // 10):
                qa_pairs.append(
                    {
                        "qa_id": f"QA-{200 + len(qa_pairs)}",
                        "question": f"Which logs show a {vtype.replace('_', ' ')} involving {log['resource']}?",
                        "answer": f"{log_id} — {explanation}",
                        "evidence_log_ids": [log_id],
                        "grounding": "high",
                    }
                )
            v_num += 1

    # --- false positives (look like violations, no violation row) ---
    for _ in range(counts.get("false_positive", 0)):
        if cursor >= n:
            break
        log_id = id_pool[cursor]
        cursor += 1
        labels[log_id] = "false_positive"
        # Mimic SoD / PAM patterns without labelling
        user = rng.choice(USER_ROSTER)
        asset = rng.choice(ASSET_LIST)
        audit_logs.append(
            mk_log(
                log_id,
                action=rng.choice(["APPROVE", "UPDATE", "DELETE"]),
                user=user,
                asset=asset,
                sensitivity="high",
                outcome="success",
            )
        )

    # --- suspicious ---
    for _ in range(counts.get("suspicious", 0)):
        if cursor >= n:
            break
        log_id = id_pool[cursor]
        cursor += 1
        labels[log_id] = "suspicious"
        audit_logs.append(
            mk_log(
                log_id,
                action=rng.choice(["EXPORT", "DELETE", "UPDATE"]),
                sensitivity=rng.choice(["high", "critical"]),
                outcome=rng.choice(["success", "denied"]),
            )
        )

    # --- normal fill ---
    while cursor < n:
        log_id = id_pool[cursor]
        cursor += 1
        labels[log_id] = "normal"
        audit_logs.append(mk_log(log_id))

    # Sequential sort by timestamp
    audit_logs.sort(key=lambda r: r["timestamp"])

    # Ensure every violation log_id resolves
    log_id_set = {r["log_id"] for r in audit_logs}
    violations = [v for v in violations if v["log_id"] in log_id_set]
    qa_pairs = [q for q in qa_pairs if all(e in log_id_set for e in q["evidence_log_ids"])]

    return {
        "audit_logs": audit_logs,
        "violations": violations,
        "qa_pairs": qa_pairs,
        "scenario_labels": labels,
        "id_pool": id_pool,
    }
