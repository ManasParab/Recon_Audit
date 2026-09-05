from pathlib import Path
from uuid import uuid4
import json
from decimal import Decimal
from .core.config import get_settings
from .ingestion.parsers import parse_batch
from .matching.engine import reconcile
from .agent.orchestrator import resolve_exception
from .ingestion.schemas import AgentResolution
from .audit_ledger.ledger import HashChain
from .evaluation.metrics import evaluate
from .db.session import SessionLocal
from .db.models import (IngestionBatch, NormalizedTransactionRow, MatchResultRow,
                        ExceptionRow, AgentResolutionRow, AuditLedgerRow, ReconciliationRun,
                        UploadedFile, ParseFailure)
from datetime import datetime
from typing import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

RUNS: dict[str, dict] = {}
LEDGER = HashChain()

def run_reconciliation(batch_id: str | None = None, progress: Callable[[dict], None] | None = None) -> dict:
    def report(stage: str, detail: str, current: int | None = None, total: int | None = None, **extra):
        if progress:
            progress({"stage": stage, "detail": detail, "current": current, "total": total, **extra})
    settings, run_id = get_settings(), str(uuid4())
    report("Reading uploaded records", "Loading the source records into the reconciliation workspace.")
    txns = _uploaded_transactions(batch_id) if batch_id else parse_batch(settings.data_dir, run_id)
    if not txns:
        raise ValueError("No accepted records are available for this case.")
    ledger_start = len(LEDGER.records)
    report("Creating audit entries", f"Recording {len(txns)} normalized source records in the audit trail.")
    for txn in txns: LEDGER.append("INGEST", txn.model_dump(mode="json"))
    report("Running deterministic matching", "Applying exact, time-window, and fuzzy matching rules to the uploaded data.")
    matches = reconcile(txns); output = []
    agent_resolutions = _agent_resolutions(matches, txns, settings, report)
    for match_number, match in enumerate(matches, start=1):
        item = match.model_dump(mode="json")
        if match.status == "MATCHED":
            LEDGER.append("MATCH", item)
            report("Recording deterministic result", f"Recorded match {match_number} of {len(matches)}.", match_number, len(matches))
        else:
            LEDGER.append("EXCEPTION", item)
            resolution = agent_resolutions.get(match.match_id) or resolve_exception(match, txns, settings.agent_step_budget, progress=report)
            item["agent"] = resolution.model_dump(mode="json")
            LEDGER.append("AGENT_RESOLVE" if resolution.outcome == "RESOLVED" else "AGENT_ABSTAIN", item["agent"])
        output.append(item)
    # Manual uploads do not have a hidden answer key: show operational counts instead of invented accuracy.
    if batch_id:
        matched = sum(1 for item in output if item["status"] == "MATCHED")
        metric = {"total_records": len([t for t in txns if t.source == "order"]), "matched_records": matched,
                  "match_rate": round(100 * matched / max(1, len([t for t in txns if t.source == "order"])), 2),
                  "resolution_accuracy": None, "honesty_score": None, "false_resolution_rate": None,
                  "exception_precision": None, "exception_recall": None, "exception_f1": None,
                  "note": "Accuracy metrics need a verified answer key and are not estimated for client uploads."}
    else:
        truth = json.loads((Path(settings.data_dir) / "ground_truth.json").read_text(encoding="utf-8"))
        metric = evaluate(output, truth)
    RUNS[run_id] = {"run_id": run_id, "batch_id": batch_id, "results": output, "evaluation": metric,
                    "workflow": ["Files validated", "Rows normalized", "Deterministic matching completed", "Exceptions investigated", "Audit ledger secured"]}
    report("Securing audit trail", "Persisting reconciled records, evidence, and hash-linked audit entries.")
    _persist(run_id, txns, output, metric, LEDGER.records[ledger_start:])
    report("Reconciliation complete", "The results and audit trail are ready to review.")
    return RUNS[run_id]


def _agent_resolutions(matches, transactions, settings, report) -> dict[str, AgentResolution]:
    """Every exception receives the same evidence-grounded agent investigation."""
    exceptions = [match for match in matches if match.status == "EXCEPTION"]
    if not exceptions:
        return {}
    workers = max(1, min(settings.agent_max_concurrency, len(exceptions)))
    report("Native Gemini investigations", f"Investigating all {len(exceptions)} exceptions with up to {workers} concurrent workers.", 0, len(exceptions))
    resolutions = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(resolve_exception, match, transactions, settings.agent_step_budget, report): match for match in exceptions}
        completed = 0
        for future in as_completed(futures):
            match = futures[future]
            completed += 1
            try:
                resolutions[match.match_id] = future.result()
            except Exception:
                resolutions[match.match_id] = AgentResolution(exception_id=match.match_id, outcome="ABSTAINED", reason_if_abstained="Automated investigation could not complete; manual review is required.")
            report("Native Gemini investigations", f"Completed {completed} of {len(exceptions)} exception investigations.", completed, len(exceptions))
    return resolutions


def get_run(run_id: str) -> dict | None:
    if run_id in RUNS:
        return RUNS[run_id]
    with SessionLocal() as session:
        stored = session.get(ReconciliationRun, run_id)
        return None if stored is None else {"run_id": stored.id, "results": stored.results, "evaluation": stored.evaluation}


def _persist(run_id, txns, results, metric, ledger_records):
    """Commit the complete immutable run projection and normalized audit entities."""
    with SessionLocal() as session:
        session.add(IngestionBatch(id=run_id))
        for t in txns:
            session.add(NormalizedTransactionRow(txn_id=f"{run_id}:{t.txn_id}", batch_id=run_id, source=t.source, amount=t.amount, currency=t.currency, timestamp=t.timestamp, raw_payload=t.raw_payload))
        for item in results:
            session.add(MatchResultRow(id=f"{run_id}:{item['match_id']}", run_id=run_id, status=item["status"], exception_type=item.get("exception_type"), rule_applied=item["rule_applied"], payload=item))
            if item["status"] == "EXCEPTION":
                session.add(ExceptionRow(id=f"{run_id}:{item['match_id']}", run_id=run_id, exception_type=item["exception_type"], payload=item))
                agent = item.get("agent")
                if agent:
                    session.add(AgentResolutionRow(exception_id=f"{run_id}:{agent['exception_id']}", outcome=agent["outcome"], root_cause_category=agent.get("root_cause_category"), payload=agent))
        for record in ledger_records:
            session.add(AuditLedgerRow(record_id=record["record_id"], event_type=record["event_type"], payload=record["payload"], timestamp=datetime.fromisoformat(record["timestamp"]), prev_hash=record["prev_hash"], record_hash=record["record_hash"]))
        session.add(ReconciliationRun(id=run_id, results=results, evaluation=metric))
        session.commit()


def create_batch() -> str:
    batch_id = str(uuid4())
    with SessionLocal() as session:
        session.add(IngestionBatch(id=batch_id)); session.commit()
    return batch_id


def save_upload(batch_id: str, source: str, filename: str, rows, failures) -> dict:
    unique_rows, seen = [], set()
    for row in rows:
        if row.txn_id in seen:
            failures.append({"row": len(unique_rows), "raw_payload": row.raw_payload, "error": f"Duplicate transaction ID '{row.txn_id}' in this file"})
        else:
            seen.add(row.txn_id); unique_rows.append(row)
    rows = unique_rows
    with SessionLocal() as session:
        if session.get(IngestionBatch, batch_id) is None:
            raise ValueError("Case workspace was not found")
        # Replacing a source is intentional: it lets a client correct and re-upload a file.
        for old in session.query(NormalizedTransactionRow).filter_by(batch_id=batch_id, source=source): session.delete(old)
        for old in session.query(UploadedFile).filter_by(batch_id=batch_id, source=source): session.delete(old)
        for old in session.query(ParseFailure).filter_by(batch_id=batch_id, source=source): session.delete(old)
        for row in rows:
            session.add(NormalizedTransactionRow(txn_id=f"{batch_id}:{row.txn_id}", batch_id=batch_id, source=row.source, amount=row.amount, currency=row.currency, timestamp=row.timestamp, raw_payload=row.raw_payload))
        session.add(UploadedFile(id=str(uuid4()), batch_id=batch_id, source=source, filename=filename, accepted_rows=len(rows), failed_rows=len(failures)))
        for failure in failures:
            session.add(ParseFailure(id=str(uuid4()), batch_id=batch_id, source=source, row_number=failure["row"] + 1, raw_payload=failure["raw_payload"], error=failure["error"]))
        session.commit()
    return get_batch(batch_id)


def get_batch(batch_id: str) -> dict | None:
    with SessionLocal() as session:
        if session.get(IngestionBatch, batch_id) is None: return None
        files = session.query(UploadedFile).filter_by(batch_id=batch_id).all()
        failures = session.query(ParseFailure).filter_by(batch_id=batch_id).all()
        rows = session.query(NormalizedTransactionRow).filter_by(batch_id=batch_id).all()
        return {"batch_id": batch_id, "files": [{"source": x.source, "filename": x.filename, "accepted_rows": x.accepted_rows, "failed_rows": x.failed_rows} for x in files],
                "records": [{"txn_id": x.txn_id.split(":", 1)[-1], "source": x.source, "amount": str(x.amount), "currency": x.currency, "timestamp": x.timestamp.isoformat(), "raw_payload": x.raw_payload} for x in rows],
                "parse_failures": [{"source": x.source, "row": x.row_number, "raw_payload": x.raw_payload, "error": x.error} for x in failures]}


def _uploaded_transactions(batch_id: str) -> list:
    view = get_batch(batch_id)
    if view is None: raise ValueError("Case workspace was not found")
    from .ingestion.schemas import NormalizedTransaction
    return [NormalizedTransaction(txn_id=r["txn_id"], source=r["source"], amount=Decimal(r["amount"]), currency=r["currency"], timestamp=r["timestamp"], counterparty=r["raw_payload"].get("merchant") or r["raw_payload"].get("counterparty"), reference_id=r["raw_payload"].get("reference"), raw_payload=r["raw_payload"], ingestion_batch_id=batch_id) for r in view["records"]]
