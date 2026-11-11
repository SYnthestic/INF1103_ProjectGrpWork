"""ReportTheme: one restrained palette and one set of paragraph styles for
the whole report."""

import os
from typing import Any


class ReportTheme:
    """One restrained palette and one set of paragraph styles for the whole
    report. Outcome cards use a muted red for non-qualification, amber for
    review, and teal for a match. Needs ReportLab, so it is only created when
    a PDF is actually being built."""

    def __init__(self) -> None:
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm

        self.regular_font, self.bold_font = self._register_fonts()
        self.navy = colors.HexColor("#18324B")
        self.teal = colors.HexColor("#167C80")
        self.ink = colors.HexColor("#253746")
        self.muted = colors.HexColor("#657786")
        self.line = colors.HexColor("#D9E2E8")
        self.pale_blue = colors.HexColor("#F2F6F9")
        self.pale_teal = colors.HexColor("#E8F4F3")
        self.pale_red = colors.HexColor("#FBEDEC")
        self.red = colors.HexColor("#A33A35")
        self.pale_amber = colors.HexColor("#FFF5E3")
        self.amber = colors.HexColor("#936218")
        self.white = colors.white
        navy, ink, muted, line = self.navy, self.ink, self.muted, self.line
        regular_font, bold_font = self.regular_font, self.bold_font

        styles = getSampleStyleSheet()
        self.title = ParagraphStyle(
            "CompanyAuditTitle",
            parent=styles["Title"],
            fontName=bold_font,
            fontSize=20,
            leading=24,
            alignment=1,
            textColor=navy,
            spaceAfter=2 * mm,
        )
        self.subtitle = ParagraphStyle(
            "CompanyAuditSubtitle",
            parent=styles["Normal"],
            fontName=bold_font,
            fontSize=9,
            leading=12,
            alignment=1,
            textColor=navy,
            spaceAfter=5 * mm,
        )
        self.section = ParagraphStyle(
            "CompanyAuditSection",
            parent=styles["Heading2"],
            fontName=bold_font,
            fontSize=11,
            leading=14,
            textColor=navy,
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
            keepWithNext=True,
        )
        self.body = ParagraphStyle(
            "CompanyAuditBody",
            parent=styles["BodyText"],
            fontName=regular_font,
            fontSize=9,
            leading=13,
            textColor=ink,
            splitLongWords=True,
        )
        self.label = ParagraphStyle(
            "CompanyAuditLabel", parent=self.body, fontName=bold_font, textColor=navy
        )
        self.small = ParagraphStyle(
            "CompanyAuditSmall",
            parent=self.body,
            fontSize=8,
            leading=10,
            textColor=muted,
        )
        disclaimer = ParagraphStyle(
            "CompanyAuditDisclaimer",
            parent=self.small,
            fontName=bold_font,
            fontSize=9,
            leading=12,
        )
        self.black_small = ParagraphStyle(
            "CompanyAuditBlackSmall", parent=self.small, textColor=colors.black
        )
        self.black_disclaimer = ParagraphStyle(
            "CompanyAuditBlackDisclaimer", parent=disclaimer, textColor=colors.black
        )
        self.ai_note = ParagraphStyle(
            "CompanyAuditAINote", parent=disclaimer, textColor=colors.black
        )
        self.outcome = ParagraphStyle(
            "CompanyAuditOutcome",
            parent=self.body,
            fontName=bold_font,
            fontSize=13,
            leading=17,
            textColor=navy,
        )
        self.narrative = ParagraphStyle(
            "CompanyAuditNarrative",
            parent=self.body,
            leftIndent=3 * mm,
            rightIndent=3 * mm,
            borderColor=line,
            borderWidth=0.5,
            borderPadding=8,
            backColor=self.pale_blue,
        )
        self.summary = ParagraphStyle(
            "CompanyAuditSummary",
            parent=self.body,
            fontSize=9,
            leading=13,
            textColor=ink,
        )

    def colour(self, name: str) -> Any:
        """A palette colour by name, e.g. "red" or "pale_red"."""
        return getattr(self, name)

    @staticmethod
    def _register_fonts() -> tuple[str, str]:
        """Embed Times New Roman when available so the report keeps the
        requested typeface on other computers. In Docker, mount/provide the
        font files and set TIMES_NEW_ROMAN_FONT and TIMES_NEW_ROMAN_BOLD_FONT.
        The built-in Times fonts are the portable fallback.
        Returns (regular_font, bold_font)."""
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        regular_font = "Times-Roman"
        bold_font = "Times-Bold"
        configured_regular = os.environ.get("TIMES_NEW_ROMAN_FONT")
        configured_bold = os.environ.get("TIMES_NEW_ROMAN_BOLD_FONT")
        font_candidates = []
        if configured_regular:
            font_candidates.append((configured_regular, configured_bold))
        font_candidates.extend(
            [
                (r"C:\Windows\Fonts\times.ttf", r"C:\Windows\Fonts\timesbd.ttf"),
                (
                    "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf",
                    "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf",
                ),
                (
                    "/Library/Fonts/Times New Roman.ttf",
                    "/Library/Fonts/Times New Roman Bold.ttf",
                ),
            ]
        )
        for regular_path, bold_path in font_candidates:
            if regular_path and os.path.isfile(regular_path):
                pdfmetrics.registerFont(TTFont("CompanyAudit", regular_path))
                regular_font = "CompanyAudit"
                if bold_path and os.path.isfile(bold_path):
                    pdfmetrics.registerFont(TTFont("CompanyAudit-Bold", bold_path))
                    bold_font = "CompanyAudit-Bold"
                else:
                    bold_font = regular_font
                break
        return regular_font, bold_font
