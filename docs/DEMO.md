# SynthCompliance — Demo Runbook

GPU-native agentic synthetic compliance data platform (NVIDIA Track C).

## Quick start (local, two terminals)

```bash
# Terminal 1 — API (writes to public/data/, SSE job stream)
pip install -e packages/taxonomy -e packages/validators -e packages/generators -e packages/agents -r services/api/requirements.txt
npm run dev:api

# Terminal 2 — Dashboard (polls public/data/ every 9s)
npm install
npm run dev
```

Open http://localhost:5173

## Demo seed fallback (no GPU / offline)

```bash
python scripts/generate_seed.py   # writes data/seeds/ (200 records, all validators pass)
# Or from UI: Pipeline → "Load 200-record Seed"
# Or API: POST /api/seed
```

Pre-loaded seed is copied to `public/data/` for instant dashboard render.

## 6-step judge demo script

1. **Pipeline** — SOX + GDPR, select SoD + Late DSAR + Access Lifecycle (or defaults), 500 logs, 20% violation mix → **Run Pipeline**
2. Watch SSE: composing → generating (count ticking) → validating → repairing → complete
3. **Validation** — 5 structural validators green + Golden-Set Fidelity 94%+
4. **Proof** — TSTR chart: baseline vs synthetic-trained rare-class recall lift
5. **Copilot** — *"Which logs show an SoD violation involving invoice approval?"* → cited log_ids + SOD-04
6. **Data** — Download export bundle → open raw JSONL for judges

Run twice back-to-back without code changes.

## Nemotron provider (env-switchable)

Copy `infra/docker/.env.example` → `.env`:

| Mode | Env |
|------|-----|
| NVIDIA Build API | `USE_SELF_HOSTED=false`, `NVIDIA_API_KEY=...` |
| Self-hosted NIM | `USE_SELF_HOSTED=true`, `NIM_BASE_URL=http://gpu-cluster:8000/v1` |

Offline deterministic generation works without any API key.

## Docker Compose

```bash
cd infra/docker
cp .env.example .env
docker compose up --build
```

## Monorepo layout

```
packages/taxonomy/     16 violation types, 70 control_ids (SOX 44 + GDPR 26)
packages/validators/   5 structural validators + golden fidelity + TSTR
packages/generators/   scenario engine + atomic writes
packages/agents/       4 agents (Composer, Generator, ValidatorRepair, TSTRCopilot)
services/api/          FastAPI + SSE
src/                   Vite React dashboard (existing UI, extended)
data/seeds/            200-record demo fallback
public/data/           Live output (dashboard contract)
```

## Output contract

See [DATA_CONTRACT.md](../DATA_CONTRACT.md). Additional top-level fields in `validation_report.json`:

- `golden_set_fidelity` — label + statistical fidelity scores
- `tstr_metrics` — logistic-regression TSTR proof
- `dataset_manifest.json` — job metadata (optional for UI poll)

## What's next (roadmap slide)

Auth/multi-tenancy, Kubernetes/Helm, S3/MinIO, pgvector RAG, DistilBERT fine-tune, Celery/PostgreSQL.
