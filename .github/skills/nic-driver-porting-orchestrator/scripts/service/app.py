"""
NIC Driver Porting Orchestrator — FastAPI wrapper around the LangGraph porting pipeline.

Exposes a REST API for submitting porting jobs and polling for results.
Designed to run as a K8s Job or Deployment.

Endpoints:
    POST /port          — Submit a new porting job (async, returns job_id)
    GET  /port/{id}     — Poll job status and retrieve results
    GET  /health        — Liveness probe
    GET  /ready         — Readiness probe (checks LLM connectivity)
"""

import logging
import os
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Imports from the existing agent package (one level up)
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.pipeline import run_pipeline, PipelineState  # noqa: E402
from agent.analyze_build import initialize_llm, validate_environment_variables, setup_logging  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("porting_orchestrator.service")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ---------------------------------------------------------------------------
# LLM singleton (initialised once on startup)
# ---------------------------------------------------------------------------
_llm = None


@asynccontextmanager
async def _lifespan(application: FastAPI):
    """Initialise the Azure OpenAI LLM connection on startup."""
    global _llm
    logger.info("Validating environment variables …")
    validate_environment_variables(logger)
    logger.info("Initialising Azure OpenAI LLM …")
    _llm = initialize_llm()
    logger.info("LLM ready")
    cleanup_thread = threading.Thread(target=_cleanup_old_jobs, daemon=True)
    cleanup_thread.start()
    logger.info("Job-store cleanup thread started (TTL=%dh, interval=%ds)",
                _JOB_TTL_HOURS, _CLEANUP_INTERVAL_SECONDS)
    yield


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="NIC Driver Porting Orchestrator",
    description="Multi-agent swarm for autonomous NIC driver data-plane porting",
    version="2.0.0",
    lifespan=_lifespan,
)
class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PortRequest(BaseModel):
    """Request body for POST /port"""
    driver_name: str = Field(..., description="Driver name (e.g. ixgbe, ice, i40e)")
    target_os: str = Field("freebsd", description="Primary target OS (freebsd, windows)")
    source_dir: Optional[str] = Field(None, description="Path to Linux driver source")
    connection_info: Optional[Dict[str, Any]] = Field(None, description="SSH connection details for target VM")


class PortResponse(BaseModel):
    """Response for POST /port"""
    job_id: str
    status: JobStatus


class JobResult(BaseModel):
    """Response for GET /port/{job_id}"""
    job_id: str
    status: JobStatus
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    report: Optional[str] = None
    phase_status: Optional[Dict[str, str]] = None
    native_score: Optional[float] = None
    portability_score: Optional[float] = None
    errors: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()

# Jobs older than this TTL (after completion) are removed by the cleanup thread
_JOB_TTL_HOURS = int(os.environ.get("JOB_TTL_HOURS", "24"))
_CLEANUP_INTERVAL_SECONDS = int(os.environ.get("JOB_CLEANUP_INTERVAL_SECONDS", "3600"))


def _cleanup_old_jobs():
    """Background thread: periodically evict completed/failed jobs past TTL."""
    while True:
        time.sleep(_CLEANUP_INTERVAL_SECONDS)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=_JOB_TTL_HOURS)
        with _jobs_lock:
            expired = [
                jid for jid, job in _jobs.items()
                if job.get("finished_at") and
                datetime.fromisoformat(job["finished_at"]) < cutoff
            ]
            for jid in expired:
                del _jobs[jid]
        if expired:
            logger.info("Evicted %d expired job(s) from job store", len(expired))


_cleanup_thread = None  # started in lifespan


# ---------------------------------------------------------------------------
# Health / Readiness
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if _llm is None:
        raise HTTPException(status_code=503, detail="LLM not initialised")
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# POST /port — submit a new porting job
# ---------------------------------------------------------------------------
@app.post("/port", response_model=PortResponse)
def submit_porting(req: PortRequest):
    job_id = uuid.uuid4().hex[:12]

    with _jobs_lock:
        _jobs[job_id] = {
            "status": JobStatus.PENDING,
            "request": req.model_dump(),
            "started_at": None,
            "finished_at": None,
            "result_state": None,
            "error": None,
        }

    thread = threading.Thread(
        target=_run_porting_job, args=(job_id,), daemon=True
    )
    thread.start()

    return PortResponse(job_id=job_id, status=JobStatus.PENDING)


# ---------------------------------------------------------------------------
# GET /port/{job_id} — poll for results
# ---------------------------------------------------------------------------
@app.get("/port/{job_id}", response_model=JobResult)
def get_porting(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    result = JobResult(
        job_id=job_id,
        status=job["status"],
        started_at=job.get("started_at"),
        finished_at=job.get("finished_at"),
    )

    if job.get("started_at") and job.get("finished_at"):
        t0 = datetime.fromisoformat(job["started_at"])
        t1 = datetime.fromisoformat(job["finished_at"])
        result.duration_seconds = (t1 - t0).total_seconds()

    state: Optional[PipelineState] = job.get("result_state")
    if state:
        result.phase_status = state.get("phase_status")
        result.native_score = state.get("native_score")
        result.portability_score = state.get("portability_score")
        result.errors = state.get("errors")
        report_path = os.path.join(
            state.get("output_dir", ""), "porting_report.md"
        )
        if os.path.isfile(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                result.report = f.read()

    if job.get("error"):
        result.errors = result.errors or []
        result.errors.append(job["error"])

    return result


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------
def _run_porting_job(job_id: str):
    """Execute the porting pipeline in a background thread."""
    with _jobs_lock:
        job = _jobs[job_id]
        job["status"] = JobStatus.RUNNING
        job["started_at"] = datetime.now(timezone.utc).isoformat()

    req = job["request"]
    output_dir = os.path.join("/tmp/porting_orchestrator", job_id)
    os.makedirs(output_dir, exist_ok=True)

    pipeline_logger = setup_logging(output_dir)

    try:
        state = run_pipeline(
            driver_name=req["driver_name"],
            target_os=req.get("target_os", "freebsd"),
            output_dir=output_dir,
            source_dir=req.get("source_dir"),
            connection_info=req.get("connection_info"),
            llm=_llm,
            logger=pipeline_logger,
        )

        with _jobs_lock:
            job["status"] = JobStatus.COMPLETED
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            job["result_state"] = state

    except Exception as exc:
        logger.exception("Porting job %s failed", job_id)
        with _jobs_lock:
            job["status"] = JobStatus.FAILED
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            job["error"] = str(exc)
