# Cluster training runbook — TSTR transformers

Trains **DistilBERT** (`distilbert-base-uncased`, 66M) and **DeBERTa-v3-base**
(`microsoft/deberta-v3-base`, 184M) on 100k synthetic audit logs and feeds the
recall numbers back into the dashboard's TSTR panel as a 4-way comparison
(rule / LogisticRegression / DistilBERT / DeBERTa).

The dashboard API **never imports torch**. Training runs out-of-band on an H100
as two Slurm jobs; they write `transformer_metrics.json` + checkpoints to team
Lustre, you `rsync` those back into `public/data/checkpoints/`, and the live
pipeline folds them into `tstr_metrics` at report-build time.

## Leakage-safe split (mentor-proofing)

Taxonomy splits cleanly into SOX (8 financial-control violation types) and GDPR
(8 privacy violation types), with **no shared violation types**. Train packs are
SOX-only; eval is held-out GDPR. A model that lifts recall on GDPR after seeing
only SOX patterns demonstrates genuine cross-pack transfer, not memorisation of
the deterministic generator's templates. The strict-split LogisticRegression +
rule baseline are recomputed on the **same** split so `recall_lift_vs_lr` is
apples-to-apples.

## On the cluster (from the SynthCompliance repo root on the login node)

```bash
export IAG_TEAM=iag-team4
export TEAM_SCRATCH=/lustre/fs01/hackathons/teams/$IAG_TEAM
# push the repo + sbatch scripts up (one-time, or keep a team clone in sync)
rsync -avP --exclude node_modules --exclude dist ./ \
  <axis_hash>@ssh.axisapps.io:$TEAM_SCRATCH/SynthCompliance/

ssh <axis_hash>@ssh.axisapps.io
cd $TEAM_SCRATCH/SynthCompliance
iag-submit cluster/tstr-distilbert.sbatch   # ~5 min on 1x H100
iag-submit cluster/tstr-deberta.sbatch      # ~15-20 min on 1x H100
iag-status        # watch;CANCEL" $J (or iag-cancel <jobid>)
```

Outputs land in `$TEAM_SCRATCH/synth-checkpoints/`: a per-model `model/` dir
and a single accumulating `transformer_metrics.json` (both jobs write into it).

## Bring it back to the dashboard

On your laptop, from the repo root:

```bash
rsync -avP <axis_hash>@ssh.axisapps.io:$TEAM_SCRATCH/synth-checkpoints/ \
  public/data/checkpoints/
export SYNTH_TRANSFORMER_DIR=public/data/checkpoints   # the live API reads this
npm run dev:api   # terminal 1
npm run dev       # terminal 2
```

The Proof tab now renders the rule / LR / DistilBERT / DeBERTa bars with the
best model ringed, and the headline "Recall lift" is best-model vs the strict
rule baseline.

## Tune knobs (env, all optional)

| Env | Default | Meaning |
|---|---|---|
| `SYNTH_N_TRAIN` | `80000` | rows generated for the SOX training corpus |
| `SYNTH_N_EVAL` | `20000` | rows generated for the GDPR held-out eval |
| `SYNTH_EPOCHS` | `2` | transformer fine-tune epochs |
| `SYNTH_BATCH` | `32` (distilbert) / `16` (deberta) | train batch size |
| `SYNTH_REPO_ROOT` | `$TEAM_SCRATCH/SynthCompliance` | where the repo lives on Lustre |
| `CKPT_DIR` | `$TEAM_SCRATCH/synth-checkpoints` | checkpoint + metrics output |
| `HF_HOME` | per-user cache on Lustre | avoids no-internet compute nodes |

For a quick smoke test before the full 100k run, override the counts:

```bash
SYNTH_N_TRAIN=2000 SYNTH_N_EVAL=1000 SYNTH_EPOCHS=1 iag-submit cluster/tstr-distilbert.sbatch
```

Note: at very small `n_train` the transformer will **underfit and underperform
LR** (we confirmed `recall=0.00` at 2k/1-epoch/CPU vs `lr=0.50`). That's expected
and is precisely the mentor's point — the bigger model only pays off at scale.
On the H100 at 80k/2-epochs you should see it clearly clear the LR bar.