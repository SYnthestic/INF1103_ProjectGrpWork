"""PdfReportExporter: lays out the company-facing assessment report with
ReportLab."""

from collections.abc import Callable
from typing import Any

from .constants import Record, Records
from .report_content import ReportContent
from .report_exporter import ReportExporter
from .report_theme import ReportTheme


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
