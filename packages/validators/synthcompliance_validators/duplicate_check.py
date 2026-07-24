"""Near-duplicate detection via difflib ratio on key fields."""

from __future__ import annotations

import difflib
from typing import Any


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


def check_duplicates(audit_logs: list[dict[str, Any]], threshold: float = 0.92) -> dict[str, Any]:
    flagged: list[dict[str, Any]] = []
    sigs = [(str(r.get("log_id", f"i{i}")), _sig(r)) for i, r in enumerate(audit_logs)]
    buckets: dict[str, list[tuple[str, str]]] = {}
    for log_id, sig in sigs:
        key = "|".join(sig.split("|")[:2])
        buckets.setdefault(key, []).append((log_id, sig))

    seen_pairs: set[tuple[str, str]] = set()
    for bucket in buckets.values():
        for i in range(len(bucket)):
            for j in range(i + 1, min(i + 8, len(bucket))):
                a_id, a_sig = bucket[i]
                b_id, b_sig = bucket[j]
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
