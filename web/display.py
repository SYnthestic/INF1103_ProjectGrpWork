"""How the web pages present results: friendly decision names, colour tones,
money, and labelled rows for the AI audit and the thresholds used. Nothing
here decides anything; it only turns the managers' output into text for the
templates."""

from typing import Any

from managers.logic_manager import (
    EFS_GREEN_NAME,
    EegAdvancedScheme,
    EegBaseScheme,
    EspScheme,
    RuleConfig,
    SmeCriteria,
    SrgScheme,
)

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


def percent(rate: float) -> str:
    return f"{rate * 100:g}%"


def grant_cards(config: RuleConfig) -> list[dict[str, Any]]:
    """One card per grant the auditor decides on, for the home page. The
    names, co-funding rates and caps come from the GrantScheme classes and
    the conditions from the thresholds in use, so the page always matches
    the rules the Logic Manager applies."""
    advanced, base, esp, srg = EegAdvancedScheme(), EegBaseScheme(), EspScheme(), SrgScheme()
    return [
        {
            "name": advanced.name,
            "for": "Equipment and energy upgrades with a large lifetime carbon saving",
            "funding": f"{percent(advanced.rate)} of your baseline annual energy spend",
            "cap": money(advanced.cap),
            "conditions": [
                f"Lifetime carbon abatement above {config.eeg_advanced_min_tonnes:g} tonnes",
                f"Energy reduction of at least {config.minimum_impact_pct:g}%",
            ],
        },
        {
            "name": base.name,
            "for": "Fast track for upgrades that cut direct (Scope 1) emissions",
            "funding": f"{percent(base.rate)} of your baseline annual energy spend",
            "cap": money(base.cap),
            "conditions": [
                "The upgrade targets Scope 1 emissions (for example fuel burned on site or in vehicles)",
                f"Energy reduction of at least {config.fast_track_min_pct:g}%",
                f"Also matched with the {esp.name}",
            ],
        },
        {
            "name": esp.name,
            "for": "Provisional support for energy upgrades in any emission scope",
            "funding": f"{percent(esp.rate)} of your baseline annual energy spend",
            "cap": money(esp.cap),
            "conditions": [
                "Any GHG scope (1, 2 or 3)",
                f"Energy reduction of at least {config.provisional_min_pct:g}%",
            ],
        },
        {
            "name": srg.name,
            "for": "Your company's first ESG / sustainability report",
            "funding": f"{percent(srg.rate)} of the external reporting or advisory fee",
            "cap": money(srg.cap),
            "conditions": [
                "Choose the ESG Reporting / Advisory proposal type",
                "A quoted reporting or advisory fee above SGD 0",
            ],
        },
    ]


def eligibility_points(config: RuleConfig) -> list[str]:
    """What every applicant must meet, and what happens near the thresholds."""
    sme = SmeCriteria
    return [
        f"Be an SME: at least {sme.MIN_LOCAL_EQUITY_PCT:g}% local shareholding and "
        f"annual group revenue of at most {money(sme.MAX_REVENUE_SGD)}.",
        "Use brand-new equipment: second-hand, refurbished or fossil-fuel "
        "modifications are sent for an exclusion review.",
        f"Equipment proposals with an energy reduction from {config.minimum_impact_pct:g}% "
        f"to under {config.provisional_min_pct:g}% are sent for manual review; below "
        f"{config.minimum_impact_pct:g}% they are not funded.",
        "Equipment subsidies are never more than the retrofit cost you enter.",
        f"Companies that are not SMEs are pointed to the {EFS_GREEN_NAME} instead.",
    ]


FILTERS = {
    "decision_label": decision_label,
    "decision_tone": decision_tone,
    "money": money,
}
HELPERS = {
    "ai_rows": ai_rows,
    "grant_cards": grant_cards,
    "eligibility_points": eligibility_points,
    "threshold_rows": threshold_rows,
    "application_rows": application_rows,
}
