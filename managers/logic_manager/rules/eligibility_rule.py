"""EligibilityRule: one small rule."""

from abc import ABC, abstractmethod

from ..constants import Decision
from ..case import Case


class EligibilityRule(ABC):
    """One small rule. It either returns a decision or returns None to say
    "not mine". Every subclass is substitutable for this base (LSP): the same
    call, the same return type, no surprises for the engine."""

    @abstractmethod
    def evaluate(self, case: Case) -> Decision | None:
        """A decision when this rule applies, otherwise None."""

    @staticmethod
    def make_decision(
        status: str,
        reasons: list[str] | None = None,
        recommendations: list[str] | None = None,
        matched_schemes: list[str] | None = None,
        subsidy: float = 0.0,
    ) -> Decision:
        """What a rule returns: the outcome plus everything the report shows."""
        return {
            "decision_status": status,
            "reasons": list(reasons or []),
            "recommendations": list(recommendations or []),
            "matched_schemes": list(matched_schemes or []),
            "approved_subsidy_sgd": subsidy,
        }
