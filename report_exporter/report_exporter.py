"""ReportExporter."""

from abc import ABC, abstractmethod

from .constants import Records


class ReportExporter(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        """True when everything the exporter needs is installed."""

    @abstractmethod
    def export(self, records: Records, output_path: str) -> None:
        """Writes the report for `records` to `output_path`. Raises on failure."""
