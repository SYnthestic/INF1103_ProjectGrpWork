"""EspProvisionalRule: any valid scope that misses the Scope-1 fast track
but still reaches 15% by default (so Scope-1 at 15-20% lands here too)."""

from ..constants import Decision
from ..case import Case
from .eligibility_rule import EligibilityRule
from ..schemes.esp_scheme import EspScheme
from ..schemes.grant_scheme import GrantScheme
from ..rule_config import RuleConfig


class EspProvisionalRule(EligibilityRule):
    """Any valid scope that misses the Scope-1 fast track but still reaches
    15% by default (so Scope-1 at 15-20% lands here too)."""

    def __init__(
        self, scheme: GrantScheme | None = None, config: RuleConfig | None = None
    ) -> None:
        self._scheme = scheme or EspScheme()
        self._config = config or RuleConfig()

    def evaluate(self, case: Case) -> Decision | None:
        threshold = self._config.provisional_min_pct
        if case.energy_reduction_pct < threshold:
            return None

        return self.make_decision(
            "PROVISIONAL_APPROVAL_TIER_2",
            [
                "Company meets the SME eligibility requirements.",
                f"Proposal targets {case.scope} emissions.",
                f"Estimated energy reduction of {case.energy_reduction_pct:.1f}% "
                f"meets the {threshold:g}% threshold for provisional capability-support approval.",
            ],
            [
                "Prepare supporting baseline energy and emissions "
                "documentation for final assessment."
            ],
            [self._scheme.name],
            self._scheme.calculate_subsidy(case.baseline_spend),
        )
