"""FossilFuelModificationRule: fossil-fuel modification may be an excluded
activity."""

from ..constants import Decision, FOSSIL_FUEL_LABEL
from ..case import Case
from .eligibility_rule import EligibilityRule


class FossilFuelModificationRule(EligibilityRule):
    """Fossil-fuel modification may be an excluded activity."""

    def evaluate(self, case: Case) -> Decision | None:
        if case.intervention != FOSSIL_FUEL_LABEL:
            return None

        return self.make_decision(
            "MANUAL_EXCLUSION_REVIEW",
            [
                "The proposed intervention involves fossil-fuel modification, "
                "which may fall under a grant exclusion."
            ],
            [
                "Consider replacing the fossil-fuel modification with an "
                "energy-efficiency or low-carbon alternative.",
                "Submit supporting technical documentation for manual eligibility review.",
            ],
        )
