from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field


class NormalizedTransaction(BaseModel):
    txn_id: str
    source: Literal["order", "settlement", "bank"]
    amount: Decimal
    currency: str
    timestamp: datetime
    counterparty: str | None = None
    reference_id: str | None = None
    raw_payload: dict = Field(default_factory=dict)
    ingestion_batch_id: str


class MatchResult(BaseModel):
    match_id: str
    status: Literal["MATCHED", "EXCEPTION"]
    exception_type: str | None = None
    matched_txn_ids: list[str]
    rule_applied: str
    order_id: str | None = None
    evidence: dict = Field(default_factory=dict)


class AgentResolution(BaseModel):
    exception_id: str
    outcome: Literal["RESOLVED", "ABSTAINED"]
    root_cause_category: str | None = None
    explanation: str | None = None
    cited_fields: list[str] = Field(default_factory=list)
    tool_trace: list[dict] = Field(default_factory=list)
    steps_used: int = 0
    reason_if_abstained: str | None = None
