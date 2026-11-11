"""UnclassifiedScopeRule: the AI could not place an equipment proposal in
Scope 1, 2 or 3."""

from ..constants import Decision, VALID_SCOPES
from ..case import Case
from .eligibility_rule import EligibilityRule


class UnclassifiedScopeRule(EligibilityRule):
    """The AI could not place an equipment proposal in Scope 1, 2 or 3."""

    def evaluate(self, case: Case) -> Decision | None:
        if case.scope in VALID_SCOPES:
            return None

        return self.make_decision(
            "MANUAL_REVIEW",
            [
                f"GHG Protocol scope could not be determined (AI returned '{case.scope}')."
            ],
            [
                "Provide a clearer description of the intervention so "
                "the AI Manager can classify it under Scope 1, 2, or 3."
            ],
        )
