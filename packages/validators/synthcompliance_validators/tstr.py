"""TSTR: Train on Synthetic, Test on Real(istic) — logistic regression rare-class recall."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline

FEATURE_KEYS = ("action", "role", "sensitivity", "system", "outcome")
# Bounds retrain cost as history grows across the life of a demo/deployment —
# oldest rows are trimmed first once this cap is hit.
MAX_TRAINING_HISTORY_ROWS = 20_000
HISTORY_FILENAME = "tstr_training_history.jsonl"
MODEL_FILENAME = "tstr_model.joblib"
META_FILENAME = "tstr_model_meta.json"
# Bounds how many past retrain snapshots tstr_model_meta.json keeps for the dashboard's
# retrain-trend chart — oldest trimmed first, same policy as MAX_TRAINING_HISTORY_ROWS.
MAX_META_HISTORY_ENTRIES = 20


def _row_features(row: dict[str, Any]) -> dict[str, Any]:
    feats: dict[str, Any] = {k: str(row.get(k, "unknown")) for k in FEATURE_KEYS}
    ts = str(row.get("timestamp", ""))
    hour = 12
    if "T" in ts and len(ts) >= 13:
        try:
            hour = int(ts[11:13])
        except ValueError:
            hour = 12
    feats["hour"] = hour
    feats["is_denied"] = 1 if row.get("outcome") == "denied" else 0
    return feats


def _build_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("vec", DictVectorizer(sparse=False)),
            ("clf", LogisticRegression(max_iter=800, class_weight="balanced", solver="lbfgs")),
        ]
    )


def _baseline_rules(rows: list[dict[str, Any]]) -> np.ndarray:
    """Manual triage rules — realistic-ratio ops without synthetic oversampling."""
    preds = []
    for r in rows:
        flagged = (
            r.get("outcome") == "denied"
            or (
                r.get("sensitivity") == "critical"
                and str(r.get("action")) in ("DELETE", "EXPORT")
            )
            or (
                str(r.get("role")) in ("contractor", "admin")
                and str(r.get("action")) in ("APPROVE", "UPDATE")
            )
        )
        preds.append(1 if flagged else 0)
    return np.array(preds)


def run_tstr(
    train_logs: list[dict[str, Any]],
    train_labels: list[int],
    eval_logs: list[dict[str, Any]],
    eval_labels: list[int],
) -> dict[str, Any]:
    """
    Baseline = rule-based manual triage on realistic-ratio eval set.
    Synthetic-trained = LR with class_weight=balanced on full oversampled train set.
    """
    if len(train_logs) < 10 or len(eval_logs) < 5:
        return {
            "baseline_rare_recall": 0.0,
            "synthetic_trained_rare_recall": 0.0,
            "recall_lift": 0.0,
            "train_size": len(train_logs),
            "eval_size": len(eval_logs),
            "eval_violation_rate": 0.0,
            "status": "skipped",
            "notes": "insufficient samples",
        }

    X_train = [_row_features(r) for r in train_logs]
    X_eval = [_row_features(r) for r in eval_logs]
    y_train = np.array(train_labels)
    y_eval = np.array(eval_labels)
    eval_rate = float(y_eval.mean()) if len(y_eval) else 0.008

    baseline_preds = _baseline_rules(eval_logs)
    baseline_recall = float(recall_score(y_eval, baseline_preds, zero_division=0)) if y_eval.sum() else 0.0

    synth_pipe = _build_pipeline()
    synth_pipe.fit(X_train, y_train)
    synth_preds = synth_pipe.predict(X_eval)
    synth_recall = float(recall_score(y_eval, synth_preds, zero_division=0)) if y_eval.sum() else 0.0

    return {
        "baseline_rare_recall": round(baseline_recall, 4),
        "synthetic_trained_rare_recall": round(synth_recall, 4),
        "recall_lift": round(synth_recall - baseline_recall, 4),
        "train_size": len(train_logs),
        "eval_size": len(eval_logs),
        "eval_violation_rate": round(eval_rate, 4),
        "train_violation_rate": round(float(y_train.mean()), 4),
        "status": "pass" if synth_recall > baseline_recall else "warn",
        "model": "sklearn.linear_model.LogisticRegression",
        "baseline_model": "manual_triage_rules",
    }


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


def load_training_history(checkpoint_dir: Path | str) -> tuple[list[dict[str, Any]], list[int]]:
    """Read every (row, label) pair persisted by prior retrains, oldest first."""
    path = Path(checkpoint_dir) / HISTORY_FILENAME
    if not path.exists():
        return [], []
    rows: list[dict[str, Any]] = []
    labels: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        rows.append(entry["row"])
        labels.append(int(entry["label"]))
    return rows, labels


def append_training_history(
    checkpoint_dir: Path | str,
    rows: list[dict[str, Any]],
    labels: list[int],
) -> tuple[list[dict[str, Any]], list[int]]:
    """Append this run's training rows to persisted history, capped to the most recent
    MAX_TRAINING_HISTORY_ROWS (oldest trimmed first). Returns the resulting cumulative set."""
    prev_rows, prev_labels = load_training_history(checkpoint_dir)
    all_rows = prev_rows + rows
    all_labels = prev_labels + labels
    if len(all_rows) > MAX_TRAINING_HISTORY_ROWS:
        all_rows = all_rows[-MAX_TRAINING_HISTORY_ROWS:]
        all_labels = all_labels[-MAX_TRAINING_HISTORY_ROWS:]

    path = Path(checkpoint_dir) / HISTORY_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for row, label in zip(all_rows, all_labels):
                f.write(json.dumps({"row": row, "label": label}, ensure_ascii=False) + "\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
    return all_rows, all_labels


def _evaluate(pipe: Pipeline, X_eval: list[dict[str, Any]], y_eval: np.ndarray) -> dict[str, Any]:
    """Confusion matrix + precision/recall/F1/accuracy for one fitted pipeline on one eval set.
    `labels=[0, 1]` forces a stable 2x2 shape even if a class is entirely absent from y_eval."""
    preds = pipe.predict(X_eval)
    tn, fp, fn, tp = confusion_matrix(y_eval, preds, labels=[0, 1]).ravel()
    return {
        "confusion_matrix": {"tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn)},
        "metrics": {
            "precision": round(float(precision_score(y_eval, preds, zero_division=0)), 4),
            "recall": round(float(recall_score(y_eval, preds, zero_division=0)), 4),
            "f1": round(float(f1_score(y_eval, preds, zero_division=0)), 4),
            "accuracy": round(float(accuracy_score(y_eval, preds)), 4),
        },
    }


def load_latest_retrain_snapshot(checkpoint_dir: Path | str) -> dict[str, Any] | None:
    """Read the full tstr_model_meta.json (model_version, confusion_matrix_after, metrics_after,
    history, ...) from the most recent retrain, if any — lets the dashboard keep showing the
    persisted model's last-known state on a run where retraining didn't fire this time, instead
    of the confusion-matrix panel just disappearing the moment recall holds steady for one run."""
    meta_path = Path(checkpoint_dir) / META_FILENAME
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_retrain_history(checkpoint_dir: Path | str) -> list[dict[str, Any]]:
    """Read just the rolling retrain-snapshot history list — used for the trend chart."""
    snapshot = load_latest_retrain_snapshot(checkpoint_dir)
    return snapshot.get("history", []) if snapshot else []


def retrain_persisted_model(
    checkpoint_dir: Path | str,
    train_logs: list[dict[str, Any]],
    train_labels: list[int],
    eval_logs: list[dict[str, Any]],
    eval_labels: list[int],
) -> dict[str, Any]:
    """Persist this run's training rows to the on-disk history, refit LogisticRegression on the
    full accumulated set (not just this run), and checkpoint the result.

    Logistic regression's loss is convex, so `warm_start` only affects solver iteration count,
    not the fitted result for a given dataset — the thing that actually makes this "learn" over
    time is the growing accumulated training set, not carrying over prior coefficients.

    Captures a before/after comparison: "before" is the *previous* checkpoint (if any),
    evaluated on this run's eval set — not last run's ephemeral run_tstr() model — so the diff
    reflects model change, not eval-data drift. None on the very first-ever retrain, since
    there's no prior persisted model to compare against.
    """
    checkpoint_dir = Path(checkpoint_dir)
    X_eval = [_row_features(r) for r in eval_logs]
    y_eval = np.array(eval_labels)

    model_path = checkpoint_dir / MODEL_FILENAME
    before: dict[str, Any] | None = None
    if model_path.exists():
        try:
            old_pipe = joblib.load(model_path)
            before = _evaluate(old_pipe, X_eval, y_eval)
        except Exception:
            before = None

    cumulative_rows, cumulative_labels = append_training_history(checkpoint_dir, train_logs, train_labels)

    meta_path = checkpoint_dir / META_FILENAME
    prev_meta: dict[str, Any] = {}
    if meta_path.exists():
        try:
            prev_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            prev_meta = {}
    model_version = int(prev_meta.get("model_version", 0)) + 1

    pipe = _build_pipeline()
    X_train = [_row_features(r) for r in cumulative_rows]
    y_train = np.array(cumulative_labels)
    pipe.fit(X_train, y_train)
    after = _evaluate(pipe, X_eval, y_eval)

    joblib.dump(pipe, model_path)
    trained_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    history = list(prev_meta.get("history", []))
    history.append(
        {
            "model_version": model_version,
            "trained_at": trained_at,
            "cumulative_train_size": len(cumulative_rows),
            "metrics_after": after["metrics"],
        }
    )
    if len(history) > MAX_META_HISTORY_ENTRIES:
        history = history[-MAX_META_HISTORY_ENTRIES:]
    meta = {
        "model_version": model_version,
        "trained_at": trained_at,
        "cumulative_train_size": len(cumulative_rows),
        "confusion_matrix_after": after["confusion_matrix"],
        "metrics_after": after["metrics"],
        "history": history,
    }
    _write_json_atomic(meta_path, meta)

    return {
        "retrained": True,
        "model_version": model_version,
        "cumulative_train_size": len(cumulative_rows),
        "trained_at": trained_at,
        "post_retrain_recall": after["metrics"]["recall"],
        "confusion_matrix_before": before["confusion_matrix"] if before else None,
        "confusion_matrix_after": after["confusion_matrix"],
        "metrics_before": before["metrics"] if before else None,
        "metrics_after": after["metrics"],
        "retrain_history": history,
    }
