"""Shared constants and type aliases for the AI layer."""

import threading
from collections.abc import Callable
from typing import Any

AiAudit = dict[str, Any]
ProgressCallback = Callable[[threading.Event, int], None]

# Seconds to wait for the model before giving up.
AI_TIMEOUT_SECONDS = 60

# Fallback defaults used whenever the AI response is missing, malformed,
# or not valid JSON.
DEFAULT_AI_AUDIT = {
    "scope_category": "Unknown",
    "primary_intervention_type": "",
    "estimated_energy_reduction_pct": 0.0,
    "estimated_lifetime_abatement_tonnes": 0.0,
    "detected_exclusion_keywords": [],
    "implementation_bottleneck": "",
    "ai_reasoning_summary": "AI response could not be parsed; manual review recommended.",
    # "ok" when the model answered with usable JSON, "failed" otherwise.
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