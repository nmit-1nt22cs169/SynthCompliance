"""Near-duplicate detection via difflib ratio on key fields, gated by temporal proximity."""

from __future__ import annotations

import difflib
from datetime import datetime
from typing import Any

# Rows with identical user/action/resource/outcome/role/system are only flagged as duplicates
# if they also happened close together in time. Without this gate, the same user performing
# the same routine action on the same resource on two different days (completely normal, and
# the generator's bounded roster/action vocabulary makes this a routine occurrence, not an edge
# case) would score a perfect content-similarity ratio and get flagged — that's not a duplicate,
# it's recurring legitimate activity. 5 minutes catches genuine same-event double-writes (which
# land within a few generator timestamp ticks of each other, ~47-67s apart) while excluding
# routine recurrence, which is typically hours apart even in a single run.
MAX_MINUTES_APART = 5.0
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _sig(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("user_id", "")),
            str(row.get("action", "")),
            str(row.get("resource", "")),
            str(row.get("outcome", "")),
            str(row.get("role", "")),
            str(row.get("system", "")),
        ]
    )


def _parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.strptime(ts, TS_FORMAT)
    except (ValueError, TypeError):
        return None


def check_duplicates(
    audit_logs: list[dict[str, Any]],
    threshold: float = 0.92,
    max_minutes_apart: float = MAX_MINUTES_APART,
) -> dict[str, Any]:
    flagged: list[dict[str, Any]] = []
    entries = [
        (str(r.get("log_id", f"i{i}")), _sig(r), _parse_ts(str(r.get("timestamp", ""))))
        for i, r in enumerate(audit_logs)
    ]
    buckets: dict[str, list[tuple[str, str, datetime | None]]] = {}
    for log_id, sig, ts in entries:
        key = "|".join(sig.split("|")[:2])
        buckets.setdefault(key, []).append((log_id, sig, ts))

    seen_pairs: set[tuple[str, str]] = set()
    for bucket in buckets.values():
        for i in range(len(bucket)):
            for j in range(i + 1, min(i + 8, len(bucket))):
                a_id, a_sig, a_ts = bucket[i]
                b_id, b_sig, b_ts = bucket[j]
                # Unparseable timestamps can't be proven close in time — don't flag rather than
                # risk a false positive (schema_validity is what catches malformed timestamps).
                if a_ts is None or b_ts is None:
                    continue
                if abs((a_ts - b_ts).total_seconds()) > max_minutes_apart * 60:
                    continue
                sim = difflib.SequenceMatcher(None, a_sig, b_sig).ratio()
                if sim >= threshold:
                    pair = tuple(sorted((a_id, b_id)))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    flagged.append(
                        {
                            "log_id": b_id,
                            "duplicate_of": a_id,
                            "similarity": round(sim, 2),
                        }
                    )

    n = max(len(audit_logs), 1)
    rate = len(flagged) / n
    target_max = 0.02
    status = "pass" if rate <= target_max else ("warn" if rate <= 0.05 else "fail")
    return {
        "target_max_rate": target_max,
        "actual_rate": round(rate, 4),
        "rows_checked": len(audit_logs),
        "rows_flagged": len(flagged),
        "status": status,
        "flagged": flagged[:20],
        "_failing_log_ids": [f["log_id"] for f in flagged],
    }
