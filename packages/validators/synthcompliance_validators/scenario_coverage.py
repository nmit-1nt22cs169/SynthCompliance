"""Scenario coverage counts for class-balance reporting."""

from __future__ import annotations

from typing import Any


def compute_scenario_coverage(
    audit_logs: list[dict[str, Any]],
    scenario_labels: dict[str, str] | None = None,
) -> dict[str, int]:
    """
    scenario_labels maps log_id -> one of normal|suspicious|violation|false_positive.
    If missing, infer: logs referenced by violations -> violation, else normal.
    """
    counts = {"normal": 0, "suspicious": 0, "violation": 0, "false_positive": 0}
    if scenario_labels:
        for lid in (r.get("log_id") for r in audit_logs):
            label = scenario_labels.get(str(lid), "normal")
            counts[label] = counts.get(label, 0) + 1
        return counts

    # Fallback — should not be used when generator tags scenarios
    for _ in audit_logs:
        counts["normal"] += 1
    return counts
