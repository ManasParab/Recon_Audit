from ..ingestion.schemas import NormalizedTransaction


class InvestigationTools:
    def __init__(self, transactions: list[NormalizedTransaction]): self.by_id = {x.txn_id: x for x in transactions}; self.all = transactions
    def lookup_record(self, txn_id: str) -> dict:
        tx = self.by_id.get(txn_id); return {"tool": "lookup_record", "input": {"txn_id": txn_id}, "result": tx.model_dump(mode="json") if tx else None}
    def search_related_transactions(self, reference: str) -> dict:
        found = [t.model_dump(mode="json") for t in self.all if t.reference_id == reference]
        return {"tool": "search_related_transactions", "input": {"reference": reference}, "result": found}
    def check_timing_window(self, txn_id_a: str, txn_id_b: str) -> dict:
        a, b = self.by_id.get(txn_id_a), self.by_id.get(txn_id_b); days = None if not a or not b else abs((a.timestamp-b.timestamp).total_seconds()) / 86400
        return {"tool": "check_timing_window", "input": {"txn_id_a": txn_id_a, "txn_id_b": txn_id_b}, "result": {"days": days, "within_t_plus_2": days is not None and days <= 2}}
    def compare_amounts(self, txn_id_a: str, txn_id_b: str) -> dict:
        a, b = self.by_id.get(txn_id_a), self.by_id.get(txn_id_b)
        return {"tool": "compare_amounts", "input": {"txn_id_a": txn_id_a, "txn_id_b": txn_id_b}, "result": {"equal": bool(a and b and a.amount == b.amount), "difference": str(abs(a.amount-b.amount)) if a and b else None}}
