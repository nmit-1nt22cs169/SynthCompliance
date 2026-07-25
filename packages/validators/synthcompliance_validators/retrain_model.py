"""LoRA fine-tuning for the retrain-target model (the Copilot rephrase backend) — offline, mirrors
tstr_transformer.py's "GPU/training work happens out-of-band, the live API only ever reads a JSON
result back" pattern, one level up: LoRA instead of a classifier head. Uses mlx-lm, so this module
should never be imported by the live FastAPI process — only by scripts/finetune_retrain_model.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

EventCb = Callable[[dict[str, Any]], None]

# Bounds retrain cost as accumulated Q&A history grows across the life of a deployment — each row
# here is a full training example (heavier per-row than an audit-log row), so the cap is smaller
# than tstr.py's MAX_TRAINING_HISTORY_ROWS.
MAX_QA_HISTORY_ROWS = 5_000
MAX_META_HISTORY_ENTRIES = 20
HISTORY_FILENAME = "retrain_qa_history.jsonl"
META_FILENAME = "retrain_model_meta.json"


def _emit(cb: EventCb | None, event: dict[str, Any]) -> None:
    if cb:
        cb(event)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def load_qa_history(checkpoint_dir: Path | str) -> list[dict[str, Any]]:
    """Every qa_pair ever accumulated for retrain-model training, oldest first."""
    path = Path(checkpoint_dir) / HISTORY_FILENAME
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def append_qa_history(checkpoint_dir: Path | str, qa_pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append this run's qa_pairs to persisted history, capped at MAX_QA_HISTORY_ROWS (oldest
    trimmed first) — same policy as tstr.py's append_training_history. Returns the cumulative set."""
    prev = load_qa_history(checkpoint_dir)
    all_rows = prev + qa_pairs
    if len(all_rows) > MAX_QA_HISTORY_ROWS:
        all_rows = all_rows[-MAX_QA_HISTORY_ROWS:]
    _write_jsonl_atomic(Path(checkpoint_dir) / HISTORY_FILENAME, all_rows)
    return all_rows


def load_latest_retrain_model_snapshot(checkpoint_dir: Path | str) -> dict[str, Any] | None:
    """Full retrain_model_meta.json (model_version, eval, status, history, ...), or None if no
    checkpoint has ever been trained."""
    meta_path = Path(checkpoint_dir) / META_FILENAME
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_retrain_model_meta(checkpoint_dir: Path | str, meta: dict[str, Any]) -> None:
    _write_json_atomic(Path(checkpoint_dir) / META_FILENAME, meta)


def _qa_to_training_example(qa: dict[str, Any]) -> dict[str, str]:
    """mlx_lm's CompletionsDataset format (verified against the installed mlx-lm's
    tuner/datasets.py: a sample is routed to CompletionsDataset when it has "prompt"+"completion"
    keys) — maps directly onto qa_pairs.jsonl's existing question/answer fields, no reshaping."""
    return {"prompt": qa["question"], "completion": qa["answer"]}


def _ensure_hf_snapshot_complete(base_model: str) -> None:
    """mlx_lm.fuse resolves a HF repo id via snapshot_download(..., local_files_only=True) — if
    the initial download (during `mlx_lm.lora --train`, which uses its own fetch path) left the
    local snapshot missing even non-essential files (observed in practice: .gitattributes/
    README.md), that offline-only resolution fails permanently with IncompleteSnapshotError,
    for every subsequent run, not just the first. One real (non-mocked, non-local-path) network
    call here — a no-op if the snapshot's already complete — avoids that bug outright. Skipped
    for local checkpoint directories, which aren't HF repo ids."""
    if Path(base_model).exists():
        return
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(base_model, local_files_only=False)
    except Exception:
        pass  # best-effort — if this fails, the subsequent fuse call will surface the real error


def _write_mlx_dataset(data_dir: Path, train_qa: list[dict[str, Any]], eval_qa: list[dict[str, Any]]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "train.jsonl").write_text(
        "\n".join(json.dumps(_qa_to_training_example(qa), ensure_ascii=False) for qa in train_qa) + "\n",
        encoding="utf-8",
    )
    # mlx_lm.lora requires valid.jsonl whenever --train is passed (it always validates).
    (data_dir / "valid.jsonl").write_text(
        "\n".join(json.dumps(_qa_to_training_example(qa), ensure_ascii=False) for qa in eval_qa) + "\n",
        encoding="utf-8",
    )


def _evaluate_checkpoint(model_path: str, eval_qa: list[dict[str, Any]]) -> dict[str, Any]:
    """Citation accuracy (does the fused model's answer still surface the right log_id) and
    groundedness (word-overlap with the real explanation) — scored via mlx_lm's in-process
    generate(), not a served HTTP call, since spinning up mlx_lm.server just to score would be
    pure overhead here. Heavy import deliberately deferred into this function: this whole module
    must never be imported by the live FastAPI process."""
    from mlx_lm import generate, load

    model, tokenizer = load(model_path)

    hits = 0
    grounded = 0
    for qa in eval_qa:
        try:
            response = generate(model, tokenizer, prompt=qa["question"], max_tokens=200, verbose=False)
        except Exception:
            response = ""
        evidence_ids = qa.get("evidence_log_ids", [])
        if evidence_ids and all(eid in response for eid in evidence_ids):
            hits += 1
        answer_words = set(qa["answer"].lower().split())
        response_words = set(response.lower().split())
        overlap = len(answer_words & response_words) / max(len(answer_words), 1)
        if overlap >= 0.3:
            grounded += 1

    n = max(len(eval_qa), 1)
    return {"citation_accuracy": round(hits / n, 4), "groundedness": round(grounded / n, 4)}


def run_llm_finetune(
    train_qa: list[dict[str, Any]],
    eval_qa: list[dict[str, Any]],
    *,
    base_model: str,
    checkpoint_dir: Path | str,
    iters: int = 200,
    batch_size: int = 4,
    on_event: EventCb | None = None,
) -> dict[str, Any]:
    """Trains a LoRA adapter on the accumulated Q&A history, fuses it into a standalone checkpoint,
    evaluates it, and only promotes ("active") if it beats the currently active checkpoint —
    mirrors tstr.py's "only retrain fires on regression" pattern, inverted to gate *promotion*.
    """
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    prev_meta = load_latest_retrain_model_snapshot(checkpoint_dir)
    model_version = int(prev_meta.get("model_version", 0)) + 1 if prev_meta else 1

    cumulative_qa = append_qa_history(checkpoint_dir, train_qa)

    adapter_path = checkpoint_dir / f"adapters_v{model_version}"
    fused_path = checkpoint_dir / f"fused_v{model_version}"

    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        _write_mlx_dataset(data_dir, cumulative_qa, eval_qa)

        _emit(on_event, {"stage": "training", "message": f"LoRA training v{model_version} on {len(cumulative_qa)} examples"})
        subprocess.run(
            [
                "python", "-m", "mlx_lm", "lora",
                "--model", base_model,
                "--train",
                "--data", str(data_dir),
                "--adapter-path", str(adapter_path),
                "--iters", str(iters),
                "--batch-size", str(batch_size),
            ],
            check=True,
        )

    _ensure_hf_snapshot_complete(base_model)
    _emit(on_event, {"stage": "fusing", "message": "Fusing LoRA adapter into base weights"})
    subprocess.run(
        [
            "python", "-m", "mlx_lm", "fuse",
            "--model", base_model,
            "--adapter-path", str(adapter_path),
            "--save-path", str(fused_path),
        ],
        check=True,
    )

    _emit(on_event, {"stage": "evaluating", "message": "Scoring fused checkpoint"})
    eval_after = _evaluate_checkpoint(str(fused_path), eval_qa)

    prev_eval = (prev_meta or {}).get("eval")
    improved = prev_eval is None or (
        eval_after["citation_accuracy"] + eval_after["groundedness"]
        >= prev_eval["citation_accuracy"] + prev_eval["groundedness"]
    )
    status = "active" if improved else "rejected"

    history = list((prev_meta or {}).get("history", []))
    entry = {
        "model_version": model_version,
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cumulative_train_size": len(cumulative_qa),
        "eval": eval_after,
        "status": status,
    }
    history.append(entry)
    if len(history) > MAX_META_HISTORY_ENTRIES:
        history = history[-MAX_META_HISTORY_ENTRIES:]

    meta = {
        **entry,
        "checkpoint_path": str(fused_path),
        "base_model": base_model,
        "history": history,
    }
    write_retrain_model_meta(checkpoint_dir, meta)
    _emit(on_event, {"stage": "done", "message": f"v{model_version} {status} — {eval_after}"})
    return meta
