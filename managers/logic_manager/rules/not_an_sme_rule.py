"""NotAnSmeRule: statutory SME check."""

from ..constants import Decision, EFS_GREEN_NAME
from ..case import Case
from .eligibility_rule import EligibilityRule
from ..sme_criteria import SmeCriteria


class NotAnSmeRule(EligibilityRule):
    """Statutory SME check. Rejection here outranks every approval path
    below it, including the reporting grant."""

    def evaluate(self, case: Case) -> Decision | None:
        if case.is_sme:
            return None

        recommendations = [
            "Review the company's local shareholding structure and SME size criteria."
        ]
        if case.local_equity < SmeCriteria.MIN_LOCAL_EQUITY_PCT:
            recommendations.append(
                "Increase local shareholding to at least 30% "
                "if commercially and legally appropriate."
            )
        if case.annual_revenue > SmeCriteria.MAX_REVENUE_SGD:
            recommendations.append(
                "The company's revenue exceeds the SME cap of S$100 million. "
                "SME-targeted co-funding is therefore unavailable "
                "under these criteria."
            )
        recommendations.append(
            "Consider the Enterprise Financing Scheme – Green "
            "(EFS-Green) as an alternative financing route."
        )

        return self.make_decision(
            "REJECT_NON_SME", case.sme_fail_reasons, recommendations, [EFS_GREEN_NAME]
        )
