"""AI Manager: sends a proposal narrative to a language model and returns a
validated, correctly typed audit. It never prints and never decides anything.

Class overview
    AIClient (abstract)        the contract: "give me a prompt, I give you text"
      OpenRouterClient         the real implementation (OpenRouter chat API)
    AuditResponseParser        raw model text -> validated audit dict
    AIManager                  uses an AIClient (aggregation) and owns an
                               AuditResponseParser (composition)

Dependency inversion: AIManager depends on the AIClient abstraction, so tests
and future providers plug in a different client without editing AIManager.
"""

import copy
import json
import logging
import math
import os
import re
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from openai import OpenAI

from models import PlaceholderKeywords

AiAudit = dict[str, Any]
ProgressCallback = Callable[[threading.Event, int], None]

# Stay silent unless the app (main.py via the Data Manager) sets up a log file;
# otherwise Python's default handler would print warnings into the terminal screens.
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Seconds to wait for the model before giving up.
AI_TIMEOUT_SECONDS = 60

# Fallback defaults used whenever the AI response is missing, malformed,
# or not valid JSON. This keeps the Logic Manager safe from AI errors
# or hallucinated formatting without it ever having to see raw AI
# output itself: schema validation with graceful fallback defaults is
# explicitly this layer's job per the system architecture.
DEFAULT_AI_AUDIT = {
    "scope_category": "Unknown",
    "primary_intervention_type": "",
    "estimated_energy_reduction_pct": 0.0,
    "estimated_lifetime_abatement_tonnes": 0.0,
    "detected_exclusion_keywords": [],
    "implementation_bottleneck": "",
    "ai_reasoning_summary": "AI response could not be parsed; manual review recommended.",
    # "ok" when the model answered with usable JSON, "failed" when the
    # call errored or the answer could not be parsed (fallback defaults).
    "ai_status": "failed",
}

SYSTEM_PROMPT = """You are a compliance-classification assistant for a Singapore SME green grant auditor.
Given a free-text proposal narrative describing an energy or sustainability upgrade, classify it
and respond with ONLY a single valid JSON object (no markdown, no commentary, no code fences)
containing EXACTLY these keys:

- "scope_category": one of "Scope-1", "Scope-2", "Scope-3", or "Unknown"
- "primary_intervention_type": a short label for the main intervention (e.g. "Commercial Fleet Electrification", "Fossil Fuel Modification", "Smart HVAC / Chiller Optimization")
- "estimated_energy_reduction_pct": a number estimating the percentage energy/emissions reduction
- "estimated_lifetime_abatement_tonnes": a number estimating lifetime carbon abatement in tonnes CO2e, ONLY if the narrative explicitly states or clearly implies a figure; otherwise 0.0. Do not invent a number.
- "detected_exclusion_keywords": a list of strings naming any disqualifying elements detected (e.g. "second-hand", "refurbished", "unregistered conversion"); empty list if none
- "implementation_bottleneck": a short string describing any practical implementation constraint mentioned, or "" if none
- "ai_reasoning_summary": a short 1-2 sentence explanation of your classification

Do not perform any financial calculations or eligibility decisions. Only classify and extract."""


# ---------------------------------------------------------------------------
# The AI provider contract and its implementation
# ---------------------------------------------------------------------------
class AIClient(ABC):
    """Anything that can turn a system prompt and a user message into the
    model's answer text."""

    @abstractmethod
    def complete(self, system_prompt: str, user_message: str) -> Any:
        """Returns the model's answer (normally a string). Raises on failure."""


class OpenRouterClient(AIClient):
    """AIClient backed by the OpenRouter chat-completions API."""

    BASE_URL = "https://openrouter.ai/api/v1"
    MODEL = "openrouter/free"

    def __init__(
        self,
        timeout_seconds: int = AI_TIMEOUT_SECONDS,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._client_factory = client_factory or self.setup_ai_client

    def setup_ai_client(self) -> OpenAI:
        api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Add it to your .env file (see README)."
            )
        return OpenAI(
            base_url=self.BASE_URL,
            api_key=api_key,
            max_retries=0,
            timeout=self._timeout,  # Otherwise, say AI not responding
        )

    def complete(self, system_prompt: str, user_message: str) -> Any:
        client = self._client_factory()
        response = client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
            timeout=self._timeout,
        )
        return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------
class AuditResponseParser:
    """Turns whatever the model returned into the exact schema the Logic
    Manager expects. The model can return the right keys with the wrong types
    (e.g. "30%" instead of 30, or null instead of a list); everything here
    falls back to the safe defaults field by field."""

    @staticmethod
    def default_audit() -> AiAudit:
        """A fresh copy of the fallback audit. A deep copy, so changing the
        keyword list of one result can never change the shared defaults."""
        return copy.deepcopy(DEFAULT_AI_AUDIT)

    @classmethod
    def unusable_answer(cls, reason: str) -> AiAudit:
        """Logs why the model's answer could not be used and returns the safe
        fallback audit (the app carries on and sends the case to manual review)."""
        logger.warning(
            "AI answer could not be used (%s); using fallback defaults.", reason
        )
        return cls.default_audit()

    @classmethod
    def parse(cls, raw_content: Any) -> AiAudit:
        """Parses raw AI text into a validated audit dict, filling in any
        missing keys with safe defaults."""
        # Some models return a list of content parts (or nothing usable).
        if not isinstance(raw_content, str):
            return cls.unusable_answer("the answer was not text")

        cleaned = raw_content.strip()

        # Strip markdown code fences in case the model wrapped its JSON in them
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            # Some models add a sentence before/after the JSON; try the part
            # between the first "{" and the last "}".
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start == -1 or end <= start:
                return cls.unusable_answer("no JSON object found")
            try:
                parsed = json.loads(cleaned[start : end + 1])
            except (json.JSONDecodeError, ValueError):
                return cls.unusable_answer("invalid JSON")

        if not isinstance(parsed, dict):
            return cls.unusable_answer("JSON was not an object")

        return cls.sanitise(parsed)

    @classmethod
    def sanitise(cls, parsed: Any) -> AiAudit:
        """Builds a complete, correctly typed audit dict from parsed JSON."""
        if not isinstance(parsed, dict):
            return cls.default_audit()
        audit = cls.default_audit()
        audit["scope_category"] = cls.to_scope(parsed.get("scope_category"))
        audit["primary_intervention_type"] = cls.to_text(
            parsed.get("primary_intervention_type")
        )
        audit["estimated_energy_reduction_pct"] = cls.to_number(
            parsed.get("estimated_energy_reduction_pct"), 0.0, 0.0, 100.0
        )
        audit["estimated_lifetime_abatement_tonnes"] = cls.to_number(
            parsed.get("estimated_lifetime_abatement_tonnes"), 0.0, 0.0
        )
        audit["detected_exclusion_keywords"] = cls.to_string_list(
            parsed.get("detected_exclusion_keywords")
        )
        audit["implementation_bottleneck"] = cls.to_text(
            parsed.get("implementation_bottleneck")
        )
        audit["ai_reasoning_summary"] = cls.to_text(
            parsed.get("ai_reasoning_summary"),
            DEFAULT_AI_AUDIT["ai_reasoning_summary"],
        )
        audit["ai_status"] = "ok"
        return audit

    @staticmethod
    def to_number(
        value: Any,
        default: float = 0.0,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        """Converts numbers and strings like "30", "30%" or "1,200" to a finite
        float, clamped to [minimum, maximum]. Anything else -> default."""
        if isinstance(value, bool):
            return default
        if isinstance(value, str):
            match = re.search(r"-?\d[\d,]*\.?\d*|-?\.\d+", value)
            if not match:
                return default
            try:
                value = float(match.group().replace(",", ""))
            except ValueError:
                return default
        if not isinstance(value, (int, float)):
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        if minimum is not None:
            number = max(number, minimum)
        if maximum is not None:
            number = min(number, maximum)
        return number

    @staticmethod
    def to_text(value: Any, default: str = "") -> str:
        if value is None:
            return default
        return value.strip() if isinstance(value, str) else str(value)

    @staticmethod
    def to_scope(value: Any) -> str:
        """ "scope-1", "Scope 1" and "scope1" all become "Scope-1"."""
        if isinstance(value, str):
            match = re.fullmatch(r"\s*scope[\s_-]*([123])\s*", value, re.IGNORECASE)
            if match:
                return f"Scope-{match.group(1)}"
        return "Unknown"

    @staticmethod
    def to_string_list(value: Any) -> list[str]:
        """A list of non-empty strings. A single string is split on commas,
        semicolons and new lines; None or other types give an empty list."""
        if isinstance(value, str):
            value = re.split(r"[,;\n]", value)
        if not isinstance(value, (list, tuple)):
            return []
        items = []
        for item in value:
            if item is None or isinstance(item, (dict, list, tuple)):
                continue
            text = str(item).strip()
            if text and not PlaceholderKeywords.matches(text):
                items.append(text)
        return items


# ---------------------------------------------------------------------------
# The AI Manager
# ---------------------------------------------------------------------------
class AIManager:
    """Sends the proposal narrative to the model and returns a validated
    audit dict matching the schema the Logic Manager expects."""

    def __init__(self, client: AIClient | None = None) -> None:
        self._client = client or OpenRouterClient()
        self._parser = AuditResponseParser()

    def get_ai_response(
        self,
        proposal_narrative: str,
        show_progress: ProgressCallback | None = None,
    ) -> AiAudit:
        """show_progress is an optional function(stop_event, timeout_seconds)
        that the caller supplies to animate a waiting screen on the main thread
        while the call runs; it must return once stop_event is set. The AI
        Manager never prints anything itself. Without it, the call is simply
        waited for."""
        # Event flag to signal when the API process completes
        api_done_event = threading.Event()

        # Storage for thread-safe return values / errors
        thread_results: dict[str, Any] = {"output": None, "error": None}

        def worker_api_call() -> None:
            """Background thread worker to execute the blocking network call."""
            try:
                thread_results["output"] = self._client.complete(
                    SYSTEM_PROMPT, proposal_narrative
                )
            except Exception as error:
                thread_results["error"] = error
            finally:
                # Tell the animation to stop tracking
                api_done_event.set()

        # daemon: if the user presses Ctrl+C during the wait, the program can
        # exit straight away instead of waiting for the network call to finish.
        api_thread = threading.Thread(target=worker_api_call, daemon=True)
        api_thread.start()

        # Let the caller show its waiting screen on the main thread
        if show_progress is not None:
            show_progress(api_done_event, AI_TIMEOUT_SECONDS)

        # Wait for the background thread (the client's own timeout ends it)
        api_thread.join()

        # Fallbacks if an error was caught inside the background worker
        error = thread_results["error"]
        if error is not None:
            logger.error(
                "AI call failed (%s: %s); using fallback defaults.",
                type(error).__name__,
                error,
            )
            fallback = self._parser.default_audit()
            fallback["ai_reasoning_summary"] = (
                f"AI call failed ({type(error).__name__}: {error}); "
                "manual review recommended."
            )
            return fallback

        return self._parser.parse(thread_results["output"])

    def parse_ai_audit(self, raw_content: Any) -> AiAudit:
        return self._parser.parse(raw_content)

    def sanitise_ai_audit(self, parsed: Any) -> AiAudit:
        return self._parser.sanitise(parsed)

    @staticmethod
    def ai_call_failed(ai_audit: Any) -> bool:
        """True when the audit is the fallback default (the AI call errored or
        its answer could not be used), so callers can avoid treating it as a
        real audit."""
        return not isinstance(ai_audit, dict) or ai_audit.get("ai_status") != "ok"
