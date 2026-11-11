"""DecisionAdjuster: a step applied to the chosen decision after the rules
have run."""

from abc import ABC, abstractmethod

from ..constants import Decision
from ..case import Case


class DecisionAdjuster(ABC):
    """A step applied to the chosen decision after the rules have run."""

    @abstractmethod
    def adjust(self, decision: Decision, case: Case) -> None: ...
