"""Constants shared by the logic_manager classes."""

from typing import Any


Decision = dict[str, Any]  # what one rule returns

VALID_SCOPES = ["Scope-1", "Scope-2", "Scope-3"]

# Default energy-reduction thresholds (percent), as in the project's rule set.
# An administrator can change them at run time (see RuleConfig):
#   >= 20  Scope-1 fast-track (EEG Base Tier)
#   >= 15  provisional approval for any scope (ESP, 50% co-funding)
#   >= 10  below 15 but at least 10: referred to a person for review
#   <  10  rejected as insufficient decarbonisation yield
FAST_TRACK_MIN_PCT = 20.0
PROVISIONAL_MIN_PCT = 15.0
MINIMUM_IMPACT_PCT = 10.0
EEG_ADVANCED_MIN_TONNES = 350.0

# Decisions whose subsidy comes from the baseline energy spend (the
# reporting grant is based on the advisory fee instead).
EQUIPMENT_SUBSIDY_STATUSES = (
    "PRE_APPROVED_TIER_1",
    "PRE_APPROVED_TIER_1_ADVANCED",
    "PROVISIONAL_APPROVAL_TIER_2",
)
PASSING_STATUSES = EQUIPMENT_SUBSIDY_STATUSES + ("PRE_APPROVED_SRG",)

FOSSIL_FUEL_LABEL = "Fossil Fuel Modification"
EFS_GREEN_NAME = "Enterprise Financing Scheme – Green (EFS-Green)"
