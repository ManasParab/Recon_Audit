"""Manual, bounded Gemini function-calling loop."""
import json
import time
from threading import Lock
from typing import Callable


class GeminiProvider:
    # Current Gemini Flash model; keep this boundary isolated for future upgrades.
    model_name = "gemini-3.6-flash"
    _last_call_at = 0.0
    _call_lock = Lock()

    def __init__(self, api_key: str):
        from google import genai
        self.client = genai.Client(api_key=api_key)

    @classmethod
    def _pace_call(cls):
        with cls._call_lock:
            time.sleep(max(0, 0.15 - (time.monotonic() - cls._last_call_at)))
            cls._last_call_at = time.monotonic()

    def investigate(self, prompt: str, tool_schemas: list[dict], execute: Callable[[str, dict], dict], max_steps: int, progress: Callable[[str, str], None] | None = None) -> tuple[dict, list[dict], bool]:
        """Execute model-selected tools and return their results to the model."""
        from google.genai import types
        declarations = [types.FunctionDeclaration(name=s["name"], description=s["description"], parameters=s["parameters"]) for s in tool_schemas]
        config = types.GenerateContentConfig(tools=[types.Tool(function_declarations=declarations)], temperature=0)
        contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        trace: list[dict] = []
        for _ in range(max_steps):
            if progress:
                progress("Waiting for Gemini", "Gemini is selecting the next evidence-gathering action.")
            self._pace_call()
            response = self.client.models.generate_content(model=self.model_name, contents=contents, config=config)
            calls = list(response.function_calls or [])
            if not calls:
                return _decision(response.text or ""), trace, False
            if len(trace) + len(calls) > max_steps:
                return {"outcome": "ABSTAINED", "reason_if_abstained": "step budget exhausted"}, trace, True
            contents.append(response.candidates[0].content)
            response_parts = []
            for call in calls:
                name, args = call.name, dict(call.args or {})
                if progress:
                    progress("Gemini selected a tool", f"Gemini selected {name.replace('_', ' ')} and is checking the returned evidence.")
                result = execute(name, args)
                trace.append({"tool": name, "input": args, "result": result})
                response_parts.append(types.Part.from_function_response(name=name, response={"result": result}))
            contents.append(types.Content(role="user", parts=response_parts))
        return {"outcome": "ABSTAINED", "reason_if_abstained": "step budget exhausted"}, trace, True

    def triage(self, cases: list[dict]) -> set[str]:
        """Select ambiguous cases that warrant the slower native tool-calling loop."""
        from google.genai import types
        prompt = (
            "You are triaging reconciliation exceptions. Select only cases that need additional "
            "record-level investigation; do not determine a financial outcome. Return ONLY JSON "
            'in the form {"escalate_ids":["exception-id"]}.\nCases:\n' + json.dumps(cases, default=str)
        )
        self._pace_call()
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0),
        )
        value = _decision(response.text or "")
        return {str(case_id) for case_id in value.get("escalate_ids", [])}


def _decision(text: str) -> dict:
    """Narrative is never accepted as a terminal financial decision."""
    try:
        start, end = text.find("{"), text.rfind("}")
        value = json.loads(text[start:end + 1]) if start >= 0 and end >= start else {}
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
