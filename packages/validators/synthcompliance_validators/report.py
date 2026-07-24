"""Assemble validation_report.json matching the dashboard contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .duplicate_check import check_duplicates
from .golden_fidelity import score_golden_fidelity
from .label_alignment import check_label_alignment
from .pii_leakage import check_pii_leakage
from .scenario_coverage import compute_scenario_coverage
from .schema_validity import check_schema_validity
from .tstr import run_tstr


def _strip_private(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def run_all_validators(
    audit_logs: list[dict[str, Any]],
    violations: list[dict[str, Any]],
    scenario_labels: dict[str, str] | None = None,
    scope_types: list[str] | None = None,
) -> dict[str, Any]:
    schema = check_schema_validity(audit_logs)
    pii = check_pii_leakage(audit_logs, violations)
    dup = check_duplicates(audit_logs)
    label = check_label_alignment(violations, audit_logs)
    coverage = compute_scenario_coverage(audit_logs, scenario_labels)
    golden = score_golden_fidelity(audit_logs, violations, scope_types=scope_types)
    return {
        "schema_validity": schema,
        "pii_leakage": pii,
        "duplicate_check": dup,
        "label_alignment": label,
        "scenario_coverage": coverage,
        "golden_set_fidelity": golden,
    }


def build_validation_report(
    *,
    run_id: str,
    audit_logs: list[dict[str, Any]],
    violations: list[dict[str, Any]],
    qa_pairs: list[dict[str, Any]],
    targets: dict[str, int],
    scenario_labels: dict[str, str] | None = None,
    pipeline_stages: list[dict[str, Any]] | None = None,
    tstr_metrics: dict[str, Any] | None = None,
    investigation_summaries: int = 2,
    scope_types: list[str] | None = None,
) -> dict[str, Any]:
    results = run_all_validators(audit_logs, violations, scenario_labels, scope_types=scope_types)
    validators = {
        "schema_validity": _strip_private(results["schema_validity"]),
        "pii_leakage": _strip_private(results["pii_leakage"]),
        "duplicate_check": _strip_private(results["duplicate_check"]),
        "label_alignment": _strip_private(results["label_alignment"]),
        "scenario_coverage": results["scenario_coverage"],
    }
    return {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset_targets": {
            "audit_logs": targets.get("audit_logs", len(audit_logs)),
            "violations": targets.get("violations", len(violations)),
            "qa_pairs": targets.get("qa_pairs", len(qa_pairs)),
            "investigation_summaries": targets.get("investigation_summaries", investigation_summaries),
        },
        "dataset_actual": {
            "audit_logs": len(audit_logs),
            "violations": len(violations),
            "qa_pairs": len(qa_pairs),
            "investigation_summaries": investigation_summaries,
        },
        "validators": validators,
        "golden_set_fidelity": results["golden_set_fidelity"],
        "tstr_metrics": tstr_metrics
        or {
            "baseline_rare_recall": 0.0,
            "synthetic_trained_rare_recall": 0.0,
            "recall_lift": 0.0,
            "status": "pending",
        },
        "pipeline_stages": pipeline_stages or [],
        "_internal": {
            "failing_log_ids": list(
                set(results["schema_validity"].get("_failing_log_ids", []))
                | set(results["pii_leakage"].get("_failing_log_ids", []))
                | set(results["duplicate_check"].get("_failing_log_ids", []))
            ),
            "failing_violation_ids": results["label_alignment"].get("_failing_violation_ids", []),
        },
    }


# re-export for agents
__all__ = ["build_validation_report", "run_all_validators", "run_tstr"]
