"""MissingBaselineSpendRule: equipment subsidies come from the baseline
energy spend, so a zero or missing value would otherwise pre-approve a SGD 0 subsidy."""

from ..constants import Decision
from ..case import Case
from .eligibility_rule import EligibilityRule


class MissingBaselineSpendRule(EligibilityRule):
    """Equipment subsidies come from the baseline energy spend, so a zero or
    missing value would otherwise pre-approve a SGD 0 subsidy."""

    def evaluate(self, case: Case) -> Decision | None:
        if case.baseline_spend > 0:
            return None

        return self.make_decision(
            "MANUAL_REVIEW",
            [
                "No valid baseline annual energy expenditure was provided, "
                "so a subsidy cannot be calculated."
            ],
            [
                "Provide the company's baseline annual energy expenditure "
                "(more than SGD 0) and resubmit the proposal."
            ],
        )
