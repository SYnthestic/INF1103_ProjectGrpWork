"""GrantScheme: a funding scheme: a co-funding rate and a maximum subsidy
in SGD."""

from abc import ABC, abstractmethod


class GrantScheme(ABC):
    """A funding scheme: a co-funding rate and a maximum subsidy in SGD."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def rate(self) -> float: ...

    @property
    @abstractmethod
    def cap(self) -> float: ...

    def calculate_subsidy(self, base_amount: float) -> float:
        """rate x base_amount, limited to the cap. Deterministic, no AI."""
        return round(min(base_amount * self.rate, self.cap), 2)
