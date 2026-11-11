"""LowImpactRule: everything else: under 10% (by default) is rejected."""

from ..constants import Decision
from ..case import Case
from .eligibility_rule import EligibilityRule
from ..rule_config import RuleConfig


class LowImpactRule(EligibilityRule):
    """Everything else: under 10% (by default) is rejected. This rule never
    returns None, so it is the catch-all that ends every rule list."""

    def __init__(self, config: RuleConfig | None = None) -> None:
        self._config = config or RuleConfig()

    def evaluate(self, case: Case) -> Decision:
        return self.make_decision(
            "REJECT_LOW_IMPACT",
            [
                f"Estimated energy reduction of {case.energy_reduction_pct:.1f}% "
                f"is below the minimum threshold of {self._config.minimum_impact_pct:.1f}% "
                "used by this system."
            ],
            [
                "Consider increasing the projected energy-efficiency "
                f"improvement to at least {self._config.provisional_min_pct:g}%.",
                "Consider additional energy-efficiency measures such "
                "as equipment upgrades, HVAC optimisation, lighting "
                "efficiency, or other applicable interventions.",
                "Recalculate the expected energy reduction after "
                "modifying the proposed project.",
            ],
        )
