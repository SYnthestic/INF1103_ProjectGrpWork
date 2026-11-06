"""How the web pages present results: friendly decision names, colour tones,
money, and labelled rows for the AI audit and the thresholds used. Nothing
here decides anything; it only turns the managers' output into text for the
templates."""

from typing import Any

from managers.logic_manager import RuleConfig

# decision_status -> (heading shown to the user, tone used for the colour)
DECISIONS = {
    "PRE_APPROVED_TIER_1_ADVANCED": ("Pre-approved: EEG Advanced Tier", "approved"),
    "PRE_APPROVED_TIER_1": ("Pre-approved: EEG Base Tier", "approved"),
    "PROVISIONAL_APPROVAL_TIER_2": ("Provisionally approved: ESP", "approved"),
    "PRE_APPROVED_SRG": ("Pre-approved: Sustainability Reporting Grant", "approved"),
    "MANUAL_REVIEW": ("Needs manual review", "review"),
    "MANUAL_EXCLUSION_REVIEW": ("Exclusion review needed", "review"),
    "REJECT_NON_SME": ("Rejected: not an SME", "rejected"),
    "REJECT_LOW_IMPACT": ("Rejected: energy reduction too low", "rejected"),
}

# AI audit key -> (label, unit or None)
AI_FIELDS = (
    ("scope_category", "GHG scope", None),
    ("primary_intervention_type", "Intervention", None),
    ("estimated_energy_reduction_pct", "Estimated energy reduction", "%"),
    ("estimated_lifetime_abatement_tonnes", "Lifetime abatement", "tonnes CO2e"),
    ("detected_exclusion_keywords", "Exclusion keywords", None),
    ("implementation_bottleneck", "Implementation bottleneck", None),
    ("ai_reasoning_summary", "AI reasoning", None),
)
HIDDEN_AI_KEYS = {"ai_status"}


def decision_label(status: Any) -> str:
    """'PRE_APPROVED_TIER_1' -> 'Pre-approved: EEG Base Tier'. Unknown
    statuses are shown as they are."""
    if not status:
        return "No decision"
    return DECISIONS.get(status, (str(status), "neutral"))[0]


def decision_tone(status: Any) -> str:
    """approved / review / rejected / neutral (used as a CSS class)."""
    return DECISIONS.get(status, ("", "neutral"))[1]


def money(amount: Any) -> str:
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        return "-"
    return f"SGD {amount:,.2f}"


def number(value: Any, unit: str | None = None) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value) if value not in (None, "") else "-"
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    if not unit:
        return text
    return f"{text}%" if unit == "%" else f"{text} {unit}"


def text_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value) if value else "None"
    if value in (None, ""):
        return "-"
    return str(value)


def ai_rows(ai_audit: Any) -> list[tuple[str, str]]:
    """(label, value) rows for an AI audit: the known fields first, in a
    fixed order, then anything else the AI returned."""
    if not isinstance(ai_audit, dict):
        return []
    rows = []
    for key, label, unit in AI_FIELDS:
        if key in ai_audit:
            value = ai_audit[key]
            shown = number(value, unit) if unit else text_value(value)
            rows.append((label, shown))
    known = {key for key, _, _ in AI_FIELDS} | HIDDEN_AI_KEYS
    for key, value in ai_audit.items():
        if key not in known:
            rows.append((key.replace("_", " ").capitalize(), text_value(value)))
    return rows


def threshold_rows(rules_used: Any) -> list[tuple[str, str]]:
    """(label, value) rows for the thresholds an audit was decided with."""
    if not isinstance(rules_used, dict):
        return []
    rows = []
    for key, (label, unit) in RuleConfig.LABELS.items():
        if key in rules_used:
            rows.append((label, number(rules_used[key], unit)))
    return rows


def application_rows(application: Any) -> list[tuple[str, str]]:
    if not isinstance(application, dict):
        return []
    rows = []
    for key, value in application.items():
        is_amount = key in (
            "Company Total Revenue",
            "Baseline Energy Expenditure",
            "Estimated Retrofit Cost",
            "Reporting Advisory Fee",
        )
        if is_amount:
            shown = money(value)
        elif key == "Local Equity":
            shown = number(value, "%")
        else:
            shown = text_value(value)
        rows.append((key, shown))
    return rows


FILTERS = {
    "decision_label": decision_label,
    "decision_tone": decision_tone,
    "money": money,
}
HELPERS = {
    "ai_rows": ai_rows,
    "threshold_rows": threshold_rows,
    "application_rows": application_rows,
}
