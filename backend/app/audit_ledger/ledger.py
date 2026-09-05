from datetime import datetime, timezone
import hashlib, json, uuid


def canonical(value: dict) -> str: return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
class HashChain:
    def __init__(self): self.records: list[dict] = []; self.last_hash = "0" * 64
    def append(self, event_type: str, payload: dict) -> dict:
        timestamp = datetime.now(timezone.utc).isoformat()
        digest = hashlib.sha256((self.last_hash + canonical(payload) + timestamp).encode()).hexdigest()
        record = {"record_id": str(uuid.uuid4()), "event_type": event_type, "payload": payload, "timestamp": timestamp, "prev_hash": self.last_hash, "record_hash": digest}
        self.records.append(record); self.last_hash = digest; return record
    def verify(self) -> dict:
        previous = "0" * 64
        for index, record in enumerate(self.records):
            expected = hashlib.sha256((previous + canonical(record["payload"]) + record["timestamp"]).encode()).hexdigest()
            if record["prev_hash"] != previous or record["record_hash"] != expected: return {"valid": False, "broken_at": index, "record_id": record["record_id"]}
            previous = record["record_hash"]
        return {"valid": True, "records_checked": len(self.records)}
