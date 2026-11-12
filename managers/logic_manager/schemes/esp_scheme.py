"""EspScheme."""

from .grant_scheme import GrantScheme


class EspScheme(GrantScheme):
    name = "Enterprise Sustainability Programme (ESP)"
    rate = 0.50
    cap = 20_000.0
