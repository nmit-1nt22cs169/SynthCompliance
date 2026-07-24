"""FastAPI gateway — job runner + SSE + copilot."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

# Ensure packages are importable when run from repo root / docker
ROOT = Path(__file__).resolve().parents[3]
for p in (
    ROOT / "packages" / "taxonomy",
    ROOT / "packages" / "validators",
    ROOT / "packages" / "generators",
    ROOT / "packages" / "agents",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from synthcompliance_agents.pipeline import PipelineOrchestrator, TSTRCopilotAgent  # noqa: E402
from synthcompliance_taxonomy.controls import CONTROL_CLASSES, REGULATION_PACKS, TAXONOMY  # noqa: E402

DATA_DIR = Path(os.getenv("SYNTH_DATA_DIR", str(ROOT / "public" / "data")))

app = FastAPI(title="SynthCompliance API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job bus for SSE
_jobs: dict[str, dict[str, Any]] = {}
_job_events: dict[str, list[dict[str, Any]]] = {}
_job_lock = threading.Lock()


class JobRequest(BaseModel):
    packs: list[str] = Field(default_factory=lambda: ["SOX", "GDPR"])
    control_classes: list[str] | None = None
    scenario_mix: dict[str, float] | None = None
    n_logs: int = 200
    industry: str = "financial_services"


class CopilotRequest(BaseModel):
    query: str


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/taxonomy")
def taxonomy() -> dict[str, Any]:
    return {
        "packs": list(REGULATION_PACKS),
        "control_classes": list(CONTROL_CLASSES),
        "taxonomy": TAXONOMY,
    }


@app.post("/api/jobs")
def start_job(req: JobRequest) -> dict[str, Any]:
    import uuid

    job_id = f"job_{uuid.uuid4().hex[:10]}"
    with _job_lock:
        _jobs[job_id] = {"status": "queued", "job_id": job_id}
        _job_events[job_id] = [{"stage": "queued", "message": "Job queued"}]

    def worker() -> None:
        def on_event(ev: dict[str, Any]) -> None:
            with _job_lock:
                _job_events.setdefault(job_id, []).append(ev)
                _jobs[job_id] = {**_jobs.get(job_id, {}), **ev, "job_id": job_id}

        try:
            with _job_lock:
                _jobs[job_id]["status"] = "running"
            orch = PipelineOrchestrator(DATA_DIR)
            result = orch.run(
                packs=req.packs,
                control_classes=req.control_classes,
                scenario_mix=req.scenario_mix,
                n_logs=req.n_logs,
                industry=req.industry,
                on_event=on_event,
            )
            with _job_lock:
                _jobs[job_id] = {
                    "status": "completed",
                    "job_id": job_id,
                    "result": {
                        "run_id": result.get("run_id"),
                        "counts": result.get("counts"),
                        "mode": result.get("mode"),
                    },
                }
                _job_events[job_id].append({"stage": "complete", "message": "done"})
        except Exception as e:  # noqa: BLE001
            with _job_lock:
                _jobs[job_id] = {"status": "failed", "job_id": job_id, "error": str(e)}
                _job_events[job_id].append({"stage": "failed", "message": str(e)})

    threading.Thread(target=worker, daemon=True).start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with _job_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    async def gen():
        idx = 0
        while True:
            with _job_lock:
                events = list(_job_events.get(job_id, []))
                status = (_jobs.get(job_id) or {}).get("status")
            while idx < len(events):
                payload = json.dumps(events[idx])
                yield f"data: {payload}\n\n"
                idx += 1
            if status in ("completed", "failed") and idx >= len(events):
                yield f"data: {json.dumps({'stage': status, 'message': 'stream-end'})}\n\n"
                break
            await asyncio.sleep(0.35)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/copilot")
def copilot(req: CopilotRequest) -> dict[str, Any]:
    audit_logs = _load_jsonl(DATA_DIR / "audit_logs.jsonl")
    violations = _load_jsonl(DATA_DIR / "violations.jsonl")
    if not violations:
        raise HTTPException(400, "No corpus loaded — run a pipeline job first")
    agent = TSTRCopilotAgent()
    return agent.answer(req.query, audit_logs=audit_logs, violations=violations)


@app.get("/api/export.zip")
def export_bundle():
    import io
    import zipfile

    buf = io.BytesIO()
    names = [
        "audit_logs.jsonl",
        "violations.jsonl",
        "qa_pairs.jsonl",
        "validation_report.json",
        "dataset_manifest.json",
    ]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            path = DATA_DIR / name
            if path.exists():
                zf.write(path, arcname=name)
    buf.seek(0)
    from fastapi.responses import Response

    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=synthcompliance_export.zip"},
    )


def create_app() -> FastAPI:
    return app
