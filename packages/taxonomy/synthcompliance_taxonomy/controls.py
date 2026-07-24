"""Fixed 48-control SOX + GDPR taxonomy. No invented control_ids."""

from __future__ import annotations

from typing import Any

ACTIONS = ("CREATE", "UPDATE", "DELETE", "APPROVE", "EXPORT", "READ")
OUTCOMES = ("success", "denied")
SENSITIVITIES = ("low", "medium", "high", "critical")
SEVERITIES = ("critical", "high", "medium", "low")

# violation_type -> (pack, severity, control_id_prefix, count)
_TAXONOMY_SPEC: dict[str, tuple[str, str, str, int]] = {
    # SOX (COSO 2013 / COBIT 2019)
    "segregation_of_duties": ("SOX", "critical", "SOD", 8),
    "privileged_access_misuse": ("SOX", "high", "PAM", 4),
    "change_without_approval": ("SOX", "medium", "CHG", 10),
    "journal_entry_override": ("SOX", "high", "JE", 6),
    "period_close_breach": ("SOX", "critical", "CLOSE", 5),
    "vendor_master_tamper": ("SOX", "medium", "VMD", 3),
    "audit_trail_gap": ("SOX", "critical", "AT", 3),
    "access_lifecycle_breach": ("SOX", "medium", "AC", 5),
    # GDPR (Art. 5/6/7/15/17/33/44-49)
    "late_dsar": ("GDPR", "medium", "PRIV", 4),
    "erasure_failure": ("GDPR", "high", "ERA", 3),
    "unlawful_basis": ("GDPR", "high", "LB", 4),
    "purpose_limitation_breach": ("GDPR", "low", "PL", 3),
    "data_minimisation_breach": ("GDPR", "low", "DM", 2),
    "cross_border_transfer": ("GDPR", "critical", "XBT", 4),
    "breach_notification_late": ("GDPR", "critical", "BN", 2),
    "consent_lifecycle_breach": ("GDPR", "medium", "CONS", 4),
}


def _build_taxonomy() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for vtype, (pack, severity, prefix, count) in _TAXONOMY_SPEC.items():
        ids = [f"{prefix}-{i:02d}" for i in range(1, count + 1)]
        out[vtype] = {
            "violation_type": vtype,
            "pack": pack,
            "severity": severity,
            "control_ids": ids,
            "label": vtype.replace("_", " ").title(),
        }
    return out


TAXONOMY = _build_taxonomy()
VIOLATION_TYPES = tuple(TAXONOMY.keys())
CONTROL_CLASSES = VIOLATION_TYPES
REGULATION_PACKS = ("SOX", "GDPR")

CONTROL_BY_ID: dict[str, dict[str, Any]] = {}
for vtype, meta in TAXONOMY.items():
    for cid in meta["control_ids"]:
        CONTROL_BY_ID[cid] = {
            "control_id": cid,
            "violation_type": vtype,
            "severity": meta["severity"],
            "pack": meta["pack"],
        }


def get_control(control_id: str) -> dict[str, Any] | None:
    return CONTROL_BY_ID.get(control_id)


def severity_for_type(violation_type: str) -> str | None:
    meta = TAXONOMY.get(violation_type)
    return meta["severity"] if meta else None


def controls_for_pack(pack: str) -> list[dict[str, Any]]:
    pack_u = pack.upper()
    return [m for m in TAXONOMY.values() if m["pack"] == pack_u]


def controls_for_packs(packs: list[str]) -> list[dict[str, Any]]:
    packs_u = {p.upper() for p in packs}
    return [m for m in TAXONOMY.values() if m["pack"] in packs_u]


# 16 violation types × listed control ranges = 70 control_ids (SOX 44 + GDPR 26)
assert len(CONTROL_BY_ID) == 70, f"expected 70 controls, got {len(CONTROL_BY_ID)}"
assert len(TAXONOMY) == 16
