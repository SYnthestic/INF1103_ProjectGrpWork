"""Proposal: what kind of proposal an applicant is making."""

from abc import ABC, abstractmethod
from typing import Any

from .constants import REPORTING_PROPOSAL


class Proposal(ABC):
    """What kind of proposal an applicant is making. Each kind knows which
    extra details it needs, so callers never branch on the type name."""

    COMMON_FIELDS = (
        "Company Name",
        "Company Industry",
        "Company Total Revenue",
        "Total Employees",
        "Local Equity",
        "Sustainability Grant",
        "Proposal Narrative",
    )

    @property
    @abstractmethod
    def type_name(self) -> str:
        """The label stored in the record's "Proposal Type" field."""

    @property
    @abstractmethod
    def extra_fields(self) -> tuple[str, ...]:
        """Record fields that only this kind of proposal asks for."""

    @abstractmethod
    def collect_details(self, prompts: Any) -> dict[str, float]:
        """Asks `prompts` (the I/O Manager) for this kind's extra details and
        returns all three money fields, 0.0 for the ones that do not apply."""

    @property
    def editable_fields(self) -> tuple[str, ...]:
        return self.COMMON_FIELDS + self.extra_fields

    @staticmethod
    def for_type(type_name: Any) -> "Proposal":
        """The Proposal for a stored "Proposal Type" label. Anything that is
        not the reporting type is treated as an equipment proposal."""
        # Imported here, not at the top: the subclasses import this module.
        from .equipment_proposal import EquipmentProposal
        from .reporting_proposal import ReportingProposal

        if type_name == REPORTING_PROPOSAL:
            return ReportingProposal()
        return EquipmentProposal()
