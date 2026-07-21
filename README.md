# SynthCompliance Dashboard

A dashboard for visualizing synthetic compliance data produced by the 5-stage
generation pipeline (Policy Templates → Event Generator → Scenario Composer →
Regulation Annotator → NeMo Curator) and the validators that check its output.

The UI does no computation of its own — it only reads and renders whatever
JSON/JSONL files are sitting in `public/data/`. That's the whole contract.

## Quick start

```bash
npm install

# Real pipeline data (starts empty — see "How data flows" below)
npm run dev

# Or develop against a bundled mock dataset instead
npm run dev:mock1
npm run dev
```

## How data flows

The app fetches four files at runtime, on a poll every ~9 seconds
(`src/hooks/useDashboardData.ts` / `src/lib/dataLoader.ts`):

```
public/data/audit_logs.jsonl
public/data/violations.jsonl
public/data/qa_pairs.jsonl
public/data/validation_report.json
```

Because this is a plain runtime `fetch`, not a build-time import, **whatever
files are in `public/data/` when the browser polls is what renders** — no
rebuild needed. That gives two ways to get data in front of the UI:

### 1. Real pipeline output (`npm run dev`)

`public/data/` starts empty (just a `.gitkeep`). Once the pipeline writes its
four output files into that directory, the dashboard picks them up on its
next poll automatically. This is the live path — see
[DATA_CONTRACT.md](./DATA_CONTRACT.md) for the exact format the pipeline
needs to produce.

### 2. Mock data for local UI development

```
mockData/
  mockData_1/   ← current dataset (500 audit logs, 150 violations, 100 QA pairs)
  mockData_2/   ← empty, ready for a different fixture
  mockData_3/   ← empty, ready for a different fixture
```

Each folder holds the same four files as the contract above. Running:

```bash
npm run dev:mock1   # or dev:mock2 / dev:mock3
```

copies that folder's files into `public/data/`, then run `npm run dev` (or
leave a dev server already running — the next poll picks the new files up).
This is copy-only: it doesn't launch the server itself, so you can swap
datasets without restarting Vite.

`mockData/mockData_1/` can be regenerated deterministically with
`node scripts/generate-data.mjs`.

## For pipeline/validator developers

If you're building the generator or validators and need to know the exact
file names, fields, types, and enums the UI expects — including what a
"flagged row" looks like for each validator — read
**[DATA_CONTRACT.md](./DATA_CONTRACT.md)**. That's the single source of
truth for the output format; matching it is all that's required to make the
real pipeline show up in this dashboard with zero UI changes.

## Other scripts

```bash
npm run build     # tsc -b && vite build
npm run lint      # oxlint
npm run preview   # preview a production build
```
