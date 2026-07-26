# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SynthCompliance is a synthetic compliance-data pipeline with a live dashboard: a Python backend generates
realistic audit logs, SOX/GDPR violation records, and Q&A pairs, validates them, and proves (via TSTR —
Train Synthetic Test Real) that a model trained on the synthetic data beats a rule-based baseline. The
dashboard is a read-only viewer + pipeline trigger over four output files the backend writes.

## Commands

```bash
# Backend (Terminal 1)
pip install -e packages/taxonomy -e packages/validators -e packages/generators -e packages/agents -r services/api/requirements.txt
npm run dev:api          # FastAPI on :8000, SSE job streaming

# Frontend (Terminal 2)
npm install
npm run dev              # Vite on :5173, proxies /api -> :8000

npm run build             # tsc -b && vite build
npm run lint              # oxlint

# Python tests (per-package, pytest not pinned in any requirements file — install ad hoc)
cd packages/agents && python -m pytest tests/ -v

# Regenerate the golden reference set (packages/taxonomy/golden/, used by golden-fidelity scoring)
npm run golden

# Docker
cd infra/docker && cp .env.example .env && docker compose up --build
```

Nemotron (LLM) is optional but required for real generation quality — see "Deterministic vs. LLM" below.
Set `PRIVATE_API_KEY` for a hosted API (e.g. NVIDIA Build), or `USE_SELF_HOSTED=true` + `LOCAL_BASE_URL`
for a self-hosted NIM / local Ollama (Ollama serves an OpenAI-compatible API on `:11434/v1`, so it drops
straight into the self-hosted path with no code changes). Offline deterministic generation works without
any key, but only the structural fields get filled in — see below. `provider.py`'s `LLMProvider` is
generic across all of these; a second model slot (`RETRAIN_*` vars, `get_retrain_provider()`, gated by
the same `RETRAIN_MODEL` flag as the classifier retrain) reuses the same class for the retrain-target
model that rephrases Copilot answers (any LLM, not tied to a specific one). Fine-tuning that model is a
separate, Apple-Silicon-only path — `scripts/finetune_retrain_model.py` LoRA-tunes it via `mlx-lm` on
accumulated `qa_pairs.jsonl` history and is never imported by the live API; see "Persisted retraining" below.

## Architecture

### Monorepo layout

| Path | What |
|---|---|
| `src/` | Vite + React 19 dashboard, no router (tab state in `App.tsx`), no Tailwind/component library |
| `services/api/app/main.py` | FastAPI gateway — job runner (background thread + in-memory `_jobs`/`_job_events`) + SSE + Copilot endpoint |
| `packages/agents/synthcompliance_agents/pipeline.py` | The 4 agents + `PipelineOrchestrator` — this is the file to read first for backend changes |
| `packages/generators/` | `corpus.py` (deterministic scaffold), `scenario_engine.py` (scenario mix -> counts), `provider.py` (Nemotron/OpenAI-compatible client), `io_atomic.py` (atomic file writes) |
| `packages/validators/` | 5 structural validators + `tstr.py` (sklearn LogisticRegression, incl. persisted-model retrain) + `tstr_transformer.py` (offline DistilBERT/DeBERTa scorer, cluster-only) + `golden_fidelity.py` (scores against `packages/taxonomy/golden/`) + `retrain_model.py` (LoRA fine-tune for the retrain-target model, `mlx-lm`-only) + `report.py` (assembles `validation_report.json`) |
| `packages/taxonomy/` | Static SOX+GDPR taxonomy, control IDs, `roster.py` (50-user roster, 200-asset list) |

### Data flow: files, not sockets (except job progress)

The dashboard polls four files under `public/data/` every ~9s (2s while a job is active):
`audit_logs.jsonl`, `violations.jsonl`, `qa_pairs.jsonl`, `validation_report.json`. `src/types.ts` is the
source of truth for their shape; see `DATA_CONTRACT.md` for field-level specs and the atomic-write
rationale. **Never** partially write these — `io_atomic.py`'s `write_dataset_bundle` writes each file via
temp-file-then-rename, and it's called exactly once per run, at the very end of `PipelineOrchestrator.run()`.
Job *progress* (not output data) streams live over SSE from `GET /api/jobs/{job_id}/events` — that endpoint
replays the **entire** buffered event history from the start on every new connection (not just new events),
which is what lets the frontend resume watching a job across a page refresh (see `PipelineTab.tsx`'s
`localStorage`-backed resume effect).

### Pipeline execution order

`PipelineOrchestrator.run()` wires four agents in sequence: `ScenarioComposerAgent` (decides scenario-mix
counts) -> `LogGeneratorAgent` (scaffold + LLM content) -> `ValidatorRepairAgent` (validates, repairs up to
3 iterations) -> `TSTRCopilotAgent` (trains the TSTR logistic regression, and separately answers Copilot
queries). Each stage's `duration_ms` in `pipeline_stages` is measured for real by the orchestrator (or,
for Validator/Repair Loop, inside `ValidatorRepairAgent` itself) — there is no fixed/hardcoded stage timing
anywhere; if you add a new stage, time it the same way rather than guessing a constant.

### Deterministic vs. LLM-generated fields — the boundary matters

`LogGeneratorAgent` splits fields into two groups by **cardinality**, not by "is it text":

- **Always deterministic** (referential keys / taxonomy ground-truth other rows depend on): `log_id`,
  `timestamp` (including SOX quarter-end date logic), and for violations `violation_id`/`control_id`/
  `severity`/`violation_type`. Never hand these to an LLM — `violations`/`qa_pairs` reference `log_id`
  directly, and repair/validation logic assumes these are taxonomy-correct.
- **LLM-written when a provider is configured** (`user_id`/`role`, `resource`/`system`, `action`, `outcome`,
  `sensitivity`, violation `explanation`): batched calls with a deterministic fallback per batch on failure.
  `user_id`/`resource` are picked from a small per-log candidate shortlist (never invented freely) so
  roster/asset referential integrity always holds; `role`/`system` are then derived from whichever
  candidate won, never asked of the LLM directly — **always resolve against the specific candidate object
  offered, not a global id->object map** (`ASSET_LIST` has 200 entries but only 168 unique `resource`
  strings, so a global map can silently resolve to the wrong asset).
- Some fields are further **forced by business logic** even when a provider is available — e.g. every
  violation's `outcome` must stay `"success"` (that's what makes it one), `late_dsar`/
  `breach_notification_late` force a specific `action`+`resource` tied to a day/hour count encoded in the
  resource string. These forced sets are computed once per run and threaded through every batch loop.
- Batch sizes and `max_tokens` for these calls are tuned empirically, not guessed — the configured model
  spends real token budget on internal reasoning before its JSON answer, so bigger batches with the default
  budget silently truncate (`finish_reason: "length"`) and the batch's fallback silently kicks in. If you
  add a new LLM-generated field or grow a batch, re-verify against a real provider rather than assuming
  the existing budget scales.
- `dataset_targets.llm_fields` / `dataset_actual.llm_fields` in the report reflect how many fields were
  *eligible* vs. *actually written* by the LLM this run — computed unconditionally (even with no provider
  configured) so the dashboard KPI is honest about "0 written" vs. "nothing was eligible."

### Persisted retraining (two independent models, both gated by `RETRAIN_MODEL=true`)

- **Classifier**: when a run's recall doesn't improve on the prior run, `PipelineOrchestrator.run()` calls
  `tstr.py`'s `retrain_persisted_model()`, which refits the LogisticRegression on the *cumulative* on-disk
  training history (not just this run) and checkpoints it under `public/data/checkpoints/`. This runs
  in-process — it's just sklearn — synchronously as part of the pipeline job.
- **Retrain-target model** (rephrases Copilot answers in `TSTRCopilotAgent.answer_with_rephrase`): on the
  same regression trigger, `main.py`'s `start_job` launches `scripts/finetune_retrain_model.py` as a
  genuinely separate OS subprocess (own job bus, `POST /api/retrain-model/start` to trigger manually,
  `GET /api/retrain-model/jobs/{id}/events` to watch it, `GET /api/retrain-model/status` for the latest
  snapshot) — it LoRA-fine-tunes via `mlx-lm`, which is Apple-Silicon-only and must never be imported by
  the live API process. A checkpoint is only promoted (`status: "active"`) if it beats the previously
  active one on citation accuracy + groundedness; otherwise it's `"rejected"` and the rule-based answer
  keeps being used.

### Frontend state patterns

- **All 6 tabs are always mounted**; `App.tsx` toggles visibility with `display: none/block`, not
  conditional rendering — this was a deliberate fix for state (wizard fields, in-flight job log, Copilot
  results) getting wiped on every tab switch. Don't reintroduce conditional `{activeTab === 'x' && <Tab/>}`
  mounting.
- **Cross-tab jump-and-highlight**: `App.tsx` holds a `jumpTarget` (`{ table, id }`) settable from any tab;
  `DataTab` consumes it by seeding that table's search box with the id (which naturally filters to just
  that row) and applying a `.highlighted` style — reuse `onJump`/`jumpToRow` rather than inventing a new
  cross-tab mechanism.
- Job state survives a full page refresh via `localStorage` (`PipelineTab`'s `JOB_STORAGE_KEY`): it stores
  `{job_id, startedAt}`, and on mount checks `GET /api/jobs/{id}` before resubscribing — this guard exists
  because the SSE endpoint hangs open indefinitely (never closes) on an unknown `job_id` rather than
  erroring, e.g. after a backend restart.
- No charting library anywhere (donut, bar charts, Gantt, line chart are all hand-rolled CSS/SVG) and no
  Tailwind — styling is one file, `src/styles/global.css`, using CSS custom properties defined in `:root`
  for color/spacing/radius/type scale. Reuse those tokens (`--space-*`, `--radius-*`, `--text-*`, `--green
  /--amber/--red` + `-text`/`-dark` variants) rather than hardcoding new literals — several past bugs in
  this codebase were exactly that (a hex color or pixel value duplicated instead of referencing the token,
  drifting out of sync later).
- Duration values are formatted with `src/lib/format.ts`'s `formatDuration` (ms below 1s, `X.Xs` below a
  minute, `Xm Ys` above) — never render a raw `duration_ms` directly.

### Dev server caveat

`npm run dev:api` runs with `--reload`. Editing a backend file while a job's SSE connection is open makes
uvicorn hang in "Waiting for connections to close" (the open stream never closes on its own) before it
force-restarts, which kills that in-flight job. Expect this if you edit backend code while testing a live
run.
