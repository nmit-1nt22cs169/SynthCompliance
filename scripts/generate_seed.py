"""Generate data/seeds/ — 200-record demo fallback that passes validators."""

from __future__ import annotations

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


def main() -> None:
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
        n_logs=200,
        industry="financial_services",
    )
    print(json.dumps(result.get("counts"), indent=2))
    gf = result.get("report", {}).get("golden_set_fidelity", {})
    print("golden_set_fidelity:", json.dumps(gf, indent=2))
    print("seed written to", out)


if __name__ == "__main__":
    main()
