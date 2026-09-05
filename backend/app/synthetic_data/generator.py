"""Deterministic three-feed dataset generator; ground truth is evaluation-only."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import csv, json, random
from pathlib import Path
from faker import Faker
import xmltodict

EXCEPTION_TYPES = ["MISSING_SETTLEMENT", "MISSING_BANK_CREDIT", "AMOUNT_MISMATCH", "TIMING_ANOMALY", "DUPLICATE_TRANSACTION", "ORPHAN_RECORD"]


def generate_batch(seed: int = 42, output_dir: Path | str | None = None, count: int = 60) -> dict:
    if count < 50:
        raise ValueError("count must be at least 50")
    out = Path(output_dir or "../infra/seed_data").resolve()
    out.mkdir(parents=True, exist_ok=True)
    rng, fake = random.Random(seed), Faker()
    fake.seed_instance(seed)
    base = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
    orders, settlements, banks, truth = [], [], [], {}
    # 70% clean, 20% resolvable exception, 10% intentionally ambiguous.
    clean_end, resolvable_end = int(count * .7), int(count * .9)
    for i in range(count):
        ref = f"RA-{seed}-{i + 1:04d}"
        amount = Decimal(rng.randrange(1000, 20000)) / 100
        when = base + timedelta(hours=i * 5)
        merchant = fake.company()
        order = {"id": f"ord-{i+1:04d}", "reference": ref, "amount": str(amount), "currency": "INR", "created_at": when.isoformat(), "merchant": merchant}
        settlement = {"id": f"set-{i+1:04d}", "reference": ref, "amount": str(amount), "currency": "INR", "settled_at": (when + timedelta(days=1)).isoformat(), "merchant": merchant}
        bank = {"id": f"bnk-{i+1:04d}", "reference": ref, "amount": str(amount), "currency": "INR", "credited_at": (when + timedelta(days=1, hours=1)).isoformat(), "counterparty": merchant}
        status, exc, resolvable, cause = "MATCHED", None, False, None
        if clean_end <= i < resolvable_end:
            exc, status, resolvable, cause = EXCEPTION_TYPES[(i-clean_end) % len(EXCEPTION_TYPES)], "EXCEPTION", True, None
            if exc == "MISSING_SETTLEMENT":
                settlement = None; cause = "MISSING_SETTLEMENT"
            elif exc == "MISSING_BANK_CREDIT":
                bank = None; cause = "MISSING_BANK_CREDIT"
            elif exc == "AMOUNT_MISMATCH":
                bank["amount"] = str(amount + Decimal("1.00")); cause = "AMOUNT_MISMATCH"
            elif exc == "TIMING_ANOMALY":
                bank["credited_at"] = (when + timedelta(days=8)).isoformat(); cause = "TIMING_ANOMALY"
            elif exc == "DUPLICATE_TRANSACTION":
                banks.append({**bank, "id": f"bnk-dup-{i+1:04d}"}); cause = "DUPLICATE_TRANSACTION"
            else:
                # An extra unlinked bank credit is the orphan, while primary trio stays valid.
                banks.append({"id": f"bnk-orphan-{i+1:04d}", "reference": f"ORPHAN-{i}", "amount": "12.34", "currency": "INR", "credited_at": bank["credited_at"], "counterparty": "Unknown"}); cause = "ORPHAN_RECORD"
        elif i >= resolvable_end:
            status, exc, resolvable, cause = "EXCEPTION", "MISSING_BANK_CREDIT", False, "INSUFFICIENT_EVIDENCE"
            bank = None
        orders.append(order)
        if settlement: settlements.append(settlement)
        if bank: banks.append(bank)
        truth[order["id"]] = {"status": status, "exception_type": exc, "root_cause": cause, "resolvable": resolvable}
    (out / "orders.json").write_text(json.dumps(orders, indent=2), encoding="utf-8")
    with (out / "settlements.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "reference", "amount", "currency", "settled_at", "merchant"]); writer.writeheader(); writer.writerows(settlements)
    xml = {"bank_records": {"record": banks}}
    (out / "bank.xml").write_text(xmltodict.unparse(xml, pretty=True), encoding="utf-8")
    (out / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    return {"seed": seed, "record_count": count, "output_dir": str(out), "mix": {"clean": clean_end, "resolvable_exceptions": resolvable_end-clean_end, "ambiguous": count-resolvable_end}}
