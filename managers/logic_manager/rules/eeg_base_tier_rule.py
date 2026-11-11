"""EegBaseTierRule: scope-1 fast track: at least 20% energy reduction (by
default)."""

from ..constants import Decision
from ..case import Case
from ..schemes.eeg_base_scheme import EegBaseScheme
from .eligibility_rule import EligibilityRule
from ..schemes.esp_scheme import EspScheme
from ..schemes.grant_scheme import GrantScheme
from ..rule_config import RuleConfig


class EegBaseTierRule(EligibilityRule):
    """Scope-1 fast track: at least 20% energy reduction (by default)."""

    def __init__(
        self,
        scheme: GrantScheme | None = None,
        companion_scheme: GrantScheme | None = None,
        config: RuleConfig | None = None,
    ) -> None:
        self._scheme = scheme or EegBaseScheme()
        self._companion = companion_scheme or EspScheme()
        self._config = config or RuleConfig()

    def evaluate(self, case: Case) -> Decision | None:
        threshold = self._config.fast_track_min_pct
        if not (case.scope == "Scope-1" and case.energy_reduction_pct >= threshold):
            return None

        return self.make_decision(
            "PRE_APPROVED_TIER_1",
            [
                "Company meets the SME eligibility requirements.",
                "Proposal targets Scope-1 emissions.",
                f"Estimated energy reduction of {case.energy_reduction_pct:.1f}% "
                f"meets the {threshold:g}% threshold for this system's fast-track rule.",
            ],
            [],
            [self._scheme.name, self._companion.name],
            self._scheme.calculate_subsidy(case.baseline_spend),
        )
