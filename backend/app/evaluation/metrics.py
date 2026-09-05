def evaluate(results: list[dict], truth: dict) -> dict:
    by_order = {r.get("order_id"): r for r in results if r.get("order_id")}
    total = len(truth); matched = sum(1 for oid, value in truth.items() if value["status"] == "MATCHED" and by_order.get(oid, {}).get("status") == "MATCHED")
    resolutions = [r for r in results if r.get("agent") and r["agent"]["outcome"] == "RESOLVED"]
    correct = sum(1 for r in resolutions if r.get("order_id") and truth.get(r["order_id"], {}).get("root_cause") == r["agent"].get("root_cause_category"))
    unresolvable = [oid for oid, x in truth.items() if not x["resolvable"] and x["status"] == "EXCEPTION"]
    abstained = sum(1 for oid in unresolvable if by_order.get(oid, {}).get("agent", {}).get("outcome") == "ABSTAINED")
    predicted_exceptions = {oid for oid, r in by_order.items() if r.get("status") == "EXCEPTION"}
    actual_exceptions = {oid for oid, value in truth.items() if value["status"] == "EXCEPTION"}
    tp = len(predicted_exceptions & actual_exceptions)
    precision = tp / len(predicted_exceptions) if predicted_exceptions else 0
    recall = tp / len(actual_exceptions) if actual_exceptions else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return {"total_records": total, "matched_records": matched, "match_rate": round(matched / total * 100, 2), "resolved_exceptions": len(resolutions), "resolution_accuracy": round((correct / len(resolutions) * 100) if resolutions else 0, 2), "honesty_score": round((abstained / len(unresolvable) * 100) if unresolvable else 100, 2), "false_resolution_rate": round(((len(resolutions)-correct)/len(resolutions)*100) if resolutions else 0, 2), "exception_precision": round(precision * 100, 2), "exception_recall": round(recall * 100, 2), "exception_f1": round(f1 * 100, 2)}
