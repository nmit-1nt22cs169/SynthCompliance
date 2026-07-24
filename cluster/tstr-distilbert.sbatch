#!/bin/bash -l
#SBATCH --job-name=iag-tstr-distilbert
#SBATCH --partition=primary
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:30:00
#SBATCH --output=slurm-tstr-distilbert-%j.out

# DistilBERT fine-tune on 100k synthetic SOX audit logs, leakage-safe eval on
# held-out GDPR pack. Trains in ~5 min on an H100. Emits transformer_metrics.json
# + checkpoint to team Lustre; rsync both back to <repo>/public/data/checkpoints
# so the live dashboard shows the 4-way recall comparison.
#
# Run from the SynthCompliance repo on the login node:
#   iag-submit cluster/tstr-distilbert.sbatch

set -euo pipefail
umask 0007

# --- team storage (mirrors python-venv-job.sbatch) ---
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
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-not set}"
nvidia-smi -L
echo

# --- venv (uv, cached on Lustre) ---
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

# --- locate the SynthCompliance repo (cluster clone or shared team copy) ---
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

# --- pre-fetch weights to HF_HOME so no-internet compute nodes still work ---
python3 - <<'PY'
from transformers import AutoTokenizer, AutoModelForSequenceClassification
for m in ("distilbert-base-uncased",):
    AutoTokenizer.from_pretrained(m)
    AutoModelForSequenceClassification.from_pretrained(m, num_labels=2)
print("pre-fetch ok:", m)
PY

# --- train ---
python3 "${REPO_ROOT}/scripts/train_transformers.py" \
    --train-pack SOX --eval-pack GDPR \
    --n-train ${SYNTH_N_TRAIN:-80000} --n-eval ${SYNTH_N_EVAL:-20000} \
    --models distilbert-base-uncased \
    --epochs ${SYNTH_EPOCHS:-2} --batch-size ${SYNTH_BATCH:-32} --max-len 64 \
    --out "$CKPT_DIR"

echo
echo "=== DONE ==="
echo "Checkpoint + transformer_metrics.json written to: ${CKPT_DIR}"
echo "To surface in the dashboard, rsync back to your laptop:"
echo "  rsync -avP ${CKPT_DIR}/ <laptop>:<repo>/public/data/checkpoints/"
echo "Then set SYNTH_TRANSFORMER_DIR=<repo>/public/data/checkpoints when running the live API."