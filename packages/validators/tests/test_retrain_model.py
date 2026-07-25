from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import synthcompliance_validators.retrain_model as retrain_model
from synthcompliance_validators.retrain_model import (
    MAX_QA_HISTORY_ROWS,
    append_qa_history,
    load_latest_retrain_model_snapshot,
    load_qa_history,
    run_llm_finetune,
)


def _qa(n: int) -> list[dict]:
    return [
        {
            "qa_id": f"QA-{i}",
            "question": f"Which logs show violation {i}?",
            "answer": f"log_{i} — some explanation",
            "evidence_log_ids": [f"log_{i}"],
            "grounding": "high",
        }
        for i in range(n)
    ]


def test_qa_history_grows_and_caps(tmp_path, monkeypatch):
    monkeypatch.setattr(retrain_model, "MAX_QA_HISTORY_ROWS", 5)
    checkpoint_dir = tmp_path / "checkpoints"

    append_qa_history(checkpoint_dir, _qa(3))
    rows = append_qa_history(checkpoint_dir, _qa(4))

    assert len(rows) == 5  # 3 + 4 = 7, capped at 5, oldest trimmed
    loaded, _ = load_qa_history(checkpoint_dir), None
    assert len(loaded) == 5


def test_load_latest_retrain_model_snapshot_none_when_missing(tmp_path):
    assert load_latest_retrain_model_snapshot(tmp_path / "checkpoints") is None


def _fake_subprocess_run(*args, **kwargs):
    class Result:
        returncode = 0

    return Result()


def test_run_llm_finetune_first_call_creates_active_candidate(tmp_path, monkeypatch):
    checkpoint_dir = tmp_path / "checkpoints"
    monkeypatch.setattr(retrain_model.subprocess, "run", _fake_subprocess_run)
    monkeypatch.setattr(
        retrain_model,
        "_evaluate_checkpoint",
        lambda model_path, eval_qa: {"citation_accuracy": 0.8, "groundedness": 0.7},
    )

    train_qa = _qa(10)
    eval_qa = _qa(3)
    meta = run_llm_finetune(train_qa, eval_qa, base_model="fake/model", checkpoint_dir=checkpoint_dir, iters=1)

    assert meta["model_version"] == 1
    assert meta["status"] == "active"  # no prior checkpoint to beat -> always promoted
    assert meta["cumulative_train_size"] == 10
    assert meta["eval"] == {"citation_accuracy": 0.8, "groundedness": 0.7}
    assert len(meta["history"]) == 1

    snapshot = load_latest_retrain_model_snapshot(checkpoint_dir)
    assert snapshot == meta


def test_run_llm_finetune_second_call_rejects_on_regression(tmp_path, monkeypatch):
    checkpoint_dir = tmp_path / "checkpoints"
    monkeypatch.setattr(retrain_model.subprocess, "run", _fake_subprocess_run)

    evals = iter([{"citation_accuracy": 0.8, "groundedness": 0.7}, {"citation_accuracy": 0.4, "groundedness": 0.3}])
    monkeypatch.setattr(retrain_model, "_evaluate_checkpoint", lambda model_path, eval_qa: next(evals))

    run_llm_finetune(_qa(10), _qa(3), base_model="fake/model", checkpoint_dir=checkpoint_dir, iters=1)
    second = run_llm_finetune(_qa(5), _qa(3), base_model="fake/model", checkpoint_dir=checkpoint_dir, iters=1)

    assert second["model_version"] == 2
    assert second["status"] == "rejected"  # eval regressed vs the active v1
    assert second["cumulative_train_size"] == 15
    assert len(second["history"]) == 2
