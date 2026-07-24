"""Generate data/seeds/ — demo fallback that passes validators.

Default 200 records for the fast dashboard demo. Pass --n-logs (or --scale) for
a larger corpus, e.g. the mentor-requested 100k run:

    python scripts/generate_seed.py --n-logs 100000
    python scripts/generate_seed.py --scale 100k   # 100000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT / "packages" / "taxonomy",
    ROOT / "packages" / "validators",
    ROOT / "packages" / "generators",
    ROOT / "packages" / "agents",
):
    sys.path.insert(0, str(p))

from synthcompliance_agents.pipeline import PipelineOrchestrator  # noqa: E402
from synthcompliance_taxonomy.controls import VIOLATION_TYPES  # noqa: E402

_SCALE = {"k": 1000, "m": 1_000_000}


def _parse_scale(s: str) -> int:
    s = s.strip().lower()
    mult = 1
    if s and s[-1] in _SCALE:
        mult = _SCALE[s[-1]]
        s = s[:-1]
    return int(float(s) * mult)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-logs", type=int, default=200, help="record count (default 200)")
    ap.add_argument("--scale", type=_parse_scale, default=None, help="e.g. 100k, 1m (overrides --n-logs)")
    args = ap.parse_args()
    n_logs = args.scale if args.scale is not None else args.n_logs

    out = ROOT / "data" / "seeds"
    out.mkdir(parents=True, exist_ok=True)
    orch = PipelineOrchestrator(out)
    result = orch.run(
        packs=["SOX", "GDPR"],
        control_classes=list(VIOLATION_TYPES),
        scenario_mix={
            "normal": 0.60,
            "suspicious": 0.15,
            "violation": 0.20,
            "false_positive": 0.05,
        },
        n_logs=n_logs,
        industry="financial_services",
    )
    print(json.dumps(result.get("counts"), indent=2))
    gf = result.get("report", {}).get("golden_set_fidelity", {})
    print("golden_set_fidelity:", json.dumps(gf, indent=2))
    print("seed written to", out)


if __name__ == "__main__":
    main()
