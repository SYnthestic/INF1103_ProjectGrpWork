"""EegBaseScheme."""

from .grant_scheme import GrantScheme


class EegBaseScheme(GrantScheme):
    name = "Energy Efficiency Grant (EEG) - Base Tier"
    rate = 0.70
    cap = 30_000.0
