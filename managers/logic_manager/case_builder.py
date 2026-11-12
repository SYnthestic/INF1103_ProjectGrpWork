"""CaseBuilder: builds a Case from the applicant's profile and the AI
audit."""

import math
from typing import Any

from models import EQUIPMENT_PROPOSAL, PlaceholderKeywords
from .case import Case
from .sme_criteria import SmeCriteria


class CaseBuilder:
    """Builds a Case from the applicant's profile and the AI audit."""

    def __init__(self, sme_criteria: SmeCriteria | None = None) -> None:
        self._sme = sme_criteria or SmeCriteria()

    @staticmethod
    def number(value: Any, default: float = 0.0) -> float:
        """A finite float, or `default` for None, text, NaN or infinity.
        Keeps one bad value from crashing the whole evaluation."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        value = float(value)
        return value if math.isfinite(value) else default

    @staticmethod
    def string_list(value: Any) -> list[str]:
        """The exclusion keywords as a list of strings (a lone string is kept
        whole instead of being read letter by letter). Placeholders such as
        "none" or "N/A" are not exclusions and are dropped."""
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple)):
            return []
        items = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text and not PlaceholderKeywords.matches(text):
                items.append(text)
        return items

    def build(self, user_profile: dict[str, Any], ai_audit: dict[str, Any]) -> Case:
        annual_revenue = self.number(user_profile.get("annual_revenue_sgd"))
        headcount = int(self.number(user_profile.get("group_employment_size")))
        local_equity = self.number(user_profile.get("local_shareholding_pct"))

        return Case(
            annual_revenue=annual_revenue,
            headcount=headcount,
            local_equity=local_equity,
            is_sme=self._sme.is_sme(local_equity, annual_revenue, headcount),
            sme_fail_reasons=self._sme.fail_reasons(
                local_equity, annual_revenue, headcount
            ),
            proposal_type=user_profile.get("proposal_type", EQUIPMENT_PROPOSAL),
            chosen_scheme=user_profile.get("sustainability_grant", 0),
            baseline_spend=self.number(
                user_profile.get("baseline_annual_energy_expenditure_sgd")
            ),
            retrofit_cost=self.number(user_profile.get("estimated_retrofit_cost_sgd")),
            advisory_fee=self.number(user_profile.get("reporting_advisory_fee_sgd")),
            scope=ai_audit.get("scope_category", "Unknown"),
            energy_reduction_pct=self.number(
                ai_audit.get("estimated_energy_reduction_pct")
            ),
            lifetime_tonnes=self.number(
                ai_audit.get("estimated_lifetime_abatement_tonnes")
            ),
            exclusions=self.string_list(ai_audit.get("detected_exclusion_keywords")),
            intervention=ai_audit.get("primary_intervention_type", ""),
            ai_failed=str(ai_audit.get("ai_status", "ok")).strip().lower() == "failed",
        )
