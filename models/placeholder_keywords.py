"""PlaceholderKeywords: words models write instead of an empty list
("none", "N/A", ...)."""

from typing import Any


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
