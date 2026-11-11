"""RuleConfig: the thresholds the eligibility rules use."""

import math
from dataclasses import dataclass
from typing import Any

from .constants import (
    EEG_ADVANCED_MIN_TONNES,
    FAST_TRACK_MIN_PCT,
    MINIMUM_IMPACT_PCT,
    PROVISIONAL_MIN_PCT,
)


@dataclass(frozen=True)
class RuleConfig:
    """The thresholds the eligibility rules use. Frozen, so a rule can never
    change them; a new set of values is a new RuleConfig, checked by
    from_dict() before it is used."""

    minimum_impact_pct: float = MINIMUM_IMPACT_PCT
    provisional_min_pct: float = PROVISIONAL_MIN_PCT
    fast_track_min_pct: float = FAST_TRACK_MIN_PCT
    eeg_advanced_min_tonnes: float = EEG_ADVANCED_MIN_TONNES

    # Field name -> (label shown to the admin, unit). Also fixes the order.
    LABELS = {
        "minimum_impact_pct": ("Minimum energy reduction (below = reject)", "%"),
        "provisional_min_pct": ("Provisional approval (ESP) from", "%"),
        "fast_track_min_pct": ("Scope-1 fast track (EEG Base Tier) from", "%"),
        "eeg_advanced_min_tonnes": ("EEG Advanced Tier: lifetime abatement above", "tonnes"),
    }
    MAX_TONNES = 1_000_000.0

    def to_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in self.LABELS}

    @classmethod
    def problems(cls, values: Any) -> list[str]:
        """Everything wrong with a proposed set of thresholds (empty if fine)."""
        if not isinstance(values, dict):
            return ["The rule settings must be a set of named values."]
        found = []
        numbers: dict[str, float] = {}
        for name, (label, _) in cls.LABELS.items():
            value = values.get(name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                found.append(f"{label}: must be a number.")
            else:
                numbers[name] = float(value)
        unknown = sorted(set(values) - set(cls.LABELS))
        if unknown:
            found.append(f"Unknown setting(s): {', '.join(map(str, unknown))}.")
        if found:
            return found

        for name in ("minimum_impact_pct", "provisional_min_pct", "fast_track_min_pct"):
            if not 0 < numbers[name] <= 100:
                found.append(f"{cls.LABELS[name][0]}: must be above 0 and at most 100.")
        if not 0 < numbers["eeg_advanced_min_tonnes"] <= cls.MAX_TONNES:
            found.append(
                f"{cls.LABELS['eeg_advanced_min_tonnes'][0]}: must be above 0 "
                f"and at most {cls.MAX_TONNES:,.0f}."
            )
        if not (
            numbers["minimum_impact_pct"]
            <= numbers["provisional_min_pct"]
            <= numbers["fast_track_min_pct"]
        ):
            found.append(
                "The percentages must not decrease: minimum <= provisional <= fast track."
            )
        return found

    @classmethod
    def from_dict(cls, values: Any) -> "RuleConfig":
        """A checked RuleConfig. Raises ValueError listing every problem."""
        found = cls.problems(values)
        if found:
            raise ValueError(" ".join(found))
        return cls(**{name: float(values[name]) for name in cls.LABELS})

    def with_value(self, name: str, value: float) -> "RuleConfig":
        """A copy with one threshold changed, checked like from_dict()."""
        if name not in self.LABELS:
            raise ValueError(f"Unknown setting '{name}'.")
        values = self.to_dict()
        values[name] = value
        return self.from_dict(values)
