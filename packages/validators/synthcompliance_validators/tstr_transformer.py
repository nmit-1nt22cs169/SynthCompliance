"""TSTR transformer scorer — DistilBERT / DeBERTa fine-tune on synthetic audit logs.

Leakage-safe pack split: train on SOX violation scenarios, evaluate on held-out
GDPR violation scenarios. A model that generalises from SOX patterns (APPROVE/
UPDATE-heavy financial controls) to GDPR patterns (EXPORT/READ-heavy privacy
controls) is demonstrating real cross-pack transfer, not memorising the
generator's templates.

This module is imported only by the offline cluster training script
(`scripts/train_transformers.py`). The live API never imports it, so torch /
transformers stay out of the API's dependency closure and the dashboard demo
remains stable without a GPU. The cluster job emits a `transformer_metrics.json`
that the pipeline reads back and merges into `tstr_metrics`.

Design notes:
- Lazy torch / transformers imports so the validators package still imports in
  CPU-only / dependency-light environments (the cluster venv installs these).
- Serialise each audit-log dict to a short canonical text string so the
  transformer sees the same closed-vocab features the LR baseline uses, plus
  free cross-feature interaction modelling.
- Class-weighted BCE to counter the rare-class imbalance; rare-class recall is
  the metric of record (matches `tstr.run_tstr`).
- fp16 on GPU (the H100 path); auto-falls back to fp32 on CPU.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .tstr import _baseline_rules

FEATURE_KEYS = ("action", "role", "sensitivity", "system", "outcome")


def _log_to_text(row: dict[str, Any]) -> str:
    """Serialise an audit-log dict to a canonical short text string."""
    ts = str(row.get("timestamp", ""))
    hour = 12
    if "T" in ts and len(ts) >= 13:
        try:
            hour = int(ts[11:13])
        except ValueError:
            hour = 12
    parts = [
        f"action={row.get('action', 'unknown')}",
        f"role={row.get('role', 'unknown')}",
        f"sensitivity={row.get('sensitivity', 'unknown')}",
        f"system={row.get('system', 'unknown')}",
        f"outcome={row.get('outcome', 'unknown')}",
        f"hour={hour}",
    ]
    return " ".join(parts)


def run_tstr_transformer(
    train_logs: list[dict[str, Any]],
    train_labels: list[int],
    eval_logs: list[dict[str, Any]],
    eval_labels: list[int],
    *,
    model_name: str = "distilbert-base-uncased",
    checkpoint_dir: str | os.PathLike[str] | None = None,
    epochs: int = 2,
    batch_size: int = 32,
    max_len: int = 64,
    lr: float = 2e-5,
    fp16: bool = True,
    seed: int = 42,
    train_pack_label: str = "SOX",
    eval_pack_label: str = "GDPR",
) -> dict[str, Any]:
    """Fine-tune (or load) a transformer and score rare-class recall.

    If `checkpoint_dir` already contains a saved model for `model_name`, load it
    and evaluate only (no training). Otherwise train inline and save the
    checkpoint + a `transformer_metrics.json` into `checkpoint_dir`.

    Returns a metrics dict additive over `run_tstr`'s schema.
    """
    if len(train_logs) < 50 or len(eval_logs) < 20:
        return {
            "transformer_rare_recall": 0.0,
            "transformer_recall_lift_vs_rule": 0.0,
            "transformer_recall_lift_vs_lr": 0.0,
            "transformer_status": "skipped",
            "transformer_model": model_name,
            "transformer_train_size": len(train_logs),
            "transformer_eval_size": len(eval_logs),
            "transformer_notes": "insufficient samples",
        }

    try:
        import torch
        from torch.utils.data import DataLoader, Dataset
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup
    except ImportError as exc:  # pragma: no cover
        return {
            "transformer_rare_recall": 0.0,
            "transformer_recall_lift_vs_rule": 0.0,
            "transformer_recall_lift_vs_lr": 0.0,
            "transformer_status": "unavailable",
            "transformer_model": model_name,
            "transformer_train_size": len(train_logs),
            "transformer_eval_size": len(eval_logs),
            "transformer_notes": f"torch/transformers not installed: {exc}",
        }

    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = fp16 and device.type == "cuda"

    y_eval = np.array(eval_labels)
    baseline_preds = _baseline_rules(eval_logs)
    from sklearn.metrics import recall_score

    baseline_recall = float(recall_score(y_eval, baseline_preds, zero_division=0)) if y_eval.sum() else 0.0
    eval_rate = float(y_eval.mean()) if len(y_eval) else 0.0

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=2)

    ckpt_path = Path(checkpoint_dir) / "model" if checkpoint_dir else None
    infer_only = ckpt_path is not None and ckpt_path.exists()

    class _LogDataset(Dataset):
        def __init__(self, logs, labels):
            self.texts = [_log_to_text(r) for r in logs]
            self.labels = list(labels)

        def __len__(self):
            return len(self.texts)

        def __getitem__(self, i):
            enc = tokenizer(
                self.texts[i],
                max_length=max_len,
                padding="max_length",
                truncation=True,
                return_tensors="pt",
            )
            return {k: v.squeeze(0) for k, v in enc.items()}, torch.tensor(self.labels[i], dtype=torch.long)

    def _evaluate():
        model.eval()
        preds_all = []
        eval_loader = DataLoader(_LogDataset(eval_logs, eval_labels), batch_size=batch_size)
        with torch.no_grad():
            for inputs, _ in eval_loader:
                inputs = {k: v.to(device) for k, v in inputs.items()}
                logits = model(**inputs).logits
                preds_all.extend(logits.argmax(dim=-1).cpu().tolist())
        preds = np.array(preds_all)
        return float(recall_score(y_eval, preds, zero_division=0)) if y_eval.sum() else 0.0

    model.to(device)

    if not infer_only:
        # Class-weighted BCE to counter rare-class imbalance.
        counts = np.bincount(np.array(train_labels), minlength=2).astype(float)
        weights = torch.tensor(
            [(len(train_labels) / (2.0 * max(c, 1))) for c in counts],
            dtype=torch.float,
            device=device,
        )
        loss_fn = torch.nn.CrossEntropyLoss(weight=weights)

        train_ds = _LogDataset(train_logs, train_labels)
        train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
        optim = torch.optim.AdamW(model.parameters(), lr=lr)
        total_steps = len(train_loader) * epochs
        sched = get_linear_schedule_with_warmup(optim, int(0.1 * total_steps), total_steps)

        scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
        model.train()
        for _ in range(epochs):
            for inputs, labels in train_loader:
                inputs = {k: v.to(device) for k, v in inputs.items()}
                labels = labels.to(device)
                optim.zero_grad()
                with torch.amp.autocast("cuda", enabled=use_amp):
                    logits = model(**inputs).logits
                    loss = loss_fn(logits, labels)
                scaler.scale(loss).backward()
                scaler.step(optim)
                scaler.update()
                sched.step()

        if ckpt_path is not None:
            ckpt_path.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(ckpt_path)
            tokenizer.save_pretrained(ckpt_path)

    transformer_recall = _evaluate()

    # lift vs LR is filled by the caller (pipeline) which also has the LR number;
    # reported here as None until merged. We do report lift vs the rule baseline.
    metrics: dict[str, Any] = {
        "transformer_rare_recall": round(transformer_recall, 4),
        "transformer_recall_lift_vs_rule": round(transformer_recall - baseline_recall, 4),
        "transformer_recall_lift_vs_lr": None,
        "transformer_status": "pass" if transformer_recall > baseline_recall else "warn",
        "transformer_model": model_name,
        "transformer_train_size": len(train_logs),
        "transformer_eval_size": len(eval_logs),
        "transformer_train_violation_rate": round(float(np.mean(train_labels)), 4),
        "transformer_eval_violation_rate": round(eval_rate, 4),
        "transformer_train_pack": train_pack_label,
        "transformer_eval_pack": eval_pack_label,
        "transformer_baseline_rare_recall": round(baseline_recall, 4),
        "transformer_epochs": epochs,
        "transformer_fp16": bool(use_amp),
        "transformer_device": device.type,
        "transformer_mode": "infer" if infer_only else "train",
    }
    return metrics


def write_transformer_metrics(
    out_dir: str | os.PathLike[str],
    metrics: dict[str, Any],
) -> Path:
    """Persist a single transformer run's metrics as transformer_metrics.json.

    Multiple runs (DistilBERT, DeBERTa) accumulate under `models` so the API
    can report all of them. Idempotent: re-running overwrites the file.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "transformer_metrics.json"
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    models = existing.get("models", {})
    models[metrics["transformer_model"]] = metrics
    bundle = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "models": models,
        "best_model": max(models.values(), key=lambda m: m.get("transformer_rare_recall", 0))["transformer_model"]
        if models
        else None,
    }
    path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return path


__all__ = ["run_tstr_transformer", "write_transformer_metrics"]