"""AiFailedRule: the AI could not analyse the narrative, so no approval is
safe."""

from ..constants import Decision
from ..case import Case
from .eligibility_rule import EligibilityRule


class AiFailedRule(EligibilityRule):
    """The AI could not analyse the narrative, so no approval is safe."""

    def evaluate(self, case: Case) -> Decision | None:
        if not case.ai_failed:
            return None
        return self.make_decision(
            "MANUAL_REVIEW",
            reasons=[
                "The AI analysis failed, so the proposal could not be assessed automatically."
            ],
            recommendations=[
                "Run the analysis again, or send the proposal for manual review."
            ],
        )
