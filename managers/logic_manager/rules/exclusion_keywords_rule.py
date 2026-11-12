"""ExclusionKeywordsRule: prohibited equipment named by the AI ->
exclusion review."""

from ..constants import Decision
from ..case import Case
from .eligibility_rule import EligibilityRule


class ExclusionKeywordsRule(EligibilityRule):
    """Prohibited equipment named by the AI -> exclusion review."""

    def evaluate(self, case: Case) -> Decision | None:
        if not case.exclusions:
            return None

        reasons = [
            "Potentially prohibited equipment or modification was detected in the proposal."
        ]
        reasons += [f"Detected exclusion: {exclusion}" for exclusion in case.exclusions]

        return self.make_decision(
            "MANUAL_EXCLUSION_REVIEW",
            reasons,
            [
                "Remove the potentially prohibited equipment or modification from the proposal.",
                "Obtain a quotation for compliant, brand-new equipment where applicable.",
                "Resubmit the revised proposal for eligibility assessment.",
            ],
            ["Enterprise Sustainability Programme (Subject to re-quotation)"],
        )
