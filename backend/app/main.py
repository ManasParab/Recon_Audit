from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from uuid import uuid4
from fastapi.middleware.cors import CORSMiddleware
from .synthetic_data.generator import generate_batch
from .core.config import get_settings
from .services import LEDGER, run_reconciliation, get_run, create_batch, save_upload, get_batch
from .db.session import Base, engine
from .db import models  # noqa: F401 -- registers database tables
from .ingestion.parsers import parse_source_content
from .db.session import SessionLocal
from .db.models import AuditLedgerRow

app = FastAPI(title="ReconAudit", version="1.0.0", description="Evidence-grounded finance reconciliation controller")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
JOBS: dict[str, dict] = {}

@app.on_event("startup")
def create_schema():
    Base.metadata.create_all(engine)

@app.get("/health")
def health(): return {"status": "ok"}
@app.post("/data/generate")
def generate(seed: int = 42, count: int = 60): return generate_batch(seed, get_settings().data_dir, count)
@app.post("/demo/run")
def demo_run(seed: int = 42):
    """One-click fixed-seed Buildathon run; answer key stays evaluation-only."""
    generate_batch(seed, get_settings().data_dir, 60)
    return run_reconciliation()

def _run_job(job_id: str, batch_id: str | None, seed: int | None = None):
    def report(event: dict):
        JOBS[job_id].update({"status": "processing", **event})
    JOBS[job_id].update({"status": "processing", "stage": "Preparing reconciliation", "detail": "Preparing the secure reconciliation workspace."})
    try:
        if seed is not None:
            report({"stage": "Generating demonstration data", "detail": "Creating the fixed, 60-record synthetic dataset."})
            generate_batch(seed, get_settings().data_dir, 60)
        JOBS[job_id] = {"status": "complete", "result": run_reconciliation(batch_id, progress=report)}
    except Exception as error:
        JOBS[job_id] = {"status": "failed", "message": str(error)}

@app.post("/demo/jobs")
def start_demo_job(background_tasks: BackgroundTasks, seed: int = 42):
    job_id = str(uuid4())
    JOBS[job_id] = {"status": "queued", "stage": "Queued", "detail": "Your demonstration is waiting to start."}
    background_tasks.add_task(_run_job, job_id, None, seed)
    return {"job_id": job_id, "status": "queued"}

@app.post("/reconcile/jobs")
def start_reconciliation_job(background_tasks: BackgroundTasks, batch_id: str):
    if get_batch(batch_id) is None:
        raise HTTPException(404, "Case workspace was not found")
    job_id = str(uuid4())
    JOBS[job_id] = {"status": "queued", "stage": "Queued", "detail": "Your reconciliation is waiting to start."}
    background_tasks.add_task(_run_job, job_id, batch_id)
    return {"job_id": job_id, "status": "queued"}

@app.get("/reconcile/jobs/{job_id}")
def reconciliation_job(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Reconciliation job was not found")
    return job
@app.post("/batches")
def create_case(): return {"batch_id": create_batch(), "message": "Your secure reconciliation workspace is ready."}
@app.get("/batches/{batch_id}")
def case_details(batch_id: str):
    batch = get_batch(batch_id)
    if batch is None: raise HTTPException(404, "Case workspace not found")
    return batch
@app.post("/batches/{batch_id}/files/{source}")
async def upload_case_file(batch_id: str, source: str, file: UploadFile = File(...)):
    if source not in {"order", "settlement", "bank"}: raise HTTPException(400, "Choose orders, settlements, or bank records")
    try:
        rows, failures = parse_source_content(await file.read(), source, batch_id)
        return save_upload(batch_id, source, file.filename or f"{source}-upload", rows, failures)
    except ValueError as error: raise HTTPException(404, str(error))
    except Exception as error: raise HTTPException(422, f"We could not read this file: {error}")
@app.post("/ingest/{source}")
async def ingest(source: str, file: UploadFile = File(...), batch_id: str | None = None):
    if source not in {"order", "settlement", "bank"}: raise HTTPException(400, "source must be order, settlement, or bank")
    try:
        rows, failures = parse_source_content(await file.read(), source, batch_id or str(uuid4()))
    except Exception as error:
        raise HTTPException(422, f"Unable to parse {source} feed: {error}")
    return {"batch_id": rows[0].ingestion_batch_id if rows else batch_id, "accepted": len(rows), "parse_failures": failures}
@app.post("/reconcile/run")
def run(batch_id: str | None = None):
    try: return run_reconciliation(batch_id)
    except ValueError as error: raise HTTPException(422, str(error))
@app.get("/reconcile/results/{run_id}")
def results(run_id: str):
    found = get_run(run_id)
    if found is None: raise HTTPException(404, "Run not found")
    return found
@app.get("/evaluation/{run_id}")
def evaluation(run_id: str):
    found = get_run(run_id)
    if found is None: raise HTTPException(404, "Run not found")
    return found["evaluation"]
@app.get("/audit/ledger")
def ledger(): return {"records": _ledger_records()}
@app.get("/audit/verify")
def verify():
    if LEDGER.records: return LEDGER.verify()
    persisted = LEDGER.__class__(); persisted.records = _ledger_records()
    return persisted.verify()

def _ledger_records():
    if LEDGER.records: return LEDGER.records
    with SessionLocal() as session:
        return [{"record_id": row.record_id, "event_type": row.event_type, "payload": row.payload,
                 "timestamp": row.timestamp.isoformat(), "prev_hash": row.prev_hash, "record_hash": row.record_hash}
                for row in session.query(AuditLedgerRow).order_by(AuditLedgerRow.timestamp).all()]

# Serve the client from the API origin. Opening index.html directly as a file: URL
# gives it an opaque browser origin and can prevent the client from reaching the API.
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[2] / "frontend", html=True), name="frontend")
