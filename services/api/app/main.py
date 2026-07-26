"""FastAPI gateway — job runner + SSE + copilot."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

# Ensure packages are importable when run from repo root / docker
ROOT = Path(__file__).resolve().parents[3]

# docker-compose injects real container env vars directly (see infra/docker/docker-compose.yml),
# so this is a no-op there (load_dotenv never overrides an already-set var by default) — it only
# fills the gap for `npm run dev:api` run bare on a host, which otherwise never reads this file.
load_dotenv(ROOT / "infra" / "docker" / ".env")

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
from synthcompliance_generators.provider import get_provider, get_retrain_provider  # noqa: E402
from synthcompliance_taxonomy.controls import CONTROL_CLASSES, REGULATION_PACKS, TAXONOMY  # noqa: E402
# retrain_model.py itself never imports mlx-lm at module level (deferred inside the function that
# actually runs training/eval) — but the live API launches that work as a genuinely separate
# subprocess anyway (see _start_retrain_model_job below), never in-process, so this stays a
# lightweight, stdlib-only import regardless.
from synthcompliance_validators.retrain_model import load_latest_retrain_model_snapshot  # noqa: E402

DATA_DIR = Path(os.getenv("SYNTH_DATA_DIR", str(ROOT / "public" / "data")))


def _bool_env(name: str, default: bool = False) -> bool:
    """Matches provider.py's helper of the same name — no central config module in this repo,
    env vars are read ad hoc at point of use."""
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _check_reachable(base_url: str, api_key: str, timeout: float = 2.0) -> bool:
    """Any HTTP response — even an auth error — proves the network path is open; only a
    connection failure/timeout means the configured host is actually unreachable. This is the
    check that would have caught a misconfigured port (talking to the wrong service, or nothing
    at all) immediately instead of requiring a manual restart-and-inspect."""
    req = urllib.request.Request(f"{base_url.rstrip('/')}/models")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False

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

# Separate job bus for the (optional, RETRAIN_MODEL-gated) LLM fine-tune — its own lock/dicts
# since it can run far longer than the main pipeline and must never block it.
_retrain_model_jobs: dict[str, dict[str, Any]] = {}
_retrain_model_job_events: dict[str, list[dict[str, Any]]] = {}
_retrain_model_lock = threading.Lock()
RETRAIN_CHECKPOINT_DIR = DATA_DIR / "checkpoints" / "retrain"


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


@app.get("/api/config")
def config() -> dict[str, Any]:
    provider = get_provider()
    retrain_model_enabled = _bool_env("RETRAIN_MODEL", False)
    result: dict[str, Any] = {
        "provider": {
            "available": provider.available,
            "use_self_hosted": provider.use_self_hosted,
            "base_url": provider.base_url,
            "model": provider.model,
            "reachable": _check_reachable(provider.base_url, provider.api_key) if provider.available else False,
        },
        "retrain_model_enabled": retrain_model_enabled,
        "data_dir": str(DATA_DIR),
    }
    # Second model slot (the retrain-target/Copilot model — any LLM, not tied to a specific
    # one) — only pinged when RETRAIN_MODEL is on, since it's not expected to be configured
    # until that path is actually built.
    if retrain_model_enabled:
        retrain_provider = get_retrain_provider()
        result["retrain_provider"] = {
            "available": retrain_provider.available,
            "use_self_hosted": retrain_provider.use_self_hosted,
            "base_url": retrain_provider.base_url,
            "model": retrain_provider.model,
            "reachable": _check_reachable(retrain_provider.base_url, retrain_provider.api_key)
            if retrain_provider.available
            else False,
        }
    return result


def _start_retrain_model_job() -> str:
    """Launches scripts/finetune_retrain_model.py as a genuinely separate OS process — never
    in-process — so the live API's own process never imports mlx-lm/loads model weights, same
    principle as the existing transformer_metrics.json precedent (train_transformers.py runs
    out-of-band; the API only ever reads a JSON result back). Its own job bus, since a real LoRA
    pass can run far longer than the main pipeline and must never block it."""
    import uuid

    job_id = f"retrain_{uuid.uuid4().hex[:10]}"
    with _retrain_model_lock:
        _retrain_model_jobs[job_id] = {"status": "queued", "job_id": job_id}
        _retrain_model_job_events[job_id] = [{"stage": "queued", "message": "Retrain-model job queued"}]

    def emit(ev: dict[str, Any]) -> None:
        with _retrain_model_lock:
            _retrain_model_job_events.setdefault(job_id, []).append(ev)
            _retrain_model_jobs[job_id] = {**_retrain_model_jobs.get(job_id, {}), **ev, "job_id": job_id}

    def worker() -> None:
        try:
            with _retrain_model_lock:
                _retrain_model_jobs[job_id]["status"] = "running"
            base_model = os.getenv("RETRAIN_BASE_MODEL", "mlx-community/Qwen2.5-7B-Instruct-4bit")
            script = ROOT / "scripts" / "finetune_retrain_model.py"
            emit({"stage": "started", "message": f"Fine-tuning {base_model}"})
            proc = subprocess.Popen(
                [
                    sys.executable, str(script),
                    "--base-model", base_model,
                    "--out", str(RETRAIN_CHECKPOINT_DIR),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if line:
                    emit({"stage": "training", "message": line})
            returncode = proc.wait()
            if returncode != 0:
                raise RuntimeError(f"finetune_retrain_model.py exited with code {returncode}")
            with _retrain_model_lock:
                _retrain_model_jobs[job_id]["status"] = "completed"
            emit({"stage": "complete", "message": "done"})
        except Exception as e:  # noqa: BLE001
            with _retrain_model_lock:
                _retrain_model_jobs[job_id] = {"status": "failed", "job_id": job_id, "error": str(e)}
            emit({"stage": "failed", "message": str(e)})

    threading.Thread(target=worker, daemon=True).start()
    return job_id


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
            retrain_model_job_id = None
            improved = result.get("report", {}).get("feedback_loop", {}).get("improved")
            if _bool_env("RETRAIN_MODEL", False) and improved is False:
                retrain_model_job_id = _start_retrain_model_job()
            with _job_lock:
                _jobs[job_id] = {
                    "status": "completed",
                    "job_id": job_id,
                    "result": {
                        "run_id": result.get("run_id"),
                        "counts": result.get("counts"),
                        "mode": result.get("mode"),
                        "retrain_model_job_id": retrain_model_job_id,
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


@app.post("/api/retrain-model/start")
def start_retrain_model_job() -> dict[str, Any]:
    """Manual trigger — the same job the main pipeline can also kick off automatically on a
    regression when RETRAIN_MODEL=true (see start_job's worker)."""
    job_id = _start_retrain_model_job()
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/retrain-model/jobs/{job_id}")
def get_retrain_model_job(job_id: str) -> dict[str, Any]:
    with _retrain_model_lock:
        job = _retrain_model_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "retrain-model job not found")
    return job


@app.get("/api/retrain-model/jobs/{job_id}/events")
async def retrain_model_job_events(job_id: str) -> StreamingResponse:
    async def gen():
        idx = 0
        while True:
            with _retrain_model_lock:
                events = list(_retrain_model_job_events.get(job_id, []))
                status = (_retrain_model_jobs.get(job_id) or {}).get("status")
            while idx < len(events):
                payload = json.dumps(events[idx])
                yield f"data: {payload}\n\n"
                idx += 1
            if status in ("completed", "failed") and idx >= len(events):
                yield f"data: {json.dumps({'stage': status, 'message': 'stream-end'})}\n\n"
                break
            await asyncio.sleep(0.35)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/retrain-model/status")
def retrain_model_status() -> dict[str, Any]:
    snapshot = load_latest_retrain_model_snapshot(RETRAIN_CHECKPOINT_DIR)
    return {"snapshot": snapshot}


@app.post("/api/copilot")
def copilot(req: CopilotRequest) -> dict[str, Any]:
    audit_logs = _load_jsonl(DATA_DIR / "audit_logs.jsonl")
    violations = _load_jsonl(DATA_DIR / "violations.jsonl")
    if not violations:
        raise HTTPException(400, "No corpus loaded — run a pipeline job first")
    agent = TSTRCopilotAgent()
    return agent.answer_with_rephrase(
        req.query,
        audit_logs=audit_logs,
        violations=violations,
        checkpoint_dir=RETRAIN_CHECKPOINT_DIR,
    )


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
