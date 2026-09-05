"""Relational persistence schema for managed Postgres deployments."""
from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .session import Base


class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))
    accepted_rows: Mapped[int] = mapped_column(Integer)
    failed_rows: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ParseFailure(Base):
    __tablename__ = "parse_failures"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(20))
    row_number: Mapped[int] = mapped_column(Integer)
    raw_payload: Mapped[dict] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(Text)

class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    results: Mapped[dict] = mapped_column(JSON)
    evaluation: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class NormalizedTransactionRow(Base):
    __tablename__ = "normalized_transactions"
    txn_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(20)); amount: Mapped[float] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3)); timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[dict] = mapped_column(JSON)

class MatchResultRow(Base):
    __tablename__ = "match_results"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True); status: Mapped[str] = mapped_column(String(20))
    exception_type: Mapped[str | None] = mapped_column(String(40), nullable=True); rule_applied: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)

class ExceptionRow(Base):
    __tablename__ = "exceptions"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    exception_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)

class AgentResolutionRow(Base):
    __tablename__ = "agent_resolutions"
    exception_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    outcome: Mapped[str] = mapped_column(String(20)); root_cause_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)

class AuditLedgerRow(Base):
    __tablename__ = "audit_ledger"
    record_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(30)); payload: Mapped[dict] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True)); prev_hash: Mapped[str] = mapped_column(String(64)); record_hash: Mapped[str] = mapped_column(String(64), unique=True)
