import os
import json
import math
import re
import sys
import time
import threading
from openai import OpenAI
import io_manager as in_and_out


def setup_ai_client():

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file (see README)."
        )
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        max_retries=0,
        timeout=60 # Otherwise, say AI not responding
    )
    return client


# Fallback defaults used whenever the AI response is missing, malformed,
# or not valid JSON. This keeps the Logic Manager safe from AI errors
# or hallucinated formatting without it ever having to see raw AI
# output itself — schema validation with graceful fallback defaults is
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
    "ai_status": "failed"
}

VALID_SCOPE_NAMES = ("Scope-1", "Scope-2", "Scope-3")

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


def get_ai_response(proposal_narrative):
    """
    Sends the proposal narrative to the LLM and returns a validated
    ai_audit dict matching the schema logic_manager.py expects.
    
    Runs a thread-safe ASCII animation bar concurrently with the API call.
    """
    # Create an event flag to signal when the API process completes
    api_done_event = threading.Event()
    
    # Storage container for thread safe return values / errors
    thread_results = {"output": None, "error": None}

    def worker_api_call():
        """Background thread worker to execute the blocking network call."""
        try:
            client = setup_ai_client()
            response = client.chat.completions.create(
                model="openrouter/free",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": proposal_narrative}
                ],
                timeout=60
            )
            thread_results["output"] = response.choices[0].message.content
        except Exception as error:
            thread_results["error"] = error
        finally:
            # Tell the animation thread to immediately stop tracking
            api_done_event.set()

    # 1. Spawn and start the background API network thread
    # daemon: if the user presses Ctrl+C during the wait, the program can
    # exit straight away instead of waiting for the network call to finish.
    api_thread = threading.Thread(target=worker_api_call, daemon=True)
    api_thread.start()

    # 2. Run the ASCII progress bar on the main UI thread immediately
    in_and_out.run_ai_analysis_bar(api_done_event, timeout_seconds=60)

    # 3. Ensure background thread wraps up completely before processing results
    api_thread.join()

    # 4. Handle Fallbacks if an error was caught inside the background worker
    if thread_results["error"] is not None:
        error = thread_results["error"]
        fallback = dict(DEFAULT_AI_AUDIT)
        fallback["ai_reasoning_summary"] = (
            f"AI call failed ({type(error).__name__}: {error}); "
            "manual review recommended."
        )
        return fallback

    # 5. Extract and parse standard response text
    raw_content = thread_results["output"]
    return parse_ai_audit(raw_content)


def parse_ai_audit(raw_content):
    """
    Parses raw AI text into a validated ai_audit dict, filling in any
    missing keys with safe defaults so downstream layers always
    receive a complete, predictable schema regardless of what the
    model actually returned.
    """

    # Some models return a list of content parts (or nothing usable).
    if not isinstance(raw_content, str):
        return dict(DEFAULT_AI_AUDIT)

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
            return dict(DEFAULT_AI_AUDIT)
        try:
            parsed = json.loads(cleaned[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return dict(DEFAULT_AI_AUDIT)

    if not isinstance(parsed, dict):
        return dict(DEFAULT_AI_AUDIT)

    return sanitise_ai_audit(parsed)


def ai_call_failed(ai_audit):
    """True when the audit is the fallback default (the AI call errored or
    its answer could not be used), so callers can avoid treating it as a
    real audit."""
    return not isinstance(ai_audit, dict) or ai_audit.get("ai_status") != "ok"


# ---------------------------------------------------------------------------
# Schema validation: the model can return the right keys with the wrong
# types (e.g. "30%" instead of 30, or null instead of a list). Everything
# below turns whatever came back into the exact types the Logic Manager
# expects, falling back to the safe defaults field by field.
# ---------------------------------------------------------------------------

def _to_number(value, default=0.0, minimum=None, maximum=None):
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


def _to_text(value, default=""):
    if value is None:
        return default
    return value.strip() if isinstance(value, str) else str(value)


def _to_scope(value):
    """"scope-1", "Scope 1" and "scope1" all become "Scope-1"."""
    if isinstance(value, str):
        match = re.fullmatch(r"\s*scope[\s_-]*([123])\s*", value, re.IGNORECASE)
        if match:
            return f"Scope-{match.group(1)}"
    return "Unknown"


def _to_string_list(value):
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
        if text:
            items.append(text)
    return items


def sanitise_ai_audit(parsed):
    """Builds a complete, correctly typed ai_audit dict from parsed JSON."""
    ai_audit = dict(DEFAULT_AI_AUDIT)
    ai_audit["scope_category"] = _to_scope(parsed.get("scope_category"))
    ai_audit["primary_intervention_type"] = _to_text(parsed.get("primary_intervention_type"))
    ai_audit["estimated_energy_reduction_pct"] = _to_number(
        parsed.get("estimated_energy_reduction_pct"), 0.0, 0.0, 100.0
    )
    ai_audit["estimated_lifetime_abatement_tonnes"] = _to_number(
        parsed.get("estimated_lifetime_abatement_tonnes"), 0.0, 0.0
    )
    ai_audit["detected_exclusion_keywords"] = _to_string_list(
        parsed.get("detected_exclusion_keywords")
    )
    ai_audit["implementation_bottleneck"] = _to_text(parsed.get("implementation_bottleneck"))
    ai_audit["ai_reasoning_summary"] = _to_text(
        parsed.get("ai_reasoning_summary"), DEFAULT_AI_AUDIT["ai_reasoning_summary"]
    )
    ai_audit["ai_status"] = "ok"
    return ai_audit
