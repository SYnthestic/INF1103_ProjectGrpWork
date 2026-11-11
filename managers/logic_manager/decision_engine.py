"""DecisionEngine: runs the rules in order; the first rule to return a
decision wins, so the ORDER of the rules is the priority order of the grant rules."""

from collections.abc import Sequence

from .constants import Decision
from .rules.ai_failed_rule import AiFailedRule
from .rules.borderline_impact_rule import BorderlineImpactRule
from .case import Case
from .adjusters.decision_adjuster import DecisionAdjuster
from .rules.eeg_advanced_tier_rule import EegAdvancedTierRule
from .rules.eeg_base_tier_rule import EegBaseTierRule
from .rules.eligibility_rule import EligibilityRule
from .rules.esp_provisional_rule import EspProvisionalRule
from .rules.exclusion_keywords_rule import ExclusionKeywordsRule
from .rules.fossil_fuel_modification_rule import FossilFuelModificationRule
from .rules.low_impact_rule import LowImpactRule
from .rules.missing_baseline_spend_rule import MissingBaselineSpendRule
from .rules.not_an_sme_rule import NotAnSmeRule
from .rules.reporting_grant_rule import ReportingGrantRule
from .rules.reporting_without_fee_rule import ReportingWithoutFeeRule
from .adjusters.retrofit_cost_cap import RetrofitCostCap
from .rule_config import RuleConfig
from .adjusters.scheme_mismatch_note import SchemeMismatchNote
from .rules.unclassified_scope_rule import UnclassifiedScopeRule


class DecisionEngine:
    """Runs the rules in order; the first rule to return a decision wins, so
    the ORDER of the rules is the priority order of the grant rules. The rules
    and adjusters are handed in (aggregation): they exist without the engine
    and can be swapped or extended without editing it."""

    def __init__(
        self,
        rules: Sequence[EligibilityRule],
        adjusters: Sequence[DecisionAdjuster] = (),
    ) -> None:
        self._rules = tuple(rules)
        self._adjusters = tuple(adjusters)

    @classmethod
    def with_default_rules(cls, config: RuleConfig | None = None) -> "DecisionEngine":
        """The project's rule set, highest priority first. `config` sets the
        thresholds the rules use (the defaults if it is None)."""
        config = config or RuleConfig()
        return cls(
            rules=[
                ExclusionKeywordsRule(),
                FossilFuelModificationRule(),
                NotAnSmeRule(),
                AiFailedRule(),
                ReportingWithoutFeeRule(),
                ReportingGrantRule(),
                MissingBaselineSpendRule(),
                UnclassifiedScopeRule(),
                EegAdvancedTierRule(config=config),
                EegBaseTierRule(config=config),
                EspProvisionalRule(config=config),
                BorderlineImpactRule(config=config),
                LowImpactRule(config=config),
            ],
            adjusters=[RetrofitCostCap(), SchemeMismatchNote()],
        )

    @property
    def rules(self) -> tuple[EligibilityRule, ...]:
        return self._rules

    def decide(self, case: Case) -> Decision:
        decision = None
        for rule in self._rules:
            decision = rule.evaluate(case)
            if decision is not None:
                break
        if decision is None:
            raise LookupError("No eligibility rule produced a decision.")

        for adjuster in self._adjusters:
            adjuster.adjust(decision, case)
        return decision
