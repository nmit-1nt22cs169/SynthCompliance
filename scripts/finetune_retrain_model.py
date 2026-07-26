"""Standalone entrypoint for LoRA fine-tuning the retrain-target/Copilot model — mirrors
train_transformers.py's "runs out-of-band, not imported by the live API" pattern, one level up.

Run (after `pip install mlx-lm`, Apple Silicon only):

    python scripts/finetune_retrain_model.py \\
        --base-model mlx-community/Qwen2.5-7B-Instruct-4bit \\
        --out public/data/checkpoints/retrain

Outputs `<out>/retrain_model_meta.json` (read back by the live API — see
synthcompliance_validators.retrain_model.load_latest_retrain_model_snapshot) plus a fused model
checkpoint directory per trained version. Serve the resulting checkpoint with mlx-lm's own
OpenAI-compatible server, which the app's existing LLMProvider already knows how to talk to:

    python -m mlx_lm server --model <out>/fused_v1 --port 8090
    # then point RETRAIN_LOCAL_BASE_URL=http://localhost:8090/v1 at it
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

from synthcompliance_validators.retrain_model import run_llm_finetune  # noqa: E402


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-model", default="mlx-community/Qwen2.5-7B-Instruct-4bit")
    ap.add_argument("--qa-pairs", default=str(ROOT / "public" / "data" / "qa_pairs.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "public" / "data" / "checkpoints" / "retrain"))
    ap.add_argument("--iters", type=int, default=200)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--eval-holdout", type=int, default=10, help="qa_pairs held out for eval, not trained on")
    args = ap.parse_args()

    qa_path = Path(args.qa_pairs)
    if not qa_path.exists():
        raise SystemExit(f"{qa_path} not found — run the main pipeline at least once first")
    qa_pairs = _load_jsonl(qa_path)
    if len(qa_pairs) <= args.eval_holdout:
        raise SystemExit(f"Need more than {args.eval_holdout} qa_pairs to train (have {len(qa_pairs)})")

    eval_qa = qa_pairs[: args.eval_holdout]
    train_qa = qa_pairs[args.eval_holdout :]

    print(f"[finetune_retrain_model] base_model={args.base_model} train={len(train_qa)} eval={len(eval_qa)}", flush=True)

    def on_event(ev: dict) -> None:
        print(f"[finetune_retrain_model] {ev['stage']}: {ev['message']}", flush=True)

    meta = run_llm_finetune(
        train_qa,
        eval_qa,
        base_model=args.base_model,
        checkpoint_dir=Path(args.out),
        iters=args.iters,
        batch_size=args.batch_size,
        on_event=on_event,
    )
    print(json.dumps(meta, indent=2), flush=True)


if __name__ == "__main__":
    main()
