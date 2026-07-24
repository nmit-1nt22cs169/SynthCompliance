"""TSTR: Train on Synthetic, Test on Real(istic) — logistic regression rare-class recall."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import recall_score
from sklearn.pipeline import Pipeline

FEATURE_KEYS = ("action", "role", "sensitivity", "system", "outcome")


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

    synth_pipe = Pipeline(
        [
            ("vec", DictVectorizer(sparse=False)),
            ("clf", LogisticRegression(max_iter=800, class_weight="balanced", solver="lbfgs")),
        ]
    )
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
