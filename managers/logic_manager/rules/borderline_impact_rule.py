"""BorderlineImpactRule: 10% to under 15% by default: above the rejection
line but below the provisional approval line, so neither an automatic approval nor an automatic rejection is fair."""

from ..constants import Decision
from ..case import Case
from .eligibility_rule import EligibilityRule
from ..rule_config import RuleConfig


class BorderlineImpactRule(EligibilityRule):
    """10% to under 15% by default: above the rejection line but below the
    provisional approval line, so neither an automatic approval nor an
    automatic rejection is fair."""

    def __init__(self, config: RuleConfig | None = None) -> None:
        self._config = config or RuleConfig()

    def evaluate(self, case: Case) -> Decision | None:
        minimum = self._config.minimum_impact_pct
        provisional = self._config.provisional_min_pct
        if not minimum <= case.energy_reduction_pct < provisional:
            return None

        return self.make_decision(
            "MANUAL_REVIEW",
            [
                f"Estimated energy reduction of {case.energy_reduction_pct:.1f}% meets the "
                f"minimum of {minimum:g}% but is below the "
                f"{provisional:g}% needed for provisional approval."
            ],
            [
                "Submit supporting baseline and measurement data so a "
                "reviewer can assess the proposal.",
                "Consider measures that raise the projected energy reduction "
                f"to at least {provisional:g}%.",
            ],
        )
