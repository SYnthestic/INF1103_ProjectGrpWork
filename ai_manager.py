import os
import json
import sys
import time
import threading
from openai import OpenAI
from sme_interface_stores.sme_interface_gui import run_ai_analysis_bar


def setup_ai_client():
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
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
    "ai_reasoning_summary": "AI response could not be parsed; manual review recommended."
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
    api_thread = threading.Thread(target=worker_api_call)
    api_thread.start()

    # 2. Run the ASCII progress bar on the main UI thread immediately
    run_ai_analysis_bar(api_done_event, timeout_seconds=60)

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

    if raw_content is None:
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
        return dict(DEFAULT_AI_AUDIT)

    if not isinstance(parsed, dict):
        return dict(DEFAULT_AI_AUDIT)

    ai_audit = dict(DEFAULT_AI_AUDIT)
    for key in DEFAULT_AI_AUDIT:
        if key in parsed:
            ai_audit[key] = parsed[key]

    return ai_audit