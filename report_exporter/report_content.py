"""ReportContent: turns stored values into reader-facing wording."""

from datetime import datetime
from typing import Any

from models import RecordSections
from .constants import Record, Records


class ReportContent:
    """Turns stored values into reader-facing wording. Pure text: no ReportLab."""

    LABEL_NAMES = {
        "company_name": "Company name",
        "company_industry": "Industry",
        "annual_revenue_sgd": "Annual revenue",
        "group_employment_size": "Group employees",
        "local_shareholding_pct": "Local shareholding",
        "proposal_type": "Proposal type",
        "sustainability_grant": "Sustainability Grant",
        "baseline_annual_energy_expenditure_sgd": "Annual energy expenditure",
        "estimated_retrofit_cost_sgd": "Estimated retrofit cost",
        "reporting_advisory_fee_sgd": "Reporting advisory fee",
        "scope_category": "Emissions scope",
        "primary_intervention_type": "Main intervention",
        "estimated_energy_reduction_pct": "Estimated energy reduction",
        "estimated_lifetime_abatement_tonnes": "Estimated lifetime abatement",
        "detected_exclusion_keywords": "Potential exclusions",
        "implementation_bottleneck": "Implementation constraint",
        "ai_reasoning_summary": "AI-generated proposal analysis",
        "approved_subsidy_sgd": "Potential grant amount",
        "audit_passed": "Screening result",
        "is_sme": "Meets SME criteria",
        "created_at": "Assessment date",
        "raw_narrative": "Proposal narrative",
    }

    STATUS_LABELS = {
        "REJECT_NON_SME": "Did not qualify - company criteria",
        "REJECT_LOW_IMPACT": "Did not qualify - impact threshold",
        "PRE_APPROVED_SRG": "Potential match - reporting grant",
        "PRE_APPROVED_TIER_1": "Potential match - base tier",
        "PRE_APPROVED_TIER_1_ADVANCED": "Potential match - advanced tier",
        "PROVISIONAL_APPROVAL_TIER_2": "Potential match - provisional",
        "MANUAL_REVIEW": "Further review required",
        "MANUAL_EXCLUSION_REVIEW": "Further review required - potential exclusion",
    }

    MONEY_TERMS = (
        "_sgd",
        "revenue",
        "cost",
        "fee",
        "expenditure",
        "subsidy",
        "grant amount",
    )

    @classmethod
    def nice_label(cls, value: Any) -> str:
        key = str(value)
        return cls.LABEL_NAMES.get(key, key.replace("_", " ").strip().capitalize())

    @classmethod
    def readable_value(cls, value: Any, key: str = "") -> str:
        """Format common values as prose, never as JSON source text."""
        if value is None or value == "":
            return "Not provided"
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, (int, float)):
            lowered = str(key).lower()
            if any(term in lowered for term in cls.MONEY_TERMS):
                return f"SGD {value:,.2f}"
            if "pct" in lowered or "percent" in lowered:
                return f"{value:,.1f}%"
            if "tonne" in lowered:
                return f"{value:,.1f} tonnes CO2e"
            return f"{value:,}" if isinstance(value, int) else f"{value:,.2f}"
        if isinstance(value, list):
            return (
                "\n".join(f"- {cls.readable_value(item)}" for item in value)
                if value
                else "None recorded"
            )
        if isinstance(value, dict):
            return "\n".join(
                f"{cls.nice_label(item_key)}: {cls.readable_value(item_value, item_key)}"
                for item_key, item_value in value.items()
            )
        text = str(value)
        if str(key).lower().replace(" ", "_") == "decision_status":
            return cls.STATUS_LABELS.get(text, text.replace("_", " ").title())
        return text

    @staticmethod
    def outcome_for(evaluation: dict[str, Any]) -> tuple[str, str, str]:
        """Returns (headline, colour name, explanation) for the outcome panel.
        The colour name is looked up in the report theme."""
        status = str(evaluation.get("decision_status", ""))
        if status.startswith("MANUAL"):
            return (
                "Further review required",
                "amber",
                "The screening identified an item that needs review before an eligibility conclusion can be made.",
            )
        if status.startswith("REJECT"):
            return (
                "Did not qualify under this screening",
                "red",
                "The recorded assessment did not meet the current screening criteria. See the reasons and next steps below.",
            )
        if evaluation.get("audit_passed") is True:
            return (
                "Potential grant match identified",
                "teal",
                "The initial screening found a potential match. Final eligibility and funding remain subject to the grant administrator's review.",
            )
        return (
            "No positive eligibility result recorded",
            "amber",
            "The saved assessment does not record a positive eligibility result. Review the details below.",
        )

    @staticmethod
    def screening_result_for(evaluation: dict[str, Any]) -> str:
        """Translate the logic status into a clear reader-facing outcome."""
        status = str(evaluation.get("decision_status", "")).upper()
        if status.startswith("MANUAL"):
            return "Further review required"
        if status.startswith("REJECT"):
            return "Did not qualify"
        if evaluation.get("audit_passed") is True:
            return "Passed"
        if not status:
            return "Not recorded"
        # An unfamiliar or incomplete status should not be presented as
        # a rejection or a pass; route it to review in the report wording.
        return "Further review required"

    @staticmethod
    def report_sections(
        record: Record, index: int
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Any, Any]:
        """Returns (profile, proposal, ai_audit, evaluation, record_id,
        created_at) for either record layout (nested audit record or the flat
        menu record)."""
        if RecordSections.is_nested(record):
            return (
                RecordSections.get(record, "company_profile"),
                RecordSections.get(record, "proposal"),
                RecordSections.get(record, "ai_audit"),
                RecordSections.get(record, "evaluation"),
                record.get("audit_id", index + 1),
                record.get("created_at", ""),
            )
        profile = {
            "company_name": record.get("Company Name", ""),
            "company_industry": record.get("Company Industry", ""),
            "annual_revenue_sgd": record.get("Company Total Revenue", 0.0),
            "group_employment_size": record.get("Total Employees", 0),
            "local_shareholding_pct": record.get("Local Equity", 0.0),
            "proposal_type": record.get("Proposal Type", ""),
            "sustainability_grant": record.get("Sustainability Grant", ""),
            "baseline_annual_energy_expenditure_sgd": record.get(
                "Baseline Energy Expenditure", 0.0
            ),
            "estimated_retrofit_cost_sgd": record.get("Estimated Retrofit Cost", 0.0),
            "reporting_advisory_fee_sgd": record.get("Reporting Advisory Fee", 0.0),
        }
        proposal = {"raw_narrative": record.get("Proposal Narrative", "")}
        ai_audit = record.get("AI Audit", {})
        evaluation = record.get("Grant Decision", {})
        if not isinstance(ai_audit, dict):
            ai_audit = {}
        if not isinstance(evaluation, dict):
            evaluation = {}
        return (
            profile,
            proposal,
            ai_audit,
            evaluation,
            record.get("Audit ID", index + 1),
            record.get("Created At", ""),
        )

    @staticmethod
    def company_name(records: Records) -> str:
        """The name printed in the page footer (taken from the first record)."""
        name = "the named company"
        if records:
            first = records[0]
            if RecordSections.is_nested(first):
                name = str(
                    RecordSections.get(first, "company_profile").get("company_name")
                    or name
                ).strip()
            else:
                name = str(first.get("Company Name") or name).strip()
        return name

    @staticmethod
    def assessment_date_time(created_at: Any) -> tuple[str, str]:
        try:
            moment = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            return moment.strftime("%Y-%m-%d"), moment.strftime("%H:%M:%S")
        except (TypeError, ValueError):
            return "Not recorded", "Not recorded"
