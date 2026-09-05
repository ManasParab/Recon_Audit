from decimal import Decimal
from rapidfuzz.fuzz import ratio
from ..ingestion.schemas import MatchResult, NormalizedTransaction
from ..synthetic_data.generator import EXCEPTION_TYPES


def reconcile(transactions: list[NormalizedTransaction]) -> list[MatchResult]:
    groups: dict[str, dict[str, list[NormalizedTransaction]]] = {}
    for t in transactions:
        if t.reference_id: groups.setdefault(t.reference_id, {}).setdefault(t.source, []).append(t)
    results, used = [], set()
    for reference, feeds in groups.items():
        orders, sets, banks = feeds.get("order", []), feeds.get("settlement", []), feeds.get("bank", [])
        for order in orders:
            used.add(order.txn_id); ss, bs = sets[:], banks[:]
            if len(bs) > 1:
                results.append(_exception(order, "DUPLICATE_TRANSACTION", [order, *bs], "duplicate_bank_reference")); continue
            if not ss:
                results.append(_exception(order, "MISSING_SETTLEMENT", [order, *bs], "missing_settlement")); continue
            if not bs:
                results.append(_exception(order, "MISSING_BANK_CREDIT", [order, *ss], "missing_bank_credit")); continue
            settlement, bank = ss[0], bs[0]
            used.update([settlement.txn_id, bank.txn_id])
            if not (order.amount == settlement.amount == bank.amount and order.currency == settlement.currency == bank.currency):
                results.append(_exception(order, "AMOUNT_MISMATCH", [order, settlement, bank], "amount_comparison_failed")); continue
            lag = (bank.timestamp - order.timestamp).total_seconds() / 86400
            if lag > 2:
                results.append(_exception(order, "TIMING_ANOMALY", [order, settlement, bank], "settlement_window_exceeded")); continue
            results.append(MatchResult(match_id=f"match-{order.txn_id}", status="MATCHED", matched_txn_ids=[order.txn_id, settlement.txn_id, bank.txn_id], rule_applied="EXACT_REFERENCE_AMOUNT_CURRENCY", order_id=order.txn_id, evidence={"reference": reference, "lag_days": round(lag, 2)}))
    # Tier 2: reference may be absent/malformed, but amount/currency and T+2 are exact controls.
    unmatched_orders = [t for t in transactions if t.source == "order" and t.txn_id not in used]
    for order in unmatched_orders:
        candidates = [t for t in transactions if t.source in {"settlement", "bank"} and t.txn_id not in used and t.currency == order.currency and t.amount == order.amount and abs((t.timestamp-order.timestamp).total_seconds()) <= 2 * 86400]
        settlements = [t for t in candidates if t.source == "settlement"]
        banks = [t for t in candidates if t.source == "bank"]
        if settlements and banks:
            pair = [order, settlements[0], banks[0]]; used.update(t.txn_id for t in pair)
            results.append(MatchResult(match_id=f"match-{order.txn_id}", status="MATCHED", matched_txn_ids=[t.txn_id for t in pair], rule_applied="WINDOWED_AMOUNT_CURRENCY_T_PLUS_2", order_id=order.txn_id, evidence={"reference": order.reference_id}))
    # Tier 3: fuzzy reference/counterparty, with a deliberately tiny amount tolerance.
    for order in [t for t in transactions if t.source == "order" and t.txn_id not in used]:
        candidates = [t for t in transactions if t.source in {"settlement", "bank"} and t.txn_id not in used and t.currency == order.currency and abs(t.amount-order.amount) <= Decimal("0.01")]
        ranked = sorted(((ratio(f"{order.reference_id or ''} {order.counterparty or ''}", f"{t.reference_id or ''} {t.counterparty or ''}"), t) for t in candidates), reverse=True, key=lambda x: x[0])
        settlements = [t for score, t in ranked if score >= 85 and t.source == "settlement"]
        banks = [t for score, t in ranked if score >= 85 and t.source == "bank"]
        if settlements and banks:
            pair = [order, settlements[0], banks[0]]; used.update(t.txn_id for t in pair)
            results.append(MatchResult(match_id=f"match-{order.txn_id}", status="MATCHED", matched_txn_ids=[t.txn_id for t in pair], rule_applied="FUZZY_REFERENCE_COUNTERPARTY_AMOUNT_TOLERANCE", order_id=order.txn_id, evidence={"fuzzy_score": ranked[0][0]}))
    for t in transactions:
        if t.source == "bank" and t.txn_id not in used:
            results.append(MatchResult(match_id=f"exception-{t.txn_id}", status="EXCEPTION", exception_type="ORPHAN_RECORD", matched_txn_ids=[t.txn_id], rule_applied="UNMATCHED_BANK_RECORD", evidence={"reference": t.reference_id}))
    return results


def _exception(order, kind, txns, rule):
    return MatchResult(match_id=f"exception-{order.txn_id}", status="EXCEPTION", exception_type=kind, matched_txn_ids=[t.txn_id for t in txns], rule_applied=rule, order_id=order.txn_id, evidence={"reference": order.reference_id})
