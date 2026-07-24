"""Golden-set fidelity: label match % + statistical distribution deviation."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from synthcompliance_taxonomy.controls import TAXONOMY

DEFAULT_GOLDEN_DIR = (
    Path(__file__).resolve().parents[2] / "taxonomy" / "golden"
)


def load_golden(golden_dir: Path | None = None) -> list[dict[str, Any]]:
    gdir = golden_dir or DEFAULT_GOLDEN_DIR
    rows: list[dict[str, Any]] = []
    if not gdir.exists():
        return rows
    for path in sorted(gdir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _kl(p: Counter, q: Counter) -> float:
    keys = set(p) | set(q)
    if not keys:
        return 0.0
    n_p = sum(p.values()) or 1
    n_q = sum(q.values()) or 1
    kl = 0.0
    for k in keys:
        pk = (p[k] + 1e-9) / n_p
        qk = (q[k] + 1e-9) / n_q
        kl += pk * math.log(pk / qk)
    return kl


def score_golden_fidelity(
    audit_logs: list[dict[str, Any]],
    violations: list[dict[str, Any]],
    golden_dir: Path | None = None,
    scope_types: list[str] | None = None,
) -> dict[str, Any]:
    golden = load_golden(golden_dir)
    if not golden:
        return {
            "label_fidelity_score": 0.0,
            "statistical_fidelity_score": 0.0,
            "matched_seeds": 0,
            "total_seeds": 0,
            "max_field_deviation_pct": 100.0,
            "status": "fail",
            "notes": "golden set missing",
        }

    # Index synthetic violations by (violation_type, control_id, severity) presence
    synth_triples = {
        (v.get("violation_type"), v.get("control_id"), v.get("severity")) for v in violations
    }
    synth_by_type = Counter(v.get("violation_type") for v in violations)

    matched = 0
    for g in golden:
        seed = g.get("seed_conditions") or g.get("violation") or {}
        triple = (seed.get("violation_type"), seed.get("control_id"), seed.get("severity"))
        # Label fidelity: does generator emit the same triple for this seed class?
        if triple in synth_triples:
            matched += 1
        elif seed.get("violation_type") in synth_by_type:
            # partial: type present but control/severity may differ — count half via type presence
            gv = g.get("violation", {})
            if any(
                v.get("violation_type") == gv.get("violation_type")
                and v.get("control_id") == gv.get("control_id")
                and v.get("severity") == gv.get("severity")
                for v in violations
            ):
                matched += 1

    # Scope label fidelity to types in this run (selected control classes or emitted violations)
    if scope_types:
        scope = {t for t in scope_types if t in TAXONOMY}
    else:
        scope = {v.get("violation_type") for v in violations if v.get("violation_type") in TAXONOMY}
    if not scope:
        scope = set(TAXONOMY.keys())

    class_hits = 0
    class_total = len(scope)
    for vtype in scope:
        meta = TAXONOMY[vtype]
        expected_sev = meta["severity"]
        if any(
            v.get("violation_type") == vtype
            and v.get("severity") == expected_sev
            and v.get("control_id") in meta["control_ids"]
            for v in violations
        ):
            class_hits += 1

    label_score = round(100.0 * class_hits / max(class_total, 1), 2)

    # Statistical fidelity: role / action / hour-of-day distributions
    def field_counter(rows: list[dict], field: str) -> Counter:
        return Counter(str(r.get(field, "")) for r in rows)

    golden_logs = [
        g["audit_log"]
        for g in golden
        if "audit_log" in g
        and (g.get("seed_conditions", {}).get("violation_type") or g.get("violation", {}).get("violation_type")) in scope
    ]
    if not golden_logs:
        golden_logs = [g["audit_log"] for g in golden if "audit_log" in g]
    deviations: list[float] = []
    for field in ("role", "action", "system"):
        g_c = field_counter(golden_logs, field)
        s_c = field_counter(audit_logs, field)
        # max absolute probability deviation
        keys = set(g_c) | set(s_c)
        n_g = sum(g_c.values()) or 1
        n_s = sum(s_c.values()) or 1
        max_dev = 0.0
        for k in keys:
            max_dev = max(max_dev, abs(g_c[k] / n_g - s_c[k] / n_s))
        deviations.append(max_dev * 100)
        _ = _kl(g_c, s_c)  # computed for future reporting

    max_dev_pct = round(max(deviations) if deviations else 100.0, 2)
    # statistical_fidelity_score = 100 - max deviation
    stat_score = round(max(0.0, 100.0 - max_dev_pct), 2)

    status = "pass" if label_score >= 90 and stat_score >= 70 else ("warn" if label_score >= 75 else "fail")
    return {
        "label_fidelity_score": label_score,
        "statistical_fidelity_score": stat_score,
        "matched_seeds": matched,
        "total_seeds": len(golden),
        "classes_matched": class_hits,
        "classes_total": class_total,
        "max_field_deviation_pct": max_dev_pct,
        "status": status,
    }
