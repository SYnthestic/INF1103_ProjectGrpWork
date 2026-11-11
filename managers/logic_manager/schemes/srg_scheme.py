"""SrgScheme."""

from .grant_scheme import GrantScheme


class SrgScheme(GrantScheme):
    name = "Sustainability Reporting Grant (SRG)"
    rate = 0.30
    cap = 150_000.0
