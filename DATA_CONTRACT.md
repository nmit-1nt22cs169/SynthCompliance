# Data Contract

This is the exact output format the dashboard expects. Match this and the
real pipeline will render with **zero UI changes** — no code in this repo
needs to be touched to go from mock data to live data.

If anything here needs to change (new field, renamed enum, etc.), update
this file and `src/types.ts` in the same change so they never drift.

## Where files go

The UI fetches these four files, by these exact names, from this exact path,
at runtime (plain HTTP GET, not a build step):

```
public/data/audit_logs.jsonl
public/data/violations.jsonl
public/data/qa_pairs.jsonl
public/data/validation_report.json
```

`public/` is served as static file root by Vite in dev and by whatever
serves the production build — so writing/overwriting these four files on
disk at that path is the entire integration. There is no API, no upload
step, no message queue on the UI side.

**Open question for whoever owns deployment:** in production this repo is
built to static files and served by *something* (nginx, a CDN, a Node
static server, etc.). The pipeline needs write access to that server's
`data/` directory, or this needs a small API/proxy layer in front of the UI
instead of direct file writes. Not decided yet — flag this before go-live.

## Refresh behavior (important for how you write files)

- The UI polls all four files every **~9 seconds** and re-renders on
  success (`src/hooks/useDashboardData.ts`).
- All four files are fetched together (`Promise.all`). **If any one is
  missing or fails to parse, the whole refresh fails** — the UI shows an
  error banner and keeps displaying the last successfully loaded snapshot
  underneath it (it does not blank out).
- Implication: **write files atomically.** If you write a new
  `audit_logs.jsonl` while the poll is mid-read, or leave it half-written,
  that poll cycle errors. Recommended pattern: write to a temp file in the
  same directory, then `rename()` all four into place together. A rename is
  atomic; in-place partial writes are not.
- On first load (nothing in `public/data/` yet), all four fetches 404 and
  the UI shows "Failed to load dashboard data" — this is the expected
  resting state before the pipeline's first run completes, not a bug.

## File formats

`.jsonl` files: one JSON object per line, no trailing commas, no wrapping
array. `.json` file: a single JSON object.

---

### `audit_logs.jsonl`

One line per audit event.

```json
{"log_id":"log_9000","timestamp":"2026-07-15T09:00:20Z","user_id":"u_4410","action":"APPROVE","resource":"deploy/config/billing_worker","outcome":"success","role":"engineer","sensitivity":"critical","system":"deploy-pipeline"}
```

| Field | Type | Notes |
|---|---|---|
| `log_id` | string | Unique. Referenced by `violations[].log_id` and `qa_pairs[].evidence_log_ids[]` — those references must resolve to a real row here. |
| `timestamp` | string | **ISO 8601** (e.g. `2026-07-15T09:00:20Z`). Non-ISO formats will be flagged by the schema validator (see `validation_report.json` below). |
| `user_id` | string | |
| `action` | string | Free text, but should come from a consistent action vocabulary (e.g. `CREATE`, `UPDATE`, `DELETE`, `APPROVE`, `EXPORT`) — arbitrary/unrecognized codes get flagged. |
| `resource` | string | Path-like identifier of the thing acted on. |
| `outcome` | `"success"` \| `"denied"` | |
| `role` | string | e.g. `engineer`, `admin`, `support_agent`, `finance_analyst`, `privacy_officer`. |
| `sensitivity` | `"low"` \| `"medium"` \| `"high"` \| `"critical"` | |
| `system` | string | Source system name, e.g. `iam-core`, `crm-core`, `ledger-svc`. |

---

### `violations.jsonl`

One line per detected policy/control violation.

```json
{"violation_id":"V-1005","log_id":"log_9180","violation_type":"segregation_of_duties","control_id":"SOD-05","severity":"medium","explanation":"User u_9013 both created and approved the change to customer_pii/exports/22713, violating maker-checker separation."}
```

| Field | Type | Notes |
|---|---|---|
| `violation_id` | string | Unique. |
| `log_id` | string | Must match a `log_id` in `audit_logs.jsonl`. |
| `violation_type` | string | e.g. `segregation_of_duties`, `late_dsar`, `missing_approval`. Should map onto a fixed taxonomy — the label-alignment validator flags mismatches between this, `control_id`, and `severity`. |
| `control_id` | string | e.g. `SOD-05`, `PRIV-03`, `CHG-07`. |
| `severity` | `"critical"` \| `"high"` \| `"medium"` \| `"low"` | |
| `explanation` | string | Human-readable justification, shown as-is in the UI. |

---

### `qa_pairs.jsonl`

One line per generated Q&A pair used to spot-check grounding.

```json
{"qa_id":"QA-201","question":"Was the Q2 ledger close reviewed by someone other than the preparer?","answer":"No — the same user (u_1047) both created and approved the entry, a segregation-of-duties violation.","evidence_log_ids":["log_9931"],"grounding":"high"}
```

| Field | Type | Notes |
|---|---|---|
| `qa_id` | string | Unique. |
| `question` | string | |
| `answer` | string | |
| `evidence_log_ids` | string[] | Each entry must match a `log_id` in `audit_logs.jsonl`. |
| `grounding` | `"high"` \| `"medium"` \| `"low"` | How well the answer is supported by the cited evidence. |

---

### `validation_report.json`

A single object summarizing one pipeline run and its validator results.

```json
{
  "run_id": "run_2026_07_18_0431",
  "generated_at": "2026-07-18T09:45:11Z",
  "dataset_targets": {
    "audit_logs": 500,
    "violations": 150,
    "qa_pairs": 100,
    "investigation_summaries": 2
  },
  "dataset_actual": {
    "audit_logs": 500,
    "violations": 147,
    "qa_pairs": 100,
    "investigation_summaries": 2
  },
  "validators": {
    "schema_validity": {
      "target_pass_rate": 0.98,
      "actual_pass_rate": 0.994,
      "rows_checked": 500,
      "rows_failed": 3,
      "status": "pass",
      "flagged": [
        { "log_id": "log_9508", "field": "timestamp", "issue": "non-ISO8601 format" }
      ]
    },
    "pii_leakage": {
      "target_detections": 0,
      "actual_detections": 2,
      "rows_checked": 500,
      "status": "warn",
      "flagged": [
        { "log_id": "log_9701", "entity": "EMAIL", "value_redacted": "j***@●●●●.com" }
      ]
    },
    "duplicate_check": {
      "target_max_rate": 0.02,
      "actual_rate": 0.008,
      "rows_checked": 500,
      "rows_flagged": 4,
      "status": "pass",
      "flagged": [
        { "log_id": "log_9130", "duplicate_of": "log_9040", "similarity": 0.97 }
      ]
    },
    "label_alignment": {
      "target_pass_rate": 0.95,
      "actual_pass_rate": 0.961,
      "rows_checked": 147,
      "rows_failed": 6,
      "status": "pass",
      "flagged": [
        { "violation_id": "V-1029", "issue": "control_id does not match violation_type taxonomy" }
      ]
    },
    "scenario_coverage": {
      "normal": 302,
      "suspicious": 71,
      "violation": 104,
      "false_positive": 23
    }
  },
  "pipeline_stages": [
    { "stage": "Policy Templates", "status": "completed", "duration_ms": 1840 },
    { "stage": "Event Generator", "status": "completed", "duration_ms": 22110 },
    { "stage": "Scenario Composer", "status": "completed", "duration_ms": 15430 },
    { "stage": "Regulation Annotator", "status": "completed", "duration_ms": 9870 },
    { "stage": "NeMo Curator", "status": "completed", "duration_ms": 31220 },
    { "stage": "Output Datasets", "status": "completed", "duration_ms": 640 }
  ]
}
```

Top-level fields:

| Field | Type | Notes |
|---|---|---|
| `run_id` | string | Unique per pipeline run. |
| `generated_at` | string | ISO 8601 timestamp of when this report was produced. |
| `dataset_targets` | object | Intended row counts (all four counters required, even if `investigation_summaries` isn't a file the UI reads today). |
| `dataset_actual` | object | Actual row counts produced this run. Same four keys. |
| `validators` | object | Exactly the five keys below — no more, no fewer. |
| `pipeline_stages` | array | One entry per stage, **in execution order**. `status` is one of `"completed"` \| `"running"` \| `"failed"` \| `"skipped"`. |

`validators` — each of the four scored validators shares the same
`status: "pass" | "warn" | "fail"` and a `flagged` array of example rows
(cap this list to a reasonable sample, e.g. ≤20 — it's for spot-checking,
not a full dump):

| Validator | Required fields | `flagged` row shape |
|---|---|---|
| `schema_validity` | `target_pass_rate`, `actual_pass_rate`, `rows_checked`, `rows_failed`, `status` | `{ log_id, field, issue }` |
| `pii_leakage` | `target_detections`, `actual_detections`, `rows_checked`, `status` | `{ log_id, entity, value_redacted }` |
| `duplicate_check` | `target_max_rate`, `actual_rate`, `rows_checked`, `rows_flagged`, `status` | `{ log_id, duplicate_of, similarity }` |
| `label_alignment` | `target_pass_rate`, `actual_pass_rate`, `rows_checked`, `rows_failed`, `status` | `{ violation_id, issue }` |

`scenario_coverage` is the exception — no `status`/`flagged`, just four
counts (`normal`, `suspicious`, `violation`, `false_positive`) that should
sum to (approximately) `dataset_actual.audit_logs`.

## Source of truth

The TypeScript types the UI actually compiles against live in
[`src/types.ts`](./src/types.ts) — if this document and that file ever
disagree, `src/types.ts` wins and this document is out of date and should
be fixed.

## Reference implementation / examples

`scripts/generate-data.mjs` generates a full example dataset matching this
contract exactly (into `mockData/mockData_1/`) — useful as a working
reference if a snippet above is ambiguous. See the main
[README](./README.md) for how mock data plugs into local dev.
