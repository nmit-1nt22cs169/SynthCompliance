"""Label alignment: violation_type / control_id / severity must match taxonomy."""

from __future__ import annotations

from typing import Any

from synthcompliance_taxonomy.controls import CONTROL_BY_ID, TAXONOMY


def check_label_alignment(
    violations: list[dict[str, Any]],
    audit_logs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    log_ids = {r["log_id"] for r in (audit_logs or []) if "log_id" in r}
    flagged: list[dict[str, str]] = []
    failed = 0

    for v in violations:
        issues: list[str] = []
        vtype = v.get("violation_type")
        cid = v.get("control_id")
        sev = v.get("severity")
        lid = v.get("log_id")

        if vtype not in TAXONOMY:
            issues.append("violation_type not present in control taxonomy")
        else:
            meta = TAXONOMY[vtype]
            if cid not in meta["control_ids"]:
                issues.append("control_id does not match violation_type taxonomy")
            if sev != meta["severity"]:
                issues.append("severity inconsistent with taxonomy for violation_type")
        if cid and cid not in CONTROL_BY_ID:
            issues.append("control_id not present in control taxonomy")
        elif cid in CONTROL_BY_ID and vtype and CONTROL_BY_ID[cid]["violation_type"] != vtype:
            if "control_id does not match violation_type taxonomy" not in issues:
                issues.append("control_id does not match violation_type taxonomy")
        if audit_logs is not None and lid and lid not in log_ids:
            issues.append("log_id does not resolve to audit_logs")

        if issues:
            failed += 1
            flagged.append({"violation_id": str(v.get("violation_id", "?")), "issue": issues[0]})

    n = max(len(violations), 1)
    pass_rate = 1.0 - (failed / n) if violations else 1.0
    target = 0.95
    status = "pass" if pass_rate >= target else ("warn" if pass_rate >= 0.90 else "fail")
    return {
        "target_pass_rate": target,
        "actual_pass_rate": round(pass_rate, 4),
        "rows_checked": len(violations),
        "rows_failed": failed,
        "status": status,
        "flagged": flagged[:20],
        "_failing_violation_ids": [f["violation_id"] for f in flagged],
    }
