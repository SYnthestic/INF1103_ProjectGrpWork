"""EquipmentProposal."""

from typing import Any

from .constants import EQUIPMENT_PROPOSAL
from .proposal import Proposal


class EquipmentProposal(Proposal):
    @property
    def type_name(self) -> str:
        return EQUIPMENT_PROPOSAL

    @property
    def extra_fields(self) -> tuple[str, ...]:
        return ("Baseline Energy Expenditure", "Estimated Retrofit Cost")

    def collect_details(self, prompts: Any) -> dict[str, float]:
        baseline = prompts.retrieve_baseline_energy_expenditure()
        retrofit_cost = prompts.retrieve_estimated_retrofit_cost()
        return {
            "Baseline Energy Expenditure": baseline,
            "Estimated Retrofit Cost": retrofit_cost,
            "Reporting Advisory Fee": 0.0,
        }
