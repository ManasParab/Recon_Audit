from pathlib import Path
from app.synthetic_data.generator import generate_batch
from app.ingestion.parsers import parse_batch
from app.matching.engine import reconcile
from app.audit_ledger.ledger import HashChain
from app.ingestion.schemas import NormalizedTransaction
from app.evaluation.metrics import evaluate
from app.agent.guardrails import validate_resolution
from app.agent.gemini import _decision
from app.ingestion.schemas import AgentResolution
from datetime import datetime, timezone, timedelta
from decimal import Decimal

def test_seed_is_reproducible(tmp_path):
    generate_batch(42, tmp_path, 60); one = (tmp_path / "orders.json").read_bytes()
    generate_batch(42, tmp_path, 60); assert one == (tmp_path / "orders.json").read_bytes()
def test_pipeline_has_expected_volume(tmp_path):
    generate_batch(42, tmp_path, 60); assert len(reconcile(parse_batch(tmp_path, "test"))) >= 60
def test_hash_chain_detects_tampering():
    ledger = HashChain(); ledger.append("MATCH", {"id": "1"}); ledger.records[0]["payload"]["id"] = "evil"; assert not ledger.verify()["valid"]

def test_windowed_match_handles_malformed_references():
    when = datetime.now(timezone.utc)
    rows = [
        NormalizedTransaction(txn_id="o", source="order", amount=Decimal("10"), currency="INR", timestamp=when, reference_id=None, ingestion_batch_id="b"),
        NormalizedTransaction(txn_id="s", source="settlement", amount=Decimal("10"), currency="INR", timestamp=when + timedelta(days=1), reference_id="TYP0", ingestion_batch_id="b"),
        NormalizedTransaction(txn_id="b", source="bank", amount=Decimal("10"), currency="INR", timestamp=when + timedelta(days=1), reference_id="TYP0", ingestion_batch_id="b"),
    ]
    assert reconcile(rows)[0].rule_applied == "WINDOWED_AMOUNT_CURRENCY_T_PLUS_2"

def test_evaluation_includes_exception_classification_metrics():
    report = evaluate([{"order_id": "o", "status": "EXCEPTION", "agent": {"outcome": "ABSTAINED"}}], {"o": {"status": "EXCEPTION", "resolvable": False, "root_cause": None}})
    assert report["exception_precision"] == report["exception_recall"] == report["exception_f1"] == 100

def test_ungrounded_agent_resolution_becomes_abstention():
    result = validate_resolution(AgentResolution(exception_id="e", outcome="RESOLVED", root_cause_category="AMOUNT_MISMATCH", cited_fields=["invented-id"], tool_trace=[]))
    assert result.outcome == "ABSTAINED"

def test_gemini_terminal_response_must_be_json():
    assert _decision("I think it is a mismatch") == {}
    assert _decision('{"outcome":"ABSTAINED","reason_if_abstained":"insufficient evidence"}')["outcome"] == "ABSTAINED"
