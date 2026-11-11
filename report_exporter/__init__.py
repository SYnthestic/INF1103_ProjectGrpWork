"""PDF report export, kept out of the Data Manager so that storing records and
drawing reports are separate responsibilities.

Class overview
    ReportExporter (abstract)   contract: can you export, and export these records
      PdfReportExporter         ReportLab implementation; creates its own
                                ReportTheme for every export (composition)
    ReportContent               text helpers (no ReportLab needed)
    ReportTheme                 fonts, colours and paragraph styles

The DataManager depends on the ReportExporter abstraction, so another format
(or a test double) can be plugged in without editing the DataManager.
"""

from .constants import (
    Record,
    Records,
)
from .report_exporter import ReportExporter
from .report_content import ReportContent
from .report_theme import ReportTheme
from .pdf_report_exporter import PdfReportExporter

__all__ = [
    "Records",
    "Record",
    "ReportExporter",
    "ReportContent",
    "ReportTheme",
    "PdfReportExporter",
]
