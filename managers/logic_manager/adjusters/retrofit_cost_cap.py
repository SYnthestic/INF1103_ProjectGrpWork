"""RetrofitCostCap: equipment subsidies are worked out from the baseline
energy spend, so a small retrofit could otherwise be "granted" more than it costs."""

from ..constants import Decision, EQUIPMENT_SUBSIDY_STATUSES
from ..case import Case
from .decision_adjuster import DecisionAdjuster


class RetrofitCostCap(DecisionAdjuster):
    """Equipment subsidies are worked out from the baseline energy spend, so
    a small retrofit could otherwise be "granted" more than it costs.
    (A cost of 0 means "not stated" and applies no cap.)"""

    def adjust(self, decision: Decision, case: Case) -> None:
        if (
            decision["decision_status"] in EQUIPMENT_SUBSIDY_STATUSES
            and 0 < case.retrofit_cost < decision["approved_subsidy_sgd"]
        ):
            decision["approved_subsidy_sgd"] = round(case.retrofit_cost, 2)
            decision["reasons"].append(
                f"Subsidy limited to the stated retrofit cost of SGD {case.retrofit_cost:,.2f}."
            )
