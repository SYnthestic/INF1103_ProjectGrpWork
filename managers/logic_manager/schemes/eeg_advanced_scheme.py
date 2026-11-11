"""EegAdvancedScheme."""

from .grant_scheme import GrantScheme


class EegAdvancedScheme(GrantScheme):
    name = "Energy Efficiency Grant (EEG) - Advanced Tier"
    rate = 0.70
    cap = 350_000.0
