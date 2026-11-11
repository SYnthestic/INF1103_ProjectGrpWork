"""ReportingWithoutFeeRule: the grant is a percentage of the fee, so no
fee = nothing to approve."""

from models import REPORTING_PROPOSAL
from ..constants import Decision
from ..case import Case
from .eligibility_rule import EligibilityRule


class ReportingWithoutFeeRule(EligibilityRule):
    """The grant is a percentage of the fee, so no fee = nothing to approve."""

    def evaluate(self, case: Case) -> Decision | None:
        if case.proposal_type != REPORTING_PROPOSAL or case.advisory_fee > 0:
            return None

        return self.make_decision(
            "MANUAL_REVIEW",
            [
                "No valid external ESG reporting/advisory fee was provided, "
                "so a subsidy cannot be calculated."
            ],
            [
                "Provide the quoted reporting/advisory fee (more than SGD 0) "
                "and resubmit the proposal."
            ],
        )
