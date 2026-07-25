from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from synthcompliance_validators.tstr import (
    HISTORY_FILENAME,
    META_FILENAME,
    MODEL_FILENAME,
    load_training_history,
    retrain_persisted_model,
)


def _rows(n: int, violation_rate: float) -> tuple[list[dict], list[int]]:
    rows = []
    labels = []
    for i in range(n):
        label = 1 if (i % int(1 / violation_rate)) == 0 else 0
        rows.append(
            {
                "action": "DELETE" if label else "READ",
                "role": "admin" if label else "engineer",
                "sensitivity": "critical" if label else "low",
                "system": "ledger-svc",
                "outcome": "success",
                "timestamp": f"2026-01-01T{10 + (i % 10):02d}:00:00Z",
            }
        )
        labels.append(label)
    return rows, labels


def test_retrain_persisted_model_creates_checkpoint_and_grows_cumulative_size(tmp_path):
    checkpoint_dir = tmp_path / "checkpoints"
    train_rows, train_labels = _rows(40, 0.2)
    eval_rows, eval_labels = _rows(20, 0.2)

    first = retrain_persisted_model(checkpoint_dir, train_rows, train_labels, eval_rows, eval_labels)

    assert first["retrained"] is True
    assert first["model_version"] == 1
    assert first["cumulative_train_size"] == 40
    assert (checkpoint_dir / MODEL_FILENAME).exists()
    assert (checkpoint_dir / META_FILENAME).exists()
    assert (checkpoint_dir / HISTORY_FILENAME).exists()

    # First-ever retrain: no prior checkpoint, so nothing to diff "before" against.
    assert first["confusion_matrix_before"] is None
    assert first["metrics_before"] is None
    assert first["confusion_matrix_after"] is not None
    assert first["metrics_after"] is not None
    assert sum(first["confusion_matrix_after"].values()) == len(eval_rows)

    more_rows, more_labels = _rows(15, 0.2)
    second = retrain_persisted_model(checkpoint_dir, more_rows, more_labels, eval_rows, eval_labels)

    assert second["model_version"] == 2
    assert second["cumulative_train_size"] == 55

    # Second retrain: a checkpoint from the first retrain exists, so "before" is that model
    # evaluated on this run's eval set.
    assert second["confusion_matrix_before"] is not None
    assert sum(second["confusion_matrix_before"].values()) == len(eval_rows)
    assert second["metrics_before"] is not None

    history_rows, history_labels = load_training_history(checkpoint_dir)
    assert len(history_rows) == 55
    assert len(history_labels) == 55
