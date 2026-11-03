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

import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from typing import Any

from models import RecordSections

Record = dict[str, Any]
Records = list[Record]


class ReportExporter(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        """True when everything the exporter needs is installed."""

    @abstractmethod
    def export(self, records: Records, output_path: str) -> None:
        """Writes the report for `records` to `output_path`. Raises on failure."""


class ReportContent:
    """Turns stored values into reader-facing wording. Pure text: no ReportLab."""

    LABEL_NAMES = {
        "company_name": "Company name",
        "company_industry": "Industry",
        "annual_revenue_sgd": "Annual revenue",
        "group_employment_size": "Group employees",
        "local_shareholding_pct": "Local shareholding",
        "proposal_type": "Proposal type",
        "sustainability_grant": "Sustainability Grant",
        "baseline_annual_energy_expenditure_sgd": "Annual energy expenditure",
        "estimated_retrofit_cost_sgd": "Estimated retrofit cost",
        "reporting_advisory_fee_sgd": "Reporting advisory fee",
        "scope_category": "Emissions scope",
        "primary_intervention_type": "Main intervention",
        "estimated_energy_reduction_pct": "Estimated energy reduction",
        "estimated_lifetime_abatement_tonnes": "Estimated lifetime abatement",
        "detected_exclusion_keywords": "Potential exclusions",
        "implementation_bottleneck": "Implementation constraint",
        "ai_reasoning_summary": "AI-generated proposal analysis",
        "approved_subsidy_sgd": "Potential grant amount",
        "audit_passed": "Screening result",
        "is_sme": "Meets SME criteria",
        "created_at": "Assessment date",
        "raw_narrative": "Proposal narrative",
    }

    STATUS_LABELS = {
        "REJECT_NON_SME": "Did not qualify - company criteria",
        "REJECT_LOW_IMPACT": "Did not qualify - impact threshold",
        "PRE_APPROVED_SRG": "Potential match - reporting grant",
        "PRE_APPROVED_TIER_1": "Potential match - base tier",
        "PRE_APPROVED_TIER_1_ADVANCED": "Potential match - advanced tier",
        "PROVISIONAL_APPROVAL_TIER_2": "Potential match - provisional",
        "MANUAL_REVIEW": "Further review required",
        "MANUAL_EXCLUSION_REVIEW": "Further review required - potential exclusion",
    }

    MONEY_TERMS = (
        "_sgd",
        "revenue",
        "cost",
        "fee",
        "expenditure",
        "subsidy",
        "grant amount",
    )

    @classmethod
    def nice_label(cls, value: Any) -> str:
        key = str(value)
        return cls.LABEL_NAMES.get(key, key.replace("_", " ").strip().capitalize())

    @classmethod
    def readable_value(cls, value: Any, key: str = "") -> str:
        """Format common values as prose, never as JSON source text."""
        if value is None or value == "":
            return "Not provided"
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, (int, float)):
            lowered = str(key).lower()
            if any(term in lowered for term in cls.MONEY_TERMS):
                return f"SGD {value:,.2f}"
            if "pct" in lowered or "percent" in lowered:
                return f"{value:,.1f}%"
            if "tonne" in lowered:
                return f"{value:,.1f} tonnes CO2e"
            return f"{value:,}" if isinstance(value, int) else f"{value:,.2f}"
        if isinstance(value, list):
            return (
                "\n".join(f"- {cls.readable_value(item)}" for item in value)
                if value
                else "None recorded"
            )
        if isinstance(value, dict):
            return "\n".join(
                f"{cls.nice_label(item_key)}: {cls.readable_value(item_value, item_key)}"
                for item_key, item_value in value.items()
            )
        text = str(value)
        if str(key).lower().replace(" ", "_") == "decision_status":
            return cls.STATUS_LABELS.get(text, text.replace("_", " ").title())
        return text

    @staticmethod
    def outcome_for(evaluation: dict[str, Any]) -> tuple[str, str, str]:
        """Returns (headline, colour name, explanation) for the outcome panel.
        The colour name is looked up in the report theme."""
        status = str(evaluation.get("decision_status", ""))
        if status.startswith("MANUAL"):
            return (
                "Further review required",
                "amber",
                "The screening identified an item that needs review before an eligibility conclusion can be made.",
            )
        if status.startswith("REJECT"):
            return (
                "Did not qualify under this screening",
                "red",
                "The recorded assessment did not meet the current screening criteria. See the reasons and next steps below.",
            )
        if evaluation.get("audit_passed") is True:
            return (
                "Potential grant match identified",
                "teal",
                "The initial screening found a potential match. Final eligibility and funding remain subject to the grant administrator's review.",
            )
        return (
            "No positive eligibility result recorded",
            "amber",
            "The saved assessment does not record a positive eligibility result. Review the details below.",
        )

    @staticmethod
    def screening_result_for(evaluation: dict[str, Any]) -> str:
        """Translate the logic status into a clear reader-facing outcome."""
        status = str(evaluation.get("decision_status", "")).upper()
        if status.startswith("MANUAL"):
            return "Further review required"
        if status.startswith("REJECT"):
            return "Did not qualify"
        if evaluation.get("audit_passed") is True:
            return "Passed"
        if not status:
            return "Not recorded"
        # An unfamiliar or incomplete status should not be presented as
        # a rejection or a pass; route it to review in the report wording.
        return "Further review required"

    @staticmethod
    def report_sections(
        record: Record, index: int
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Any, Any]:
        """Returns (profile, proposal, ai_audit, evaluation, record_id,
        created_at) for either record layout (nested audit record or the flat
        menu record)."""
        if RecordSections.is_nested(record):
            return (
                RecordSections.get(record, "company_profile"),
                RecordSections.get(record, "proposal"),
                RecordSections.get(record, "ai_audit"),
                RecordSections.get(record, "evaluation"),
                record.get("audit_id", index + 1),
                record.get("created_at", ""),
            )
        profile = {
            "company_name": record.get("Company Name", ""),
            "company_industry": record.get("Company Industry", ""),
            "annual_revenue_sgd": record.get("Company Total Revenue", 0.0),
            "group_employment_size": record.get("Total Employees", 0),
            "local_shareholding_pct": record.get("Local Equity", 0.0),
            "proposal_type": record.get("Proposal Type", ""),
            "sustainability_grant": record.get("Sustainability Grant", ""),
            "baseline_annual_energy_expenditure_sgd": record.get(
                "Baseline Energy Expenditure", 0.0
            ),
            "estimated_retrofit_cost_sgd": record.get("Estimated Retrofit Cost", 0.0),
            "reporting_advisory_fee_sgd": record.get("Reporting Advisory Fee", 0.0),
        }
        proposal = {"raw_narrative": record.get("Proposal Narrative", "")}
        ai_audit = record.get("AI Audit", {})
        evaluation = record.get("Grant Decision", {})
        if not isinstance(ai_audit, dict):
            ai_audit = {}
        if not isinstance(evaluation, dict):
            evaluation = {}
        return (
            profile,
            proposal,
            ai_audit,
            evaluation,
            record.get("Audit ID", index + 1),
            record.get("Created At", ""),
        )

    @staticmethod
    def company_name(records: Records) -> str:
        """The name printed in the page footer (taken from the first record)."""
        name = "the named company"
        if records:
            first = records[0]
            if RecordSections.is_nested(first):
                name = str(
                    RecordSections.get(first, "company_profile").get("company_name")
                    or name
                ).strip()
            else:
                name = str(first.get("Company Name") or name).strip()
        return name

    @staticmethod
    def assessment_date_time(created_at: Any) -> tuple[str, str]:
        try:
            moment = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            return moment.strftime("%Y-%m-%d"), moment.strftime("%H:%M:%S")
        except (TypeError, ValueError):
            return "Not recorded", "Not recorded"


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


class PdfReportExporter(ReportExporter):
    """Lays out the company-facing assessment report with ReportLab."""

    def __init__(self) -> None:
        self._theme: ReportTheme | None = None

    def is_available(self) -> bool:
        try:
            import reportlab  # noqa: F401
            import reportlab.platypus  # noqa: F401
        except ImportError:
            return False
        return True

    # ----- small building blocks -----
    def _para(self, value: Any, style: Any = None) -> Any:
        from reportlab.platypus import Paragraph
        from xml.sax.saxutils import escape

        safe = escape(str(value)).replace("\r\n", "\n").replace("\r", "\n")
        return Paragraph(safe.replace("\n", "<br/>"), style or self._theme.body)

    def _heading(self, text: str) -> Any:
        from reportlab.platypus import Paragraph
        from xml.sax.saxutils import escape

        return Paragraph(escape(text), self._theme.section)

    def _add_detail_table(self, story: list[Any], items: list[tuple[str, Any]]) -> None:
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import Spacer, Table, TableStyle

        theme = self._theme
        if not items:
            story.append(
                self._para("No information was recorded for this section.", theme.small)
            )
            return
        rows = [
            [
                self._para(ReportContent.nice_label(key), theme.label),
                self._para(ReportContent.readable_value(value, key), theme.body),
            ]
            for key, value in items
        ]
        table = Table(rows, colWidths=[53 * mm, 117 * mm], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), theme.pale_blue),
                    (
                        "ROWBACKGROUNDS",
                        (1, 0),
                        (1, -1),
                        [theme.white, colors.HexColor("#FAFBFC")],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.35, theme.line),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.extend([table, Spacer(1, 2 * mm)])

    def _add_bullets(
        self, story: list[Any], heading: str, items: Any, color: Any = None
    ) -> None:
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm

        if not items:
            return
        story.append(self._heading(heading))
        if not isinstance(items, list):
            items = [items]
        bullet_style = ParagraphStyle(
            "CompanyAuditBullet",
            parent=self._theme.body,
            leftIndent=5 * mm,
            firstLineIndent=-3 * mm,
            textColor=color or self._theme.ink,
            spaceAfter=2,
        )
        for item in items:
            story.append(self._para(f"- {ReportContent.readable_value(item)}", bullet_style))

    def _add_outcome_panel(self, story: list[Any], evaluation: dict[str, Any]) -> str:
        """Adds the coloured outcome box and disclaimer. Returns the headline."""
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
        from xml.sax.saxutils import escape

        theme = self._theme
        headline, colour_name, explanation = ReportContent.outcome_for(evaluation)
        outcome_color = theme.colour(colour_name)
        outcome_bg = theme.colour("pale_" + colour_name)
        coloured_style = ParagraphStyle(
            "CompanyAuditOutcomeColored", parent=theme.outcome, textColor=outcome_color
        )
        panel = Table(
            [
                [Paragraph(escape(headline), coloured_style)],
                [self._para(explanation, theme.summary)],
            ],
            colWidths=[170 * mm],
            hAlign="LEFT",
        )
        panel.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), outcome_bg),
                    ("BOX", (0, 0), (-1, -1), 0.8, outcome_color),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.extend([panel, Spacer(1, 2 * mm)])
        story.append(
            self._para(
                "This is a preliminary automated screening report, not an official grant decision or funding offer.",
                theme.black_disclaimer,
            )
        )
        return headline

    def _add_ai_section(self, story: list[Any], ai_audit: dict[str, Any]) -> None:
        from reportlab.lib.units import mm
        from reportlab.platypus import Spacer

        theme = self._theme
        story.append(self._heading("AI-generated scope and impact analysis"))
        story.append(
            self._para(
                "Supporting analysis generated by AI from the proposal description. "
                "It does not determine grant eligibility; the Logic Manager applies "
                "the programmed rules shown in the eligibility assessment above.",
                theme.ai_note,
            )
        )
        story.append(Spacer(1, 3 * mm))
        self._add_detail_table(
            story,
            [
                (key, value)
                for key, value in ai_audit.items()
                if key != "ai_reasoning_summary"
            ],
        )
        if ai_audit.get("ai_reasoning_summary"):
            story.append(self._para("AI-generated proposal summary", theme.label))
            story.append(self._para(ai_audit["ai_reasoning_summary"], theme.body))

    def _add_record_pages(self, story: list[Any], record: Record, index: int) -> None:
        """Adds the pages for one audit record: summary page, then AI analysis."""
        from reportlab.lib.units import mm
        from reportlab.platypus import PageBreak, Paragraph, Spacer

        theme = self._theme
        profile, proposal, ai_audit, evaluation, record_id, created_at = (
            ReportContent.report_sections(record, index)
        )

        story.extend(
            [
                Spacer(1, 4 * mm),
                Paragraph("GREEN GRANT ELIGIBILITY ASSESSMENT", theme.title),
                Paragraph("Company audit report", theme.subtitle),
            ]
        )
        story.append(
            self._heading(str(profile.get("company_name") or "Company name not recorded"))
        )

        assessment_date, assessment_time = ReportContent.assessment_date_time(created_at)
        story.append(self._para(f"Assessment ID: {record_id}", theme.black_small))
        story.append(
            self._para(f"Date: {assessment_date} (YYYY-MM-DD)", theme.black_small)
        )
        story.append(self._para(f"Time: {assessment_time}", theme.black_small))
        story.append(Spacer(1, 3 * mm))

        headline = self._add_outcome_panel(story, evaluation)

        story.append(self._heading("Logic Manager eligibility assessment"))
        self._add_detail_table(
            story,
            [
                ("Decision status", evaluation.get("decision_status", "Not recorded")),
                ("Meets SME criteria", evaluation.get("is_sme", "Not recorded")),
                ("Potential grant amount", evaluation.get("approved_subsidy_sgd", 0)),
                ("Screening outcome", ReportContent.screening_result_for(evaluation)),
            ],
        )

        story.append(self._heading("Company profile"))
        self._add_detail_table(story, list(profile.items()))

        story.append(self._heading("Proposal"))
        story.append(Spacer(1, 3 * mm))
        narrative = proposal.get("raw_narrative", "")
        if narrative:
            story.append(self._para(narrative, theme.narrative))
        else:
            story.append(self._para("No proposal narrative was recorded.", theme.small))
        other_proposal = [
            (key, value) for key, value in proposal.items() if key != "raw_narrative"
        ]
        if other_proposal:
            story.append(Spacer(1, 2 * mm))
            self._add_detail_table(story, other_proposal)

        story.append(PageBreak())
        self._add_ai_section(story, ai_audit)

        did_not_qualify = headline.startswith("Did not qualify")
        reasons = evaluation.get("reasons", [])
        if not reasons and did_not_qualify:
            reasons = ["No detailed reason was recorded in the saved assessment."]
        self._add_bullets(
            story,
            "Why this result was reached",
            reasons,
            color=theme.red if did_not_qualify else theme.ink,
        )
        self._add_bullets(
            story, "Recommended next steps", evaluation.get("recommendations", [])
        )
        self._add_bullets(
            story, "Potentially matched grants", evaluation.get("matched_schemes", [])
        )

        other_evaluation = [
            (key, value)
            for key, value in evaluation.items()
            if key
            not in {
                "decision_status",
                "approved_subsidy_sgd",
                "audit_passed",
                "is_sme",
                "reasons",
                "recommendations",
                "matched_schemes",
            }
        ]
        if other_evaluation:
            story.append(self._heading("Additional assessment details"))
            self._add_detail_table(story, other_evaluation)

    def _make_page_chrome(self, company_name: str) -> Callable[[Any, Any], None]:
        """Returns the function ReportLab calls to draw each page's header bar
        and footer."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics

        theme = self._theme
        regular_font = theme.regular_font

        def draw_page_chrome(canvas: Any, doc: Any) -> None:
            canvas.saveState()
            canvas.setFillColor(theme.navy)
            canvas.rect(0, A4[1] - 5 * mm, A4[0], 5 * mm, fill=1, stroke=0)
            canvas.setStrokeColor(theme.line)
            canvas.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
            canvas.setFont(regular_font, 8)
            canvas.setFillColor(colors.black)
            footer_company_name = company_name
            footer_text = f"CONFIDENTIAL | Prepared for {footer_company_name}"
            max_footer_width = A4[0] - 50 * mm
            while (
                footer_text
                and pdfmetrics.stringWidth(footer_text, regular_font, 8)
                > max_footer_width
            ):
                footer_company_name = (
                    footer_company_name[:-4] + "..."
                    if len(footer_company_name) > 4
                    else "..."
                )
                footer_text = f"CONFIDENTIAL | Prepared for {footer_company_name}"
            canvas.drawString(20 * mm, 10 * mm, footer_text)
            canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {doc.page}")
            canvas.restoreState()

        return draw_page_chrome

    def export(self, records: Records, output_path: str) -> None:
        """Lays out the whole report and writes it to output_path."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

        self._theme = ReportTheme()  # owned by this export run
        theme = self._theme
        document = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=20 * mm,
            leftMargin=20 * mm,
            topMargin=14 * mm,
            bottomMargin=22 * mm,
            title="Company Green Grant Eligibility Assessment",
            author="SME Green Grant Eligibility Auditor",
        )
        story: list[Any] = []
        if not records:
            story.extend(
                [
                    Spacer(1, 5 * mm),
                    Paragraph("GREEN GRANT ELIGIBILITY ASSESSMENT", theme.title),
                    Paragraph("Company audit report", theme.subtitle),
                    self._para("No audit records were found in the selected JSON file."),
                ]
            )
        for index, record in enumerate(records):
            if index:
                story.append(PageBreak())
            self._add_record_pages(story, record, index)

        chrome = self._make_page_chrome(ReportContent.company_name(records))
        document.build(story, onFirstPage=chrome, onLaterPages=chrome)
