"""ReportingGrantRule: sustainability Reporting Grant (30% of the fee,
capped)."""

from models import REPORTING_PROPOSAL
from ..constants import Decision
from ..case import Case
from .eligibility_rule import EligibilityRule
from ..schemes.grant_scheme import GrantScheme
from ..schemes.srg_scheme import SrgScheme


class ReportingGrantRule(EligibilityRule):
    """Sustainability Reporting Grant (30% of the fee, capped)."""

    def __init__(self, scheme: GrantScheme | None = None) -> None:
        self._scheme = scheme or SrgScheme()

    def evaluate(self, case: Case) -> Decision | None:
        if case.proposal_type != REPORTING_PROPOSAL:
            return None

        return self.make_decision(
            "PRE_APPROVED_SRG",
            [
                "Company meets the SME eligibility requirements.",
                "Proposal covers an inaugural ESG assurance report "
                "rather than an equipment or capability upgrade.",
            ],
            [
                "Ensure the external assurance statement covers, at "
                "minimum, Scope 1 and Scope 2 emissions in line with "
                "ISSB and GRI standards."
            ],
            [self._scheme.name],
            self._scheme.calculate_subsidy(case.advisory_fee),
        )
