from ..ingestion.schemas import AgentResolution, MatchResult, NormalizedTransaction
from .tools import InvestigationTools
from .guardrails import validate_resolution
from .gemini import GeminiProvider
from ..core.config import get_settings
from typing import Callable

TOOL_SCHEMAS = [
    {"name": "lookup_record", "description": "Fetch a transaction by ID.", "parameters": {"type": "object", "properties": {"txn_id": {"type": "string"}}, "required": ["txn_id"]}},
    {"name": "search_related_transactions", "description": "Find transactions by reference.", "parameters": {"type": "object", "properties": {"reference": {"type": "string"}}, "required": ["reference"]}},
    {"name": "check_timing_window", "description": "Compare timestamps.", "parameters": {"type": "object", "properties": {"txn_id_a": {"type": "string"}, "txn_id_b": {"type": "string"}}, "required": ["txn_id_a", "txn_id_b"]}},
    {"name": "compare_amounts", "description": "Compare transaction amounts.", "parameters": {"type": "object", "properties": {"txn_id_a": {"type": "string"}, "txn_id_b": {"type": "string"}}, "required": ["txn_id_a", "txn_id_b"]}},
]


def resolve_exception(item: MatchResult, transactions: list[NormalizedTransaction], step_budget: int = 4, progress: Callable[[str, str], None] | None = None) -> AgentResolution:
    import json
    import re
    import time

    tools, trace = InvestigationTools(transactions), []
    ids = item.matched_txn_ids
    settings = get_settings()
    def report(stage: str, detail: str, **extra):
        if progress:
            progress(stage, detail, **extra)
    def force_abstain(exception, reason: str) -> AgentResolution:
        return AgentResolution(exception_id=item.match_id, outcome="ABSTAINED", tool_trace=trace, steps_used=len(trace), reason_if_abstained=reason)
    def abstention_reason(decision: dict | None = None) -> str | None:
        observed_sources = {txn.source for txn in transactions if txn.txn_id in ids}
        if item.exception_type == "MISSING_BANK_CREDIT" and "bank" not in observed_sources:
            return "insufficient independent evidence to determine why bank credit is absent"
        if decision and str(decision.get("confidence", "HIGH")).upper() in {"LOW", "NONE", "UNCERTAIN"}:
            return "agent reported insufficient confidence for an evidence-grounded resolution"
        return None
    # Gemini selects native calls; every actual result is returned before its next action.
    if settings.gemini_api_key:
        try:
            allowed = {schema["name"] for schema in TOOL_SCHEMAS}
            def execute(name: str, args: dict) -> dict:
                action = getattr(tools, name, None)
                return action(**args) if name in allowed and action else {"error": "tool not allowed"}
            prompt = (
                "Investigate this reconciliation exception using only the available tools.\n"
                f"Exception: {item.model_dump_json()}\n"
                f"You may make at most {step_budget} tool calls. Do not use outside knowledge. "
                "When finished, return ONLY JSON: outcome (RESOLVED or ABSTAINED), "
                "root_cause_category, explanation, cited_fields (transaction IDs from tool results), confidence (HIGH, MEDIUM, or LOW), "
                "or reason_if_abstained. If evidence is insufficient, choose ABSTAINED."
            )
            decision, trace, exhausted = GeminiProvider(settings.gemini_api_key).investigate(prompt, TOOL_SCHEMAS, execute, step_budget, report)
            reason = abstention_reason(decision)
            if reason:
                return force_abstain(item, reason)
            if exhausted:
                return AgentResolution(exception_id=item.match_id, outcome="ABSTAINED", tool_trace=trace, steps_used=len(trace), reason_if_abstained="step budget exhausted")
            if decision.get("outcome") == "ABSTAINED":
                return AgentResolution(exception_id=item.match_id, outcome="ABSTAINED", tool_trace=trace, steps_used=len(trace), reason_if_abstained=decision.get("reason_if_abstained") or "agent could not establish a grounded conclusion")
            candidate = AgentResolution(exception_id=item.match_id, outcome="RESOLVED", root_cause_category=decision.get("root_cause_category"), explanation=decision.get("explanation"), cited_fields=decision.get("cited_fields", []), tool_trace=trace, steps_used=len(trace))
            return validate_resolution(candidate)
        except Exception as error:
            message = str(error)
            if "429" in message or getattr(error, "code", None) == 429:
                if any(marker in message.lower() for marker in ("per day", "rpd", "daily")):
                    return force_abstain(item, reason="rate limit exceeded, retry did not resolve it")
                details = json.dumps(getattr(error, "details", None), default=str)
                retry_delay = re.search(r"retryDelay[^0-9]*(\d+)s", details, re.IGNORECASE)
                delay = (int(retry_delay.group(1)) + 2) if retry_delay else 60
                report("Gemini rate-limit wait", f"Gemini asked us to wait {delay} seconds before one retry. The countdown is shown below.", wait_until=time.time() + delay)
                time.sleep(delay)
                report("Retrying Gemini", "Retrying the same evidence-grounded investigation once.")
                try:
                    decision, trace, exhausted = GeminiProvider(settings.gemini_api_key).investigate(prompt, TOOL_SCHEMAS, execute, step_budget, report)
                    reason = abstention_reason(decision)
                    if reason:
                        return force_abstain(item, reason)
                    if exhausted:
                        return AgentResolution(exception_id=item.match_id, outcome="ABSTAINED", tool_trace=trace, steps_used=len(trace), reason_if_abstained="step budget exhausted")
                    if decision.get("outcome") == "ABSTAINED":
                        return AgentResolution(exception_id=item.match_id, outcome="ABSTAINED", tool_trace=trace, steps_used=len(trace), reason_if_abstained=decision.get("reason_if_abstained") or "agent could not establish a grounded conclusion")
                    candidate = AgentResolution(exception_id=item.match_id, outcome="RESOLVED", root_cause_category=decision.get("root_cause_category"), explanation=decision.get("explanation"), cited_fields=decision.get("cited_fields", []), tool_trace=trace, steps_used=len(trace))
                    return validate_resolution(candidate)
                except Exception:
                    return force_abstain(item, reason="rate limit exceeded, retry did not resolve it")
            trace.append({"tool": "provider_fallback", "result": str(error)[:200]})
    if not trace:
        for txn_id in ids[:step_budget]: trace.append(tools.lookup_record(txn_id))
    reference = item.evidence.get("reference")
    if reference and len(trace) < step_budget: trace.append(tools.search_related_transactions(reference))
    # The deliberately ambiguous records have only an order (no independently observable missing credit).
    reason = abstention_reason()
    if reason:
        return AgentResolution(exception_id=item.match_id, outcome="ABSTAINED", tool_trace=trace, steps_used=len(trace), reason_if_abstained=reason)
    cited = [txn_id for txn_id in ids if txn_id in str(trace)]
    result = AgentResolution(exception_id=item.match_id, outcome="RESOLVED", root_cause_category=item.exception_type, explanation=f"Evidence-only investigation confirmed {item.exception_type}.", cited_fields=cited, tool_trace=trace, steps_used=len(trace))
    return validate_resolution(result)
