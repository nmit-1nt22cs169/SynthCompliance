"""Schema validity: enums, ISO timestamps, required fields."""

from __future__ import annotations

import re
from typing import Any

from synthcompliance_taxonomy.controls import ACTIONS, OUTCOMES, SENSITIVITIES

ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

REQUIRED_LOG_FIELDS = (
    "log_id",
    "timestamp",
    "user_id",
    "action",
    "resource",
    "outcome",
    "role",
    "sensitivity",
    "system",
)


def check_schema_validity(audit_logs: list[dict[str, Any]]) -> dict[str, Any]:
    flagged: list[dict[str, str]] = []
    failed = 0
    for row in audit_logs:
        row_failed = False
        for field in REQUIRED_LOG_FIELDS:
            if field not in row or row[field] in (None, ""):
                flagged.append({"log_id": str(row.get("log_id", "?")), "field": field, "issue": "missing enum value" if field == "sensitivity" else "missing required field"})
                row_failed = True
        ts = row.get("timestamp")
        if isinstance(ts, str) and ts and not ISO_RE.match(ts):
            flagged.append({"log_id": str(row.get("log_id", "?")), "field": "timestamp", "issue": "non-ISO8601 format"})
            row_failed = True
        action = row.get("action")
        if action is not None and action != "" and action not in ACTIONS:
            flagged.append({"log_id": str(row.get("log_id", "?")), "field": "action", "issue": "unrecognized action code"})
            row_failed = True
        outcome = row.get("outcome")
        if outcome is not None and outcome != "" and outcome not in OUTCOMES:
            flagged.append({"log_id": str(row.get("log_id", "?")), "field": "outcome", "issue": "invalid outcome enum"})
            row_failed = True
        sens = row.get("sensitivity")
        if sens is not None and sens != "" and sens not in SENSITIVITIES:
            flagged.append({"log_id": str(row.get("log_id", "?")), "field": "sensitivity", "issue": "missing enum value"})
            row_failed = True
        if row_failed:
            failed += 1

    n = max(len(audit_logs), 1)
    pass_rate = 1.0 - (failed / n)
    target = 0.98
    status = "pass" if pass_rate >= target else ("warn" if pass_rate >= 0.95 else "fail")
    return {
        "target_pass_rate": target,
        "actual_pass_rate": round(pass_rate, 4),
        "rows_checked": len(audit_logs),
        "rows_failed": failed,
        "status": status,
        "flagged": flagged[:20],
        "_failing_log_ids": [f["log_id"] for f in flagged],
    }
