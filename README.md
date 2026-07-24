# SynthCompliance Dashboard

GPU-native agentic synthetic compliance data platform for NVIDIA Track C (Synthetic Data Generation).

The dashboard reads JSON/JSONL from `public/data/` (polled every ~9s). The Python pipeline writes there atomically via the FastAPI job runner.

## Quick start

```bash
# 1. Python backend (Terminal 1)
pip install -e packages/taxonomy -e packages/validators -e packages/generators -e packages/agents -r services/api/requirements.txt
npm run dev:api

# 2. Dashboard (Terminal 2)
npm install
npm run dev
```

Open http://localhost:5173 — see **[docs/DEMO.md](./docs/DEMO.md)** for the full judge demo script.

## Architecture

| Layer | Path |
|-------|------|
| Dashboard (Vite + React) | `src/` |
| FastAPI + SSE jobs | `services/api/` |
| 4 agents | `packages/agents/` |
| Generators + Nemotron provider | `packages/generators/` |
| 5 validators + TSTR + golden fidelity | `packages/validators/` |
| SOX+GDPR taxonomy + golden set | `packages/taxonomy/` |
| Optional: DistilBERT/DeBERTa TSTR comparison (H100/Slurm, out-of-band) | `cluster/` — see [cluster/README.md](./cluster/README.md) |

## Output contract

Four files the UI polls (plus optional manifest):

```
public/data/audit_logs.jsonl
public/data/violations.jsonl
public/data/qa_pairs.jsonl
public/data/validation_report.json   # includes golden_set_fidelity + tstr_metrics
```

See **[DATA_CONTRACT.md](./DATA_CONTRACT.md)** for field-level specs.

## Scripts

```bash
npm run dev:api      # FastAPI on :8000
npm run golden       # Regenerate packages/taxonomy/golden/
npm run build        # Production build
npm run lint         # oxlint
```

## Testing

```bash
cd packages/agents && python -m pytest tests/ -v
```

## Docker

```bash
cd infra/docker && cp .env.example .env && docker compose up --build
```

## Nemotron

`log_id`, `timestamp`, and taxonomy fields (`violation_id`/`control_id`/`severity`/`violation_type`) are
always deterministic — they're referential keys other rows depend on. Everything that reads as *content*
(`user_id`/`role`, `resource`/`system`, `action`, `outcome`, `sensitivity`, violation `explanation`) is
written by an LLM when a provider is configured, with a deterministic fallback per batch on failure. With
no provider configured, generation still runs end-to-end, but those content fields fall back to randomly
assigned deterministic values instead of LLM-written ones — the dashboard's "Fields LLM-generated" KPI
shows 0 in that case, honestly.

Set `NVIDIA_API_KEY` for the NVIDIA Build API, or `USE_SELF_HOSTED=true` + `NIM_BASE_URL` for a self-hosted
NIM — this also covers a local Ollama instance, since Ollama serves an OpenAI-compatible API on
`:11434/v1` and needs no code changes, just `NIM_BASE_URL=http://localhost:11434/v1` (or
`http://host.docker.internal:11434/v1` from inside Docker) and `NEMOTRON_MODEL=<a pulled model>`.
