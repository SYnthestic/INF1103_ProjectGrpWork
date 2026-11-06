"""Shared domain classes used by more than one manager.

Nothing in this module prints, reads input, touches files or calls the AI,
so every manager may import it without breaking the "managers never import
each other" rule.

    Proposal (abstract)          what kind of proposal an applicant makes
      EquipmentProposal          is-a Proposal: baseline spend + retrofit cost
      ReportingProposal          is-a Proposal: an ESG reporting/advisory fee
    ApplicationRecord            adapter around one stored application dict
    PlaceholderKeywords          words such as "none" that are not exclusions
    FileCipher (interface)       encrypts/decrypts data files
      PlainFileCipher            no encryption (used in tests)
"""

from abc import ABC, abstractmethod
from typing import Any

Record = dict[str, Any]

EQUIPMENT_PROPOSAL = "Equipment / Energy Upgrade"
REPORTING_PROPOSAL = "ESG Reporting / Advisory"


class RecordSections:
    """Safe access to the sections of a nested audit record."""

    REQUIRED = ("company_profile", "proposal", "ai_audit", "evaluation")

    @staticmethod
    def get(record: Any, section_name: str) -> dict[str, Any]:
        """The named section of a record: always a dict (empty if absent)."""
        if not isinstance(record, dict):
            return {}
        section = record.get(section_name)
        return section if isinstance(section, dict) else {}

    @classmethod
    def is_nested(cls, record: Record) -> bool:
        return all(isinstance(record.get(name), dict) for name in cls.REQUIRED)


class PlaceholderKeywords:
    """Words models write instead of an empty list ("none", "N/A", ...).
    They are not real exclusions and must never trigger an exclusion review.
    One shared definition, used by both the AI Manager and the Logic Manager."""

    _WORDS = frozenset(
        {
            "none",
            "no",
            "nil",
            "null",
            "n/a",
            "na",
            "-",
            "--",
            "not applicable",
            "none detected",
            "no exclusions",
            "no exclusion",
            "no keywords",
            "none found",
            "nothing",
            "unknown",
        }
    )

    @classmethod
    def matches(cls, text: Any) -> bool:
        lowered = str(text).strip().lower().strip(".")
        return lowered in cls._WORDS or lowered.startswith("none ")


# ---------------------------------------------------------------------------
# File encryption
# ---------------------------------------------------------------------------


class EncryptionKeyError(ValueError):
    """Key is missing or invalid. reason: missing / not_base64 / wrong_length."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class FileDecryptionError(Exception):
    """File can't be decrypted. reason: no_key, not_encrypted, damaged or wrong_key.
    The file is never changed, since the key might just be wrong."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class FileCipher(ABC):
    """Interface for encrypting data files. DataManager uses any FileCipher
    without knowing which one (polymorphism)."""

    # Header on every encrypted file, so we can tell it apart from plain JSON.
    MAGIC = b"SMEENC1"

    @property
    @abstractmethod
    def encrypts(self) -> bool: ...

    @abstractmethod
    def encrypt(self, plaintext: bytes) -> bytes:
        """Returns the bytes to save to disk."""

    @abstractmethod
    def decrypt(self, stored: bytes) -> bytes:
        """Returns the original JSON bytes. Raises FileDecryptionError."""

    @classmethod
    def is_encrypted(cls, stored: bytes) -> bool:
        return stored.startswith(cls.MAGIC)


class PlainFileCipher(FileCipher):
    """FileCipher that doesn't encrypt. Used in tests."""

    @property
    def encrypts(self) -> bool:
        return False

    def encrypt(self, plaintext: bytes) -> bytes:
        return plaintext

    def decrypt(self, stored: bytes) -> bytes:
        if self.is_encrypted(stored):
            raise FileDecryptionError(
                "no_key", "This file is encrypted, but no encryption key is in use."
            )
        return stored


# ---------------------------------------------------------------------------
# Proposals: one abstract idea, two concrete kinds
# ---------------------------------------------------------------------------


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
        if type_name == REPORTING_PROPOSAL:
            return ReportingProposal()
        return EquipmentProposal()


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


# ---------------------------------------------------------------------------
# Application records
# ---------------------------------------------------------------------------


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
