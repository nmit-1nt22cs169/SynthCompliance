#!/bin/bash -l
#SBATCH --job-name=iag-tstr-deberta
#SBATCH --partition=primary
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --time=01:00:00
#SBATCH --output=slurm-tstr-deberta-%j.out

# DeBERTa-v3-base fine-tune on 100k synthetic SOX audit logs, leakage-safe eval
# on held-out GDPR pack. Heavier than DistilBERT (~15-20 min on H100, 184M
# params) — the "serious model" weight the mentor asked for. Trains into the
# SAME checkpoint dir as the DistilBERT job so both bars land in one
# transformer_metrics.json for the dashboard's 4-way comparison.
#
# Submit AFTER the DistilBERT job (or before; order doesn't matter — the metrics
# file accumulates). Run from the SynthCompliance repo on the login node:
#   iag-submit cluster/tstr-deberta.sbatch

set -euo pipefail
umask 0007

TEAM="${IAG_TEAM:-}"
if [[ -z "$TEAM" ]]; then
    TEAM="$(id -Gn | tr ' ' '\n' | grep -E '^iag-team[0-9]+$' | head -n 1 || true)"
fi
if [[ -z "$TEAM" ]]; then
    echo "Could not detect team. Set IAG_TEAM=iag-team<N> before submitting." >&2
    exit 1
fi
TEAM_SCRATCH="${TEAM_SCRATCH:-/lustre/fs01/hackathons/teams/${TEAM}}"
RUNTIME_DIR="${TEAM_SCRATCH}/.iag/${USER:-user}"
VENV_DIR="${VENV_DIR:-${RUNTIME_DIR}/venvs/synth-transformer}"
HF_HOME="${HF_HOME:-${RUNTIME_DIR}/cache/hf}"
CKPT_DIR="${CKPT_DIR:-${TEAM_SCRATCH}/synth-checkpoints}"

mkdir -p "$RUNTIME_DIR" "$HF_HOME" "$CKPT_DIR"
chgrp "$TEAM" "$RUNTIME_DIR" 2>/dev/null || true
chmod 2770 "$RUNTIME_DIR" 2>/dev/null || true
export HF_HOME

echo "Host: $(hostname -f 2>/dev/null || hostname)"
echo "Job id: ${SLURM_JOB_ID}"
nvidia-smi -L
echo

export UV_CACHE_DIR="${RUNTIME_DIR}/cache/uv"
export PIP_CACHE_DIR="${RUNTIME_DIR}/cache/pip"
if [[ ! -d "$VENV_DIR" ]]; then
    module load uv
    uv venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
module load uv
uv pip install --upgrade pip
uv pip install torch transformers scikit-learn numpy "pillow>=10"

REPO_ROOT="${SYNTH_REPO_ROOT:-${TEAM_SCRATCH}/SynthCompliance}"
if [[ ! -d "$REPO_ROOT" ]]; then
    echo "Cloning SynthCompliance into ${REPO_ROOT}" >&2
    git clone https://github.com/boi-doingthings/SynthCompliance.git "$REPO_ROOT" || \
        git clone https://github.com/boi-doingthings/Hackathon_Cluster.git "$REPO_ROOT"
fi
uv pip install -e "${REPO_ROOT}/packages/taxonomy" \
    -e "${REPO_ROOT}/packages/validators" \
    -e "${REPO_ROOT}/packages/generators" \
    -e "${REPO_ROOT}/packages/agents"

# DeBERTa-v3 needs sentencepiece on some builds; harmless if unused.
uv pip install sentencepiece 2>/dev/null || true

python3 - <<'PY'
from transformers import AutoTokenizer, AutoModelForSequenceClassification
m = "microsoft/deberta-v3-base"
AutoTokenizer.from_pretrained(m)
AutoModelForSequenceClassification.from_pretrained(m, num_labels=2)
print("pre-fetch ok:", m)
PY

python3 "${REPO_ROOT}/scripts/train_transformers.py" \
    --train-pack SOX --eval-pack GDPR \
    --n-train ${SYNTH_N_TRAIN:-80000} --n-eval ${SYNTH_N_EVAL:-20000} \
    --models microsoft/deberta-v3-base \
    --epochs ${SYNTH_EPOCHS:-2} --batch-size ${SYNTH_BATCH:-16} --max-len 64 \
    --out "$CKPT_DIR"

echo
echo "=== DONE ==="
echo "transformer_metrics.json (now containing both models) at: ${CKPT_DIR}"
echo "rsync -avP ${CKPT_DIR}/ <laptop>:<repo>/public/data/checkpoints/"