"""RecordSections: safe access to the sections of a nested audit record."""

from typing import Any

from .constants import Record


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
