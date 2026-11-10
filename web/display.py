"""How the web pages present results: friendly decision names, colour tones,
money, labelled rows for the AI audit and the thresholds used, and the grant
cards on the home page. Nothing here decides anything; it only turns the
managers' output into text for the templates.

Class overview
    ResultPresenter   formatting for the templates. install() makes its
                      methods available in every template as filters
                      (decision_label, decision_tone, money) and helpers.
"""

from typing import Any

from flask import Flask

from managers.logic_manager import (
    EFS_GREEN_NAME,
    EegAdvancedScheme,
    EegBaseScheme,
    EspScheme,
    RuleConfig,
    SmeCriteria,
    SrgScheme,
)


class ResultPresenter:
    """Turns decisions, AI audits, applications and thresholds into text and
    rows for the templates."""

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

    @classmethod
    def decision_label(cls, status: Any) -> str:
        """'PRE_APPROVED_TIER_1' -> 'Pre-approved: EEG Base Tier'. Unknown
        statuses are shown as they are."""
        if not status:
            return "No decision"
        return cls.DECISIONS.get(status, (str(status), "neutral"))[0]


    @classmethod
    def decision_tone(cls, status: Any) -> str:
        """approved / review / rejected / neutral (used as a CSS class)."""
        return cls.DECISIONS.get(status, ("", "neutral"))[1]


    @staticmethod
    def money(amount: Any) -> str:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            return "-"
        return f"SGD {amount:,.2f}"


    @staticmethod
    def number(value: Any, unit: str | None = None) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return str(value) if value not in (None, "") else "-"
        text = f"{value:,.2f}".rstrip("0").rstrip(".")
        if not unit:
            return text
        return f"{text}%" if unit == "%" else f"{text} {unit}"


    @staticmethod
    def text_value(value: Any) -> str:
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value) if value else "None"
        if value in (None, ""):
            return "-"
        return str(value)


    @classmethod
    def ai_rows(cls, ai_audit: Any) -> list[tuple[str, str]]:
        """(label, value) rows for an AI audit: the known fields first, in a
        fixed order, then anything else the AI returned."""
        if not isinstance(ai_audit, dict):
            return []
        rows = []
        for key, label, unit in cls.AI_FIELDS:
            if key in ai_audit:
                value = ai_audit[key]
                shown = cls.number(value, unit) if unit else cls.text_value(value)
                rows.append((label, shown))
        known = {key for key, _, _ in cls.AI_FIELDS} | cls.HIDDEN_AI_KEYS
        for key, value in ai_audit.items():
            if key not in known:
                rows.append((key.replace("_", " ").capitalize(), cls.text_value(value)))
        return rows


    @classmethod
    def threshold_rows(cls, rules_used: Any) -> list[tuple[str, str]]:
        """(label, value) rows for the thresholds an audit was decided with."""
        if not isinstance(rules_used, dict):
            return []
        rows = []
        for key, (label, unit) in RuleConfig.LABELS.items():
            if key in rules_used:
                rows.append((label, cls.number(rules_used[key], unit)))
        return rows


    @classmethod
    def application_rows(cls, application: Any) -> list[tuple[str, str]]:
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
                shown = cls.money(value)
            elif key == "Local Equity":
                shown = cls.number(value, "%")
            else:
                shown = cls.text_value(value)
            rows.append((key, shown))
        return rows


    @staticmethod
    def percent(rate: float) -> str:
        return f"{rate * 100:g}%"


    @classmethod
    def grant_cards(cls, config: RuleConfig) -> list[dict[str, Any]]:
        """One card per grant the auditor decides on, for the home page. The
        names, co-funding rates and caps come from the GrantScheme classes and
        the conditions from the thresholds in use, so the page always matches
        the rules the Logic Manager applies."""
        advanced, base, esp, srg = EegAdvancedScheme(), EegBaseScheme(), EspScheme(), SrgScheme()
        return [
            {
                "name": advanced.name,
                "for": "Equipment and energy upgrades with a large lifetime carbon saving",
                "funding": f"{cls.percent(advanced.rate)} of your baseline annual energy spend",
                "cap": cls.money(advanced.cap),
                "conditions": [
                    f"Lifetime carbon abatement above {config.eeg_advanced_min_tonnes:g} tonnes",
                    f"Energy reduction of at least {config.minimum_impact_pct:g}%",
                ],
            },
            {
                "name": base.name,
                "for": "Fast track for upgrades that cut direct (Scope 1) emissions",
                "funding": f"{cls.percent(base.rate)} of your baseline annual energy spend",
                "cap": cls.money(base.cap),
                "conditions": [
                    "The upgrade targets Scope 1 emissions (for example fuel burned on site or in vehicles)",
                    f"Energy reduction of at least {config.fast_track_min_pct:g}%",
                    f"Also matched with the {esp.name}",
                ],
            },
            {
                "name": esp.name,
                "for": "Provisional support for energy upgrades in any emission scope",
                "funding": f"{cls.percent(esp.rate)} of your baseline annual energy spend",
                "cap": cls.money(esp.cap),
                "conditions": [
                    "Any GHG scope (1, 2 or 3)",
                    f"Energy reduction of at least {config.provisional_min_pct:g}%",
                ],
            },
            {
                "name": srg.name,
                "for": "Your company's first ESG / sustainability report",
                "funding": f"{cls.percent(srg.rate)} of the external reporting or advisory fee",
                "cap": cls.money(srg.cap),
                "conditions": [
                    "Choose the ESG Reporting / Advisory proposal type",
                    "A quoted reporting or advisory fee above SGD 0",
                ],
            },
        ]


    @classmethod
    def eligibility_points(cls, config: RuleConfig) -> list[str]:
        """What every applicant must meet, and what happens near the thresholds."""
        sme = SmeCriteria
        return [
            f"Be an SME: at least {sme.MIN_LOCAL_EQUITY_PCT:g}% local shareholding and "
            f"annual group revenue of at most {cls.money(sme.MAX_REVENUE_SGD)}.",
            "Use brand-new equipment: second-hand, refurbished or fossil-fuel "
            "modifications are sent for an exclusion review.",
            f"Equipment proposals with an energy reduction from {config.minimum_impact_pct:g}% "
            f"to under {config.provisional_min_pct:g}% are sent for manual review; below "
            f"{config.minimum_impact_pct:g}% they are not funded.",
            "Equipment subsidies are never more than the retrofit cost you enter.",
            f"Companies that are not SMEs are pointed to the {EFS_GREEN_NAME} instead.",
        ]

    def filters(self) -> dict[str, Any]:
        return {
            "decision_label": self.decision_label,
            "decision_tone": self.decision_tone,
            "money": self.money,
        }

    def helpers(self) -> dict[str, Any]:
        return {
            "ai_rows": self.ai_rows,
            "grant_cards": self.grant_cards,
            "eligibility_points": self.eligibility_points,
            "threshold_rows": self.threshold_rows,
            "application_rows": self.application_rows,
        }

    def install(self, app: Flask) -> None:
        """Makes the formatting available in every template of `app`."""
        app.jinja_env.filters.update(self.filters())
        app.jinja_env.globals.update(self.helpers())
