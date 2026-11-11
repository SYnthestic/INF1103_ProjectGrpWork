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

from .constants import (
    Record,
    EQUIPMENT_PROPOSAL,
    REPORTING_PROPOSAL,
)
from .record_sections import RecordSections
from .placeholder_keywords import PlaceholderKeywords
from .encryption_key_error import EncryptionKeyError
from .file_decryption_error import FileDecryptionError
from .file_cipher import FileCipher
from .plain_file_cipher import PlainFileCipher
from .proposal import Proposal
from .equipment_proposal import EquipmentProposal
from .reporting_proposal import ReportingProposal
from .application_record import ApplicationRecord

__all__ = [
    "REPORTING_PROPOSAL",
    "EQUIPMENT_PROPOSAL",
    "Record",
    "RecordSections",
    "PlaceholderKeywords",
    "EncryptionKeyError",
    "FileDecryptionError",
    "FileCipher",
    "PlainFileCipher",
    "Proposal",
    "EquipmentProposal",
    "ReportingProposal",
    "ApplicationRecord",
]
