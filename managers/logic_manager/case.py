"""Case: the applicant's numbers plus the cleaned AI audit, with every
missing or malformed value already replaced by a safe default."""

from dataclasses import dataclass, field
from typing import Any

from models import EQUIPMENT_PROPOSAL


@dataclass(frozen=True)
class Case:
    """The applicant's numbers plus the cleaned AI audit, with every missing
    or malformed value already replaced by a safe default."""

    # Company
    annual_revenue: float
    headcount: int
    local_equity: float
    is_sme: bool
    sme_fail_reasons: list[str] = field(default_factory=list)
    # Proposal (self-declared by the applicant, not inferred by the AI)
    proposal_type: str = EQUIPMENT_PROPOSAL
    chosen_scheme: Any = 0
    baseline_spend: float = 0.0
    retrofit_cost: float = 0.0
    advisory_fee: float = 0.0
    # AI audit
    scope: str = "Unknown"
    energy_reduction_pct: float = 0.0
    lifetime_tonnes: float = 0.0
    exclusions: list[str] = field(default_factory=list)
    intervention: str = ""
    ai_failed: bool = False
