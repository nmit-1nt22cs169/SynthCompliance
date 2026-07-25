from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from synthcompliance_validators.duplicate_check import check_duplicates


def _row(log_id: str, timestamp: str) -> dict:
    return {
        "log_id": log_id,
        "timestamp": timestamp,
        "user_id": "u_1001",
        "action": "READ",
        "resource": "iam-core/config/policy",
        "outcome": "success",
        "role": "engineer",
        "system": "iam-core",
    }


def test_same_routine_action_on_different_days_is_not_a_duplicate():
    logs = [
        _row("log_1", "2026-07-01T09:00:00Z"),
        _row("log_2", "2026-07-02T09:00:00Z"),
        _row("log_3", "2026-07-03T09:00:00Z"),
    ]
    result = check_duplicates(logs)
    assert result["rows_flagged"] == 0
    assert result["flagged"] == []


def test_near_identical_rows_seconds_apart_are_flagged_as_duplicates():
    logs = [
        _row("log_1", "2026-07-01T09:00:00Z"),
        _row("log_2", "2026-07-01T09:00:20Z"),
    ]
    result = check_duplicates(logs)
    assert result["rows_flagged"] == 1
    assert result["flagged"][0]["duplicate_of"] == "log_1"
    assert result["flagged"][0]["log_id"] == "log_2"


def test_rows_just_outside_the_time_window_are_not_flagged():
    logs = [
        _row("log_1", "2026-07-01T09:00:00Z"),
        _row("log_2", "2026-07-01T09:06:00Z"),  # 6 min apart, default window is 5 min
    ]
    result = check_duplicates(logs)
    assert result["rows_flagged"] == 0


def test_malformed_timestamp_does_not_crash_and_is_not_flagged():
    logs = [
        _row("log_1", "not-a-timestamp"),
        _row("log_2", "2026-07-01T09:00:20Z"),
    ]
    result = check_duplicates(logs)
    assert result["rows_flagged"] == 0
