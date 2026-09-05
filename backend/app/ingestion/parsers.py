from datetime import datetime
from decimal import Decimal
from pathlib import Path
import json
from io import BytesIO
import pandas as pd
import xmltodict
from .schemas import NormalizedTransaction


def _dt(value: str) -> datetime: return datetime.fromisoformat(value.replace("Z", "+00:00"))
def _make(row: dict, source: str, batch_id: str) -> NormalizedTransaction:
    mapping = {"order": ("created_at", "merchant"), "settlement": ("settled_at", "merchant"), "bank": ("credited_at", "counterparty")}
    time_key, party_key = mapping[source]
    return NormalizedTransaction(txn_id=row["id"], source=source, amount=Decimal(str(row["amount"])), currency=str(row["currency"]).upper(), timestamp=_dt(row[time_key]), counterparty=row.get(party_key), reference_id=row.get("reference"), raw_payload=dict(row), ingestion_batch_id=batch_id)


def parse_batch(data_dir: Path | str, batch_id: str) -> list[NormalizedTransaction]:
    folder = Path(data_dir)
    orders = json.loads((folder / "orders.json").read_text(encoding="utf-8"))
    settlements = pd.read_csv(folder / "settlements.csv").fillna("").to_dict("records")
    raw_bank = xmltodict.parse((folder / "bank.xml").read_text(encoding="utf-8"))["bank_records"].get("record", [])
    if isinstance(raw_bank, dict): raw_bank = [raw_bank]
    return ([_make(x, "order", batch_id) for x in orders] + [_make(x, "settlement", batch_id) for x in settlements] + [_make(x, "bank", batch_id) for x in raw_bank])


def parse_source_content(content: bytes, source: str, batch_id: str) -> tuple[list[NormalizedTransaction], list[dict]]:
    """Parse an uploaded feed; invalid rows are returned as explicit failures."""
    if source == "order": rows = json.loads(content.decode("utf-8"))
    elif source == "settlement": rows = pd.read_csv(BytesIO(content)).fillna("").to_dict("records")
    elif source == "bank":
        rows = xmltodict.parse(content.decode("utf-8"))["bank_records"].get("record", [])
        if isinstance(rows, dict): rows = [rows]
    else: raise ValueError("unsupported source")
    valid, failures = [], []
    for index, row in enumerate(rows):
        try: valid.append(_make(row, source, batch_id))
        except Exception as error: failures.append({"row": index, "raw_payload": row, "error": str(error)})
    return valid, failures
