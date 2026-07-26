"""Cross-run adaptive feedback: persists per-violation-type weights that bias the next run's
scenario mix toward types seen before (mild reinforcement) and brand-new types (stronger boost),
so repeated runs gradually cover more of the taxonomy without manual tuning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def update_feedback_state(
    out_dir: Path | str,
    *,
    run_id: str,
    violation_types: list[str],
    label_counts: dict[str, int],
    previous_recall_lift: float,
    current_recall_lift: float,
    status: str,
    previous_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge this run's outcome into feedback_state.json and return the updated weights.

    New violation types get a 1.15x weight (first-seen boost); types already seen before get a
    smaller 1.05x nudge each time they recur. Weights only ever grow (floored at 1.0), so this is
    cumulative coverage pressure across runs, not a rolling average.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / "feedback_state.json"

    if previous_state is None and state_path.exists():
        previous_state = json.loads(state_path.read_text(encoding="utf-8"))

    state = {
        "seen_violation_types": list(previous_state.get("seen_violation_types", []) if previous_state else []),
        "violation_type_weights": dict(previous_state.get("violation_type_weights", {}) if previous_state else {}),
        "history": list(previous_state.get("history", []) if previous_state else []),
    }

    seen = set(state["seen_violation_types"])
    new_patterns = [v for v in violation_types if v not in seen]
    for v in new_patterns:
        seen.add(v)
        state["violation_type_weights"][v] = state["violation_type_weights"].get(v, 1.0) * 1.15

    for v in state["violation_type_weights"]:
        if v in violation_types:
            state["violation_type_weights"][v] = max(1.0, state["violation_type_weights"].get(v, 1.0) * 1.05)

    history_entry = {
        "run_id": run_id,
        "status": status,
        "violation_types": violation_types,
        "label_counts": label_counts,
        "previous_recall_lift": previous_recall_lift,
        "current_recall_lift": current_recall_lift,
        "improved": current_recall_lift >= previous_recall_lift,
    }
    state["history"].append(history_entry)
    state["seen_violation_types"] = sorted(seen)
    state["last_run_id"] = run_id
    state["last_recall_lift"] = current_recall_lift

    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "feedback_state": state,
        "new_violation_patterns": new_patterns,
        "next_violation_type_weights": state["violation_type_weights"],
        "history_entry": history_entry,
    }
