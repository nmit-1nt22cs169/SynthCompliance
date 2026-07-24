"""Generate golden/*.jsonl — 10 deterministic seed records per violation_type."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "taxonomy"))

from synthcompliance_taxonomy.controls import TAXONOMY  # noqa: E402
from synthcompliance_taxonomy.roster import ASSET_LIST, USER_ROSTER  # noqa: E402

OUT = ROOT / "packages" / "taxonomy" / "golden"
OUT.mkdir(parents=True, exist_ok=True)

EXPLANATIONS = {
    "segregation_of_duties": (
        "User {uid} both created and approved {resource}, violating maker-checker separation."
    ),
    "privileged_access_misuse": (
        "Privileged account {uid} ({role}) misused elevated access on {resource}."
    ),
    "change_without_approval": (
        "Change to {resource} deployed by {uid} without a recorded approval step."
    ),
    "journal_entry_override": (
        "Journal entry override on {resource} by {uid} bypassed standard JE controls."
    ),
    "period_close_breach": (
        "Period-close control breach on {resource} during quarter-end pressure window."
    ),
    "vendor_master_tamper": (
        "Unauthorized vendor-master modification on {resource} by {uid}."
    ),
    "audit_trail_gap": (
        "Audit trail gap detected for action on {resource}; required logging missing."
    ),
    "access_lifecycle_breach": (
        "Access lifecycle breach: {uid} retained or gained access to {resource} improperly."
    ),
    "late_dsar": (
        "DSAR on {resource} fulfilled after the 30-day window with no extension justification."
    ),
    "erasure_failure": (
        "Right-to-erasure request failed for {resource}; residual PII retained."
    ),
    "unlawful_basis": (
        "Processing of {resource} by {uid} lacked a lawful basis under Art. 6."
    ),
    "purpose_limitation_breach": (
        "Data from {resource} reused beyond stated purpose by {uid}."
    ),
    "data_minimisation_breach": (
        "Excessive personal data collected/exported via {resource}."
    ),
    "cross_border_transfer": (
        "Cross-border transfer of {resource} without adequate Art. 44-49 safeguards."
    ),
    "breach_notification_late": (
        "Personal-data breach notification for {resource} exceeded the 72-hour threshold."
    ),
    "consent_lifecycle_breach": (
        "Consent record for {resource} was expired/withdrawn when {uid} processed it."
    ),
}

ACTIONS_BY_TYPE = {
    "segregation_of_duties": "APPROVE",
    "privileged_access_misuse": "UPDATE",
    "change_without_approval": "UPDATE",
    "journal_entry_override": "CREATE",
    "period_close_breach": "APPROVE",
    "vendor_master_tamper": "UPDATE",
    "audit_trail_gap": "DELETE",
    "access_lifecycle_breach": "READ",
    "late_dsar": "EXPORT",
    "erasure_failure": "DELETE",
    "unlawful_basis": "READ",
    "purpose_limitation_breach": "EXPORT",
    "data_minimisation_breach": "EXPORT",
    "cross_border_transfer": "EXPORT",
    "breach_notification_late": "CREATE",
    "consent_lifecycle_breach": "UPDATE",
}


def quarter_end_ts(seed: int) -> str:
    """Skew some SOX events into last-5-business-days-of-quarter."""
    # 2026-03-31, 2026-06-30, 2026-09-30, 2026-12-31 windows
    anchors = [
        datetime(2026, 3, 27, 18, 0, tzinfo=timezone.utc),
        datetime(2026, 6, 26, 17, 30, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 19, 0, tzinfo=timezone.utc),
        datetime(2026, 12, 29, 16, 45, tzinfo=timezone.utc),
    ]
    base = anchors[seed % 4]
    return (base + timedelta(hours=seed % 24, minutes=seed % 50)).strftime("%Y-%m-%dT%H:%M:%SZ")


def normal_ts(seed: int) -> str:
    base = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    return (base + timedelta(hours=seed * 3, minutes=seed * 7)).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    index: list[dict] = []
    for vtype, meta in TAXONOMY.items():
        rows = []
        for i in range(10):
            user = USER_ROSTER[(hash(vtype) + i) % len(USER_ROSTER)]
            asset = ASSET_LIST[(hash(vtype) * 3 + i * 7) % len(ASSET_LIST)]
            control_id = meta["control_ids"][i % len(meta["control_ids"])]
            pack = meta["pack"]
            ts = quarter_end_ts(i) if pack == "SOX" and i % 2 == 0 else normal_ts(i + hash(vtype) % 50)
            log_id = f"golden_{vtype[:8]}_{i:02d}"
            explanation = EXPLANATIONS[vtype].format(
                uid=user["user_id"],
                role=user["role"],
                resource=asset["resource"],
            )
            record = {
                "audit_log": {
                    "log_id": log_id,
                    "timestamp": ts,
                    "user_id": user["user_id"],
                    "action": ACTIONS_BY_TYPE[vtype],
                    "resource": asset["resource"],
                    "outcome": "success",
                    "role": user["role"],
                    "sensitivity": "critical" if meta["severity"] == "critical" else "high",
                    "system": asset["system"],
                },
                "violation": {
                    "violation_id": f"GV-{vtype[:6].upper()}-{i:02d}",
                    "log_id": log_id,
                    "violation_type": vtype,
                    "control_id": control_id,
                    "severity": meta["severity"],
                    "explanation": explanation,
                },
                "seed_conditions": {
                    "pack": pack,
                    "violation_type": vtype,
                    "control_id": control_id,
                    "severity": meta["severity"],
                    "action": ACTIONS_BY_TYPE[vtype],
                    "role": user["role"],
                },
            }
            rows.append(record)
        path = OUT / f"{vtype}.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        index.append({"violation_type": vtype, "count": len(rows), "file": path.name})
        print(f"wrote {path.name}: {len(rows)}")

    (OUT / "index.json").write_text(json.dumps({"classes": index, "per_class": 10}, indent=2), encoding="utf-8")
    print(f"golden set ready: {len(index)} classes × 10")


if __name__ == "__main__":
    main()
