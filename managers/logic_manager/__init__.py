"""Logic Manager: every business rule of the grant auditor (no I/O, no AI).

Class overview
    LogicManager            facade the controller talks to
      PasswordHasher        owned by LogicManager   (composition)
      AesGcmCipher          owned by LogicManager   (composition): encrypts data files
      DecisionEngine        owned by LogicManager   (composition)
        EligibilityRule     abstract rule, 13 subclasses, injected (aggregation)
        DecisionAdjuster    abstract post-processor, 2 subclasses, injected
      AccessPolicy          owned by LogicManager   (composition): who is an admin
                            and which account changes are allowed
    RuleConfig              the adjustable thresholds (energy-reduction
                            percentages and the Advanced Tier tonnes), handed
                            to the rules that use them
    GrantScheme             abstract funding scheme, 4 subclasses
    SmeCriteria             the statutory SME test
    CaseBuilder / Case      turns a profile + AI audit into the facts the rules use

Open/Closed: a new rule, scheme or adjustment is a new subclass handed to the
DecisionEngine. Nothing in DecisionEngine has to change. Changing a threshold
needs no code change at all: it is a new RuleConfig.
"""

from .constants import (
    Decision,
    VALID_SCOPES,
    FAST_TRACK_MIN_PCT,
    PROVISIONAL_MIN_PCT,
    MINIMUM_IMPACT_PCT,
    EEG_ADVANCED_MIN_TONNES,
    EQUIPMENT_SUBSIDY_STATUSES,
    PASSING_STATUSES,
    FOSSIL_FUEL_LABEL,
    EFS_GREEN_NAME,
)
from .password_hasher import PasswordHasher
from .access_policy import AccessPolicy
from .rule_config import RuleConfig
from .schemes import (
    GrantScheme,
    EegAdvancedScheme,
    EegBaseScheme,
    EspScheme,
    SrgScheme,
)
from .sme_criteria import SmeCriteria
from .case import Case
from .case_builder import CaseBuilder
from .rules import (
    EligibilityRule,
    ExclusionKeywordsRule,
    FossilFuelModificationRule,
    NotAnSmeRule,
    AiFailedRule,
    ReportingWithoutFeeRule,
    ReportingGrantRule,
    MissingBaselineSpendRule,
    UnclassifiedScopeRule,
    EegAdvancedTierRule,
    EegBaseTierRule,
    EspProvisionalRule,
    BorderlineImpactRule,
    LowImpactRule,
)
from .adjusters import (
    DecisionAdjuster,
    RetrofitCostCap,
    SchemeMismatchNote,
)
from .decision_engine import DecisionEngine
from .aes_gcm_cipher import AesGcmCipher
from .logic_manager import LogicManager

__all__ = [
    "EFS_GREEN_NAME",
    "EQUIPMENT_SUBSIDY_STATUSES",
    "PASSING_STATUSES",
    "FAST_TRACK_MIN_PCT",
    "VALID_SCOPES",
    "MINIMUM_IMPACT_PCT",
    "Decision",
    "PROVISIONAL_MIN_PCT",
    "EEG_ADVANCED_MIN_TONNES",
    "FOSSIL_FUEL_LABEL",
    "PasswordHasher",
    "AccessPolicy",
    "RuleConfig",
    "GrantScheme",
    "EegAdvancedScheme",
    "EegBaseScheme",
    "EspScheme",
    "SrgScheme",
    "SmeCriteria",
    "Case",
    "CaseBuilder",
    "EligibilityRule",
    "ExclusionKeywordsRule",
    "FossilFuelModificationRule",
    "NotAnSmeRule",
    "AiFailedRule",
    "ReportingWithoutFeeRule",
    "ReportingGrantRule",
    "MissingBaselineSpendRule",
    "UnclassifiedScopeRule",
    "EegAdvancedTierRule",
    "EegBaseTierRule",
    "EspProvisionalRule",
    "BorderlineImpactRule",
    "LowImpactRule",
    "DecisionAdjuster",
    "RetrofitCostCap",
    "SchemeMismatchNote",
    "DecisionEngine",
    "AesGcmCipher",
    "LogicManager",
]
