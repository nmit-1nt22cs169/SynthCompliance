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

### Instant demo (no API)

```bash
npm run dev:mock1 && npm run dev
```

Or load the pre-built seed: **Pipeline → Load 200-record Seed**.

## Architecture

| Layer | Path |
|-------|------|
| Dashboard (Vite + React) | `src/` |
| FastAPI + SSE jobs | `services/api/` |
| 4 agents | `packages/agents/` |
| Generators + Nemotron provider | `packages/generators/` |
| 5 validators + TSTR + golden fidelity | `packages/validators/` |
| SOX+GDPR taxonomy + golden set | `packages/taxonomy/` |
| 200-record fallback | `data/seeds/` |

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
npm run seed         # Regenerate data/seeds/ (200 records)
npm run golden       # Regenerate packages/taxonomy/golden/
npm run build        # Production build
npm run lint         # oxlint
```

## Docker

```bash
cd infra/docker && cp .env.example .env && docker compose up --build
```

## Nemotron (optional)

Set `NVIDIA_API_KEY` for NVIDIA Build API polish, or `USE_SELF_HOSTED=true` + `NIM_BASE_URL` for self-hosted NIM. Offline deterministic generation works without keys.
