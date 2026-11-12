"""EegAdvancedTierRule: more than 350 tonnes of lifetime abatement (by
default)."""

from ..constants import Decision
from ..case import Case
from ..schemes.eeg_advanced_scheme import EegAdvancedScheme
from .eligibility_rule import EligibilityRule
from ..schemes.grant_scheme import GrantScheme
from ..rule_config import RuleConfig


class EegAdvancedTierRule(EligibilityRule):
    """More than 350 tonnes of lifetime abatement (by default). The AI's
    tonnes figure is only an estimate, so the proposal must also reach the
    minimum energy reduction (a claimed 400 tonnes with 0% reduction does not
    qualify)."""

    def __init__(
        self, scheme: GrantScheme | None = None, config: RuleConfig | None = None
    ) -> None:
        self._scheme = scheme or EegAdvancedScheme()
        self._config = config or RuleConfig()

    def evaluate(self, case: Case) -> Decision | None:
        limit = self._config.eeg_advanced_min_tonnes
        if not (
            case.lifetime_tonnes > limit
            and case.energy_reduction_pct >= self._config.minimum_impact_pct
        ):
            return None

        return self.make_decision(
            "PRE_APPROVED_TIER_1_ADVANCED",
            [
                "Company meets the SME eligibility requirements.",
                f"Estimated lifetime carbon abatement of "
                f"{case.lifetime_tonnes:.1f} tonnes exceeds the "
                f"{limit:g}-tonne Advanced Tier threshold.",
            ],
            [
                "Engage an independent energy assessor to verify the "
                "lifetime abatement estimate before final disbursement."
            ],
            [self._scheme.name],
            self._scheme.calculate_subsidy(case.baseline_spend),
        )
