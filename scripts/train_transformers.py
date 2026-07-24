"""Cluster entrypoint: leakage-safe transformer TSTR at scale.

Trains DistilBERT and DeBERTa-v3-base on synthetic SOX audit-logs and evaluates
on a held-out GDPR pack (no shared violation types between train and eval). Also
re-runs the rule baseline + LogisticRegression on the SAME strict split so the
`recall_lift_vs_lr` reported by the transformer is an apples-to-apples comparison
against the existing scorer, not the in-distribution LR from the live pipeline.

Run on a GPU node (see samples/bert-tstr.sbatch in the Hackathon_Cluster repo):

    python scripts/train_transformers.py \\
        --train-pack SOX --eval-pack GDPR \\
        --n-train 80000 --n-eval 20000 \\
        --out /lustre/fs01/hackathons/teams/iag-team4/.iag/$USER/checkpoints

Outputs `<out>/transformer_metrics.json` (read back by the live pipeline) plus a
`<out>/<model>/model` checkpoint per trained model. Set HF_HOME to your
team-staged Hugging Face cache if the compute nodes have no outbound internet.
"""

from __future__ import annotations

import argparse
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
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from synthcompliance_generators.corpus import generate_corpus
from synthcompliance_generators.scenario_engine import EVAL_TARGETS, TRAIN_TARGETS, ScenarioEngine
from synthcompliance_validators.tstr import run_tstr
from synthcompliance_validators.tstr_transformer import run_tstr_transformer, write_transformer_metrics

# DistilBERT vs DeBERTa-v3-base. DeBERTa is ~3x heavier; the point is to show
# mentor that more capacity buys (or doesn't) more cross-pack recall.
MODEL_CHOICES = ("distilbert-base-uncased", "microsoft/deberta-v3-base")


def _build_corpus(*, pack: str, n_logs: int, mode: str, seed: str):
    """Generate a single-pack corpus. control_classes filter to the pack's types."""
    engine = ScenarioEngine(
        packs=[pack],
        control_classes=None,
        scenario_mix=TRAIN_TARGETS if mode == "train" else EVAL_TARGETS,
        n_logs=n_logs,
        industry="financial_services",
        seed=seed,
        mode=mode,
    )
    plan = engine.compose_plan()
    plan["engine"] = engine
    return generate_corpus(plan, engine), engine


def _labels(corpus, logs):
    return [1 if corpus["scenario_labels"].get(r["log_id"]) == "violation" else 0 for r in logs]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-pack", default="SOX")
    ap.add_argument("--eval-pack", default="GDPR")
    ap.add_argument("--n-train", type=int, default=80000)
    ap.add_argument("--n-eval", type=int, default=20000)
    ap.add_argument("--out", default=str(ROOT / "public" / "data" / "checkpoints"))
    ap.add_argument("--models", nargs="+", default=list(MODEL_CHOICES))
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--max-len", type=int, default=64)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--no-fp16", action="store_true")
    ap.add_argument("--infer-only", action="store_true", help="skip training, load existing checkpoints")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[train_transformers] train_pack={args.train_pack} n={args.n_train}  "
          f"eval_pack={args.eval_pack} n={args.n_eval}", flush=True)

    (train_corpus, _), (eval_corpus, _) = (
        _build_corpus(pack=args.train_pack, n_logs=args.n_train, mode="train", seed=f"train-{args.train_pack}"),
        _build_corpus(pack=args.eval_pack, n_logs=args.n_eval, mode="eval", seed=f"eval-{args.eval_pack}"),
    )
    train_logs, eval_logs = train_corpus["audit_logs"], eval_corpus["audit_logs"]
    train_labels, eval_labels = _labels(train_corpus, train_logs), _labels(eval_corpus, eval_logs)

    print(f"[train_transformers] train_violation_rate={sum(train_labels)/len(train_labels):.4f} "
          f"eval_violation_rate={sum(eval_labels)/len(eval_labels):.4f}", flush=True)

    # Strict-split LR + rules (apples-to-apples vs the transformers on this split).
    lr_metrics = run_tstr(train_logs, train_labels, eval_logs, eval_labels)
    lr_strict_recall = lr_metrics["synthetic_trained_rare_recall"]
    rule_strict_recall = lr_metrics["baseline_rare_recall"]
    print(f"[train_transformers] strict-split  rule_recall={rule_strict_recall:.4f} "
          f"lr_recall={lr_strict_recall:.4f}", flush=True)

    shared_kwargs = dict(
        epochs=args.epochs,
        batch_size=args.batch_size,
        max_len=args.max_len,
        lr=args.lr,
        fp16=not args.no_fp16,
        train_pack_label=args.train_pack,
        eval_pack_label=args.eval_pack,
    )

    for model_name in args.models:
        ckpt_dir = out / model_name.replace("/", "_")
        mode = "infer" if args.infer_only else "train"
        print(f"[train_transformers] {mode} {model_name} -> {ckpt_dir}", flush=True)
        metrics = run_tstr_transformer(
            train_logs, train_labels, eval_logs, eval_labels,
            model_name=model_name,
            checkpoint_dir=ckpt_dir,
            **shared_kwargs,
        )
        # fill lift-vs-LR using the strict-split LR recall, since the live
        # pipeline's LR ran on a different (in-distribution) eval set.
        metrics["transformer_recall_lift_vs_lr"] = round(
            metrics["transformer_rare_recall"] - lr_strict_recall, 4
        )
        metrics["lr_strict_rare_recall"] = round(lr_strict_recall, 4)
        metrics["rule_strict_rare_recall"] = round(rule_strict_recall, 4)
        metrics["lr_strict_recall_lift_vs_rule"] = round(lr_strict_recall - rule_strict_recall, 4)
        print(f"[train_transformers] {model_name}  recall={metrics['transformer_rare_recall']:.4f} "
              f"lift_vs_rule={metrics['transformer_recall_lift_vs_rule']:.4f} "
              f"lift_vs_lr={metrics['transformer_recall_lift_vs_lr']:.4f}", flush=True)
        write_transformer_metrics(out, metrics)

    print(f"[train_transformers] wrote {out/'transformer_metrics.json'}", flush=True)
    print(json.dumps(json.loads((out / "transformer_metrics.json").read_text()), indent=2), flush=True)


if __name__ == "__main__":
    main()