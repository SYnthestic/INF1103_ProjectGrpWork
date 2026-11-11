"""SchemeMismatchNote: tells the applicant if they picked a different
scheme from the match."""

from typing import Any

from ..constants import Decision, PASSING_STATUSES
from ..case import Case
from .decision_adjuster import DecisionAdjuster
from ..schemes.eeg_advanced_scheme import EegAdvancedScheme
from ..schemes.eeg_base_scheme import EegBaseScheme
from ..schemes.srg_scheme import SrgScheme


class SchemeMismatchNote(DecisionAdjuster):
    """Tells the applicant if they picked a different scheme from the match.
    Informational only: the decision itself is never changed."""

    # Menu text chosen by the applicant -> the scheme name the rules produce.
    # Other choices (e.g. Enterprise Development Grant, "Others") have no
    # matching rule, so they are never flagged.
    KEYWORDS = (
        ("advanced tier", EegAdvancedScheme.name),
        ("base tier", EegBaseScheme.name),
        ("reporting", SrgScheme.name),
    )

    def note_for(self, chosen_scheme: Any, matched_schemes: list[str]) -> str | None:
        """A recommendation when the scheme the applicant picked is not the
        one the rules matched, otherwise None."""
        if not isinstance(chosen_scheme, str) or not matched_schemes:
            return None

        lowered = chosen_scheme.lower()
        for keyword, expected_scheme in self.KEYWORDS:
            if keyword in lowered:
                if expected_scheme in matched_schemes:
                    return None
                chosen_name = chosen_scheme.lstrip("0123456789. ").strip()
                return (
                    f"You selected '{chosen_name}', but this proposal matched: "
                    f"{'; '.join(matched_schemes)}. Check that you are applying "
                    "for the right scheme."
                )
        return None

    def adjust(self, decision: Decision, case: Case) -> None:
        if decision["decision_status"] in PASSING_STATUSES:
            note = self.note_for(case.chosen_scheme, decision["matched_schemes"])
            if note:
                decision["recommendations"].append(note)
