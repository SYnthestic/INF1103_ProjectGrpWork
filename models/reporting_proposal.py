"""ReportingProposal."""

from typing import Any

from .constants import REPORTING_PROPOSAL
from .proposal import Proposal


class ReportingProposal(Proposal):
    @property
    def type_name(self) -> str:
        return REPORTING_PROPOSAL

    @property
    def extra_fields(self) -> tuple[str, ...]:
        return ("Reporting Advisory Fee",)

    def collect_details(self, prompts: Any) -> dict[str, float]:
        return {
            "Baseline Energy Expenditure": 0.0,
            "Estimated Retrofit Cost": 0.0,
            "Reporting Advisory Fee": prompts.retrieve_reporting_advisory_fee(),
        }
