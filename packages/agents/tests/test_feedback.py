from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from synthcompliance_agents.feedback import update_feedback_state


def test_feedback_state_detects_new_patterns_and_boosts_weights(tmp_path):
    prior_state = {
        "seen_violation_types": ["segregation_of_duties"],
        "violation_type_weights": {"segregation_of_duties": 1.0},
        "history": [],
    }

    result = update_feedback_state(
        tmp_path,
        run_id="run_2",
        violation_types=["segregation_of_duties", "late_dsar"],
        label_counts={"violation": 12, "normal": 88},
        previous_recall_lift=0.12,
        current_recall_lift=0.38,
        status="completed",
        previous_state=prior_state,
    )

    assert result["new_violation_patterns"] == ["late_dsar"]
    assert result["next_violation_type_weights"]["late_dsar"] > 1.0
    assert result["next_violation_type_weights"]["segregation_of_duties"] >= 1.0
    assert result["history_entry"]["label_counts"]["violation"] == 12
