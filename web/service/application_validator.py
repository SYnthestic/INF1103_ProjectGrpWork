"""ApplicationValidator: the same limits as the terminal prompts
(IOManager.retrieve_*): Company Total Revenue above 0 Total Employees a whole number above 0 Local Equity above 0 and at most 100 money fields 0 or more when given."""

import math
from typing import Any

from managers.io_manager import InputValidator, IOManager
from models import REPORTING_PROPOSAL


class ApplicationValidator:
    """The same limits as the terminal prompts (IOManager.retrieve_*):

        Company Total Revenue   above 0
        Total Employees         a whole number above 0
        Local Equity            above 0 and at most 100
        money fields            0 or more when given
    """

    REQUIRED_TEXT = ("Company Name", "Company Industry", "Proposal Narrative")
    MONEY_FIELDS = (
        "Baseline Energy Expenditure",
        "Estimated Retrofit Cost",
        "Reporting Advisory Fee",
    )
    # Which money fields each kind of proposal asks for (the others are 0), as
    # in the terminal's EquipmentProposal / ReportingProposal.
    REPORTING_MONEY = ("Reporting Advisory Fee",)
    EQUIPMENT_MONEY = ("Baseline Energy Expenditure", "Estimated Retrofit Cost")

    def __init__(
        self,
        name_max_len: int = IOManager.COMPANY_NAME_MAX_LEN,
        narrative_max_len: int = IOManager.NARRATIVE_MAX_LEN,
    ) -> None:
        self._name_max_len = name_max_len
        self._narrative_max_len = narrative_max_len

    @staticmethod
    def form_number(text: Any) -> float | None:
        """A typed form value as a finite number, or None. Uses the terminal's
        finite_float, so "nan", "inf" and "1e309" (which float() accepts) are
        refused, while ordinary forms such as "1e5" still work."""
        if not isinstance(text, str):
            return None
        try:
            return InputValidator.finite_float(text.strip())
        except ValueError:
            return None

    @staticmethod
    def is_number(value: Any) -> bool:
        """A real, finite number (JSON can carry NaN and Infinity, and True is
        an int in Python, so a plain isinstance check is not enough)."""
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
        )

    @classmethod
    def money_fields_for(cls, proposal_type: Any) -> tuple[str, ...]:
        if proposal_type == REPORTING_PROPOSAL:
            return cls.REPORTING_MONEY
        return cls.EQUIPMENT_MONEY

    def problem(self, record: Any, strict_costs: bool = False) -> str | None:
        """Error message, or None if acceptable. strict_costs (the web forms)
        also requires, like the terminal, a baseline energy spend and retrofit
        cost above 0 for equipment proposals. The JSON API leaves them
        optional; a missing baseline then goes to manual review."""
        if not isinstance(record, dict):
            return "JSON object required"
        for key in self.REQUIRED_TEXT:
            value = record.get(key)
            if not isinstance(value, str) or not value.strip():
                return f"{key} is required"
        if len(record["Company Name"]) > self._name_max_len:
            return f"Company Name must be at most {self._name_max_len} characters"
        if len(record["Proposal Narrative"]) > self._narrative_max_len:
            return f"Proposal Narrative must be at most {self._narrative_max_len} characters"

        revenue = record.get("Company Total Revenue")
        if not self.is_number(revenue) or revenue <= 0:
            return "Company Total Revenue must be a number above 0"
        employees = record.get("Total Employees")
        if not self.is_number(employees) or employees <= 0 or employees != int(employees):
            return "Total Employees must be a whole number above 0"
        equity = record.get("Local Equity")
        if not self.is_number(equity) or not 0 < equity <= 100:
            return "Local Equity must be between 0 and 100 (above 0)"

        for key in self.MONEY_FIELDS:
            if key in record and not (self.is_number(record[key]) and record[key] >= 0):
                return f"{key} must be a number of 0 or more"
        if strict_costs:
            for key in self.money_fields_for(record.get("Proposal Type")):
                if key != "Reporting Advisory Fee" and not record.get(key, 0) > 0:
                    return f"{key} must be above 0 for an equipment proposal"
        return None
