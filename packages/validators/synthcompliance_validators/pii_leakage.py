"""PII leakage scanner — regex Presidio-compatible entities on all string fields."""

from __future__ import annotations

import re
from typing import Any

# Scan these fields especially (resource/device often leak PII in synthetic data)
SCAN_FIELDS = ("user_id", "resource", "system", "role", "action", "explanation")

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("PHONE", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("IP_ADDRESS", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b")),
]


def _redact(entity: str, value: str) -> str:
    if entity == "EMAIL":
        local, _, domain = value.partition("@")
        return f"{local[:1]}***@●●●●.{domain.rsplit('.', 1)[-1]}"
    if entity == "SSN":
        return f"●●●-●●-{value[-4:]}"
    return value[:2] + "●●●" + value[-2:]


def _scan_text(text: str) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for entity, pat in PATTERNS:
        for m in pat.finditer(text):
            hits.append((entity, m.group(0)))
    return hits


def check_pii_leakage(
    audit_logs: list[dict[str, Any]],
    violations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    flagged: list[dict[str, str]] = []
    detections = 0

    for row in audit_logs:
        log_id = str(row.get("log_id", "?"))
        for field in SCAN_FIELDS:
            val = row.get(field)
            if not isinstance(val, str):
                continue
            # user_id like u_1001 is fine — only flag if it looks like email/ssn etc.
            for entity, raw in _scan_text(val):
                detections += 1
                flagged.append(
                    {
                        "log_id": log_id,
                        "entity": entity,
                        "value_redacted": _redact(entity, raw),
                    }
                )

    if violations:
        for v in violations:
            for field in ("explanation", "violation_id"):
                val = v.get(field)
                if isinstance(val, str):
                    for entity, raw in _scan_text(val):
                        # emails in explanations are usually ok as user refs; flag SSN/CC only
                        if entity in ("SSN", "CREDIT_CARD", "EMAIL"):
                            detections += 1
                            flagged.append(
                                {
                                    "log_id": str(v.get("log_id", "?")),
                                    "entity": entity,
                                    "value_redacted": _redact(entity, raw),
                                }
                            )

    target = 0
    status = "pass" if detections == 0 else ("warn" if detections <= 3 else "fail")
    return {
        "target_detections": target,
        "actual_detections": detections,
        "rows_checked": len(audit_logs),
        "status": status,
        "flagged": flagged[:20],
        "_failing_log_ids": [f["log_id"] for f in flagged],
    }
