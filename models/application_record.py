"""ApplicationRecord: adapter around one stored application."""

from typing import Any

from .constants import EQUIPMENT_PROPOSAL, Record
from .proposal import Proposal
from .record_sections import RecordSections


class ApplicationRecord:
    """Adapter around one stored application.

    Records reach the program in two layouts: the flat, capitalised one the
    screens use ("Company Name", ...) and the nested one from older saves
    (company_profile / proposal / ...). This class hides the difference, so
    a file that does not match exactly shows "N/A" instead of crashing.
    The wrapped dict is never changed.
    """

    def __init__(self, raw: Any) -> None:
        self._raw: Record = raw if isinstance(raw, dict) else {}

    @classmethod
    def nested_to_flat(cls, audit_record: Record) -> Record:
        """Turns a saved (nested) audit record into the capitalised keys the
        screens use."""
        profile = RecordSections.get(audit_record, "company_profile")
        return {
            "Company Name": profile.get("company_name", ""),
            "Company Industry": profile.get("company_industry", ""),
            "Company Total Revenue": profile.get("annual_revenue_sgd", 0.0),
            "Total Employees": profile.get("group_employment_size", 0),
            "Local Equity": profile.get("local_shareholding_pct", 0.0),
            "Proposal Type": profile.get("proposal_type", ""),
            "Sustainability Grant": profile.get("sustainability_grant", ""),
            "Proposal Narrative": RecordSections.get(audit_record, "proposal").get(
                "raw_narrative", ""
            ),
            "Baseline Energy Expenditure": profile.get(
                "baseline_annual_energy_expenditure_sgd", 0.0
            ),
            "Estimated Retrofit Cost": profile.get("estimated_retrofit_cost_sgd", 0.0),
            "Reporting Advisory Fee": profile.get("reporting_advisory_fee_sgd", 0.0),
        }

    @property
    def flat(self) -> Record:
        """The record in the flat layout ({} if it was not a dict)."""
        if isinstance(self._raw.get("company_profile"), dict):
            return self.nested_to_flat(self._raw)
        return self._raw

    @property
    def company_name(self) -> str:
        return self.flat.get("Company Name") or "N/A"

    @property
    def narrative(self) -> str:
        return self.flat.get("Proposal Narrative", "")

    @property
    def proposal(self) -> Proposal:
        return Proposal.for_type(self.flat.get("Proposal Type"))

    def to_profile(self) -> dict[str, Any]:
        """The snake_case profile the Logic Manager reads."""
        record = self.flat
        return {
            "company_name": record.get("Company Name", ""),
            "company_industry": record.get("Company Industry", ""),
            "annual_revenue_sgd": record.get("Company Total Revenue", 0.0),
            "group_employment_size": record.get("Total Employees", 0),
            "local_shareholding_pct": record.get("Local Equity", 0.0),
            "proposal_type": record.get("Proposal Type", EQUIPMENT_PROPOSAL),
            "sustainability_grant": record.get("Sustainability Grant", "Not Specified"),
            "baseline_annual_energy_expenditure_sgd": record.get(
                "Baseline Energy Expenditure", 0.0
            ),
            "estimated_retrofit_cost_sgd": record.get("Estimated Retrofit Cost", 0.0),
            "reporting_advisory_fee_sgd": record.get("Reporting Advisory Fee", 0.0),
        }
