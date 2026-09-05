from ..ingestion.schemas import AgentResolution
from ..synthetic_data.generator import EXCEPTION_TYPES


def validate_resolution(resolution: AgentResolution) -> AgentResolution:
    if resolution.outcome == "ABSTAINED": return resolution
    observed = str(resolution.tool_trace)
    valid = resolution.root_cause_category in EXCEPTION_TYPES and bool(resolution.cited_fields) and all(field in observed for field in resolution.cited_fields)
    if not valid:
        return AgentResolution(exception_id=resolution.exception_id, outcome="ABSTAINED", tool_trace=resolution.tool_trace, steps_used=resolution.steps_used, reason_if_abstained="grounding guardrail rejected unsupported resolution")
    return resolution
