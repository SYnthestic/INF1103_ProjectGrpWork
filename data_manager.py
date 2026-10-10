import json
import logging
import os
import re
from datetime import datetime

# Stay silent unless someone configures logging (otherwise Python's default
# handler would write warnings straight to the terminal).
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Invalid characters for filenames
INVALID_FILENAME_CHARS = '/\\:*?"<>|'

# Where save files live. Override with the DATA_DIR environment variable
# (e.g. point it at a mounted volume when running in Docker).
DATA_DIR = os.environ.get("DATA_DIR", ".")

# Legacy default filename for callers that still use a shared save file.
DEFAULT_SAVE_FILE = "audit_records.json"

# Every saved audit record must contain these sections, each as a dict.
REQUIRED_RECORD_SECTIONS = ("company_profile", "proposal", "ai_audit", "evaluation")


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

def normalise_filename(jsonfile_name):
    """Strips whitespace and makes sure the name ends with .json
    (any capitalisation of the extension is accepted)."""
    jsonfile_name = str(jsonfile_name).strip()
    if jsonfile_name and not jsonfile_name.lower().endswith('.json'):
        jsonfile_name += '.json'
    return jsonfile_name


def is_valid_filename(jsonfile_name):
    """A bare filename only: no folders, control characters, or empty stem."""
    if any(char in jsonfile_name for char in INVALID_FILENAME_CHARS):
        return False
    if any(ord(char) < 32 for char in jsonfile_name):
        return False
    stem = jsonfile_name[:-len('.json')] if jsonfile_name.lower().endswith('.json') else jsonfile_name
    # Rejects ".json", "..json", " .json" and similar nameless files.
    return stem.strip(" .") != ""


def _full_path(jsonfile_name):
    return os.path.join(DATA_DIR, jsonfile_name)

def generate_company_save_filename(company_name):
    """Return a stable, safe JSON filename for one company.

    Repeated assessments for the same company use this same JSON/PDF pair;
    different company names produce separate pairs.
    """
    company_name = str(company_name or "Company").strip()
    safe_name = "".join(
        "_" if char in INVALID_FILENAME_CHARS or ord(char) < 32 else char
        for char in company_name
    )
    safe_name = re.sub(r"\s+", " ", safe_name).strip(" .")[:100].rstrip(" .")
    if not safe_name:
        safe_name = "Company"
    return f"audit_{safe_name}.json"

# ---------------------------------------------------------------------------
# Record helpers
# ---------------------------------------------------------------------------

def is_valid_audit_record(record):
    """Accept both canonical audit records and the current IO Manager record shape."""
    if not isinstance(record, dict):
        return False

    # Canonical records used by the newer manager architecture.
    if all(isinstance(record.get(section), dict) for section in REQUIRED_RECORD_SECTIONS):
        return True

    # Flat, display-oriented records created by the attached main.py.
    return "Company Name" in record and (
        "Proposal Narrative" in record or "Company Total Revenue" in record
    )


def _section(record, section_name):
    """Safe access to a record section: always returns a dict."""
    if not isinstance(record, dict):
        return {}
    section = record.get(section_name)
    return section if isinstance(section, dict) else {}


# ---------------------------------------------------------------------------
# Audit record management
# ---------------------------------------------------------------------------

def generate_audit_id(records):
    """Return the next ID for either nested or flat audit records."""
    if not isinstance(records, list) or not records:
        return 1

    highest_id = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        audit_id = record.get("audit_id", record.get("Audit ID", 0))
        if isinstance(audit_id, int) and not isinstance(audit_id, bool):
            highest_id = max(highest_id, audit_id)
    return highest_id + 1


def create_audit_record(audit_id, user_profile, proposal, ai_audit, evaluation):
    """Combine all assessment information into one audit record."""
    return {
        "audit_id": audit_id,
        "created_at": datetime.now().isoformat(),
        "company_profile": user_profile,
        "proposal": {
            "raw_narrative": proposal
        },
        "ai_audit": ai_audit,
        "evaluation": evaluation
    }


def add_audit_record(records, audit_record):
    """Add a completed audit record to the current record list."""
    if not isinstance(records, list):
        records = []
    records.append(audit_record)
    return records


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def inspect_save_file(jsonfile_name):
    """
    Checks a filename WITHOUT reading the file.

    Returns (clean_name, status) where status is one of:
        "no_name"       nothing was given          (clean_name is "")
        "invalid_name"  has illegal characters     (clean_name is "")
        "exists"        a save file is already there
        "not_found"     no such file yet           (clean_name is still usable)
    """
    name = normalise_filename(jsonfile_name)
    if not name:
        return "", "no_name"
    if not is_valid_filename(name):
        return "", "invalid_name"
    if os.path.isfile(_full_path(name)):
        return name, "exists"
    return name, "not_found"


def _backup_corrupt_file(path):
    """Moves a bad file aside so a later save cannot silently destroy it."""
    try:
        os.replace(path, path + ".corrupt")
    except OSError as err:
        logger.error("Could not back up corrupt file %s: %s", path, err)


def load_data_from_json(jsonfile_name):
    """
    Loads records from a JSON save file.

    Returns (data, clean_name, status). data is ALWAYS a list.
    status is one of:
        "loaded"          success
        "no_name"         nothing was given
        "invalid_name"    illegal characters in the name
        "not_found"       file does not exist
        "invalid_json"    file is corrupt/unreadable (set aside as .corrupt)
        "invalid_format"  valid JSON but not a list of audit records (set aside)
        "io_error"        the OS refused to read the file
    """
    name = normalise_filename(jsonfile_name)
    if not name:
        return [], "", "no_name"
    if not is_valid_filename(name):
        return [], "", "invalid_name"

    path = _full_path(name)
    if not os.path.isfile(path):
        return [], name, "not_found"

    try:
        with open(path, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except ValueError:  # JSONDecodeError and UnicodeDecodeError
        logger.error("%s contains invalid JSON.", path)
        _backup_corrupt_file(path)
        return [], name, "invalid_json"
    except (OSError, RecursionError) as err:
        logger.error("Could not read %s: %s", path, err)
        return [], name, "io_error"

    # A single record on its own is treated as a one-item list.
    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list) or not all(is_valid_audit_record(r) for r in data):
        logger.error("%s is not a list of audit records.", path)
        _backup_corrupt_file(path)
        return [], name, "invalid_format"

    return data, name, "loaded"


def is_data_loaded(data, jsonfile_name):
    """True if there is already data/filename in memory (io_manager should
    then ask the user before overwriting it)."""
    return not (data == [] and jsonfile_name == "")


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

def save_data_to_json(data, jsonfile_name):
    """
    Saves records to a JSON file.

    Writes to a temporary file first and then swaps it in, so a crash midway
    can never leave a half-written (corrupt) save file.

    Returns (saved_name_or_None, status) where status is one of:
        "saved", "no_name", "invalid_name", "io_error"
    """
    name = normalise_filename(jsonfile_name)
    if not name:
        return None, "no_name"
    if not is_valid_filename(name):
        return None, "invalid_name"

    path = _full_path(name)
    tmp_path = path + ".tmp"
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(tmp_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
        os.replace(tmp_path, path)
        return name, "saved"
    except (OSError, TypeError, ValueError) as err:
        logger.error("Could not save to %s: %s", path, err)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return None, "io_error"


# ---------------------------------------------------------------------------
# Filtering / querying
# ---------------------------------------------------------------------------

def filter_by_decision_status(records, decision_status):
    """Records whose evaluation decision_status matches exactly.
    Example: filter_by_decision_status(records, "PRE_APPROVED_TIER_1")"""
    return [
        r for r in records
        if _section(r, "evaluation").get("decision_status") == decision_status
    ]


def filter_approved_records(records):
    """Records where the audit passed."""
    return [
        r for r in records
        if _section(r, "evaluation").get("audit_passed") is True
    ]


def find_records_by_company(records, company_name):
    """Case-insensitive exact match on company name."""
    wanted = str(company_name).strip().lower()
    return [
        r for r in records
        if str(_section(r, "company_profile").get("company_name", "")).strip().lower() == wanted
    ]


def available_decision_statuses(records):
    """Sorted list of the distinct decision statuses present in the records
    (lets io_manager offer only filters that can match something)."""
    statuses = {
        _section(r, "evaluation").get("decision_status")
        for r in records
    }
    return sorted(status for status in statuses if isinstance(status, str) and status)


# ---------------------------------------------------------------------------
# Bridge back to io_manager's display format
# ---------------------------------------------------------------------------

def audit_record_to_display_format(audit_record):
    """
    Converts a saved audit record into the capitalised keys that
    io_manager.display_applied_grants() uses. Needed so records loaded from
    JSON can be listed exactly like records entered in the current session.
    """
    profile = _section(audit_record, "company_profile")
    return {
        "Company Name": profile.get("company_name", ""),
        "Company Industry": profile.get("company_industry", ""),
        "Company Total Revenue": profile.get("annual_revenue_sgd", 0.0),
        "Total Employees": profile.get("group_employment_size", 0),
        "Local Equity": profile.get("local_shareholding_pct", 0.0),
        "Proposal Type": profile.get("proposal_type", ""),
        "Proposal Narrative": _section(audit_record, "proposal").get("raw_narrative", ""),
        "Baseline Energy Expenditure": profile.get("baseline_annual_energy_expenditure_sgd", 0.0),
        "Estimated Retrofit Cost": profile.get("estimated_retrofit_cost_sgd", 0.0),
        "Reporting Advisory Fee": profile.get("reporting_advisory_fee_sgd", 0.0),
    }


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

def export_json_to_pdf(jsonfile_name, pdf_filename=None):
    """Create a polished, company-facing assessment report from saved JSON.

    The report includes every audit record in the source file. It is saved in
    DATA_DIR and uses the JSON filename stem by default.

    Returns (pdf_filename, status). A successful export returns "exported".
    Requires ReportLab: python -m pip install reportlab
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        )
        from xml.sax.saxutils import escape
    except ImportError:
        logger.error("PDF export requires ReportLab. Install it with: python -m pip install reportlab")
        return None, "missing_dependency"

    records, clean_json_name, load_status = load_data_from_json(jsonfile_name)
    if load_status != "loaded":
        return None, load_status

    if pdf_filename is None or not str(pdf_filename).strip():
        pdf_name = os.path.splitext(clean_json_name)[0] + ".pdf"
    else:
        pdf_name = str(pdf_filename).strip()
        if not pdf_name.lower().endswith(".pdf"):
            pdf_name += ".pdf"

    pdf_stem = os.path.splitext(pdf_name)[0]
    if (
        not pdf_stem.strip(" .")
        or os.path.basename(pdf_name) != pdf_name
        or any(char in pdf_name for char in INVALID_FILENAME_CHARS)
        or any(ord(char) < 32 for char in pdf_name)
    ):
        return None, "invalid_pdf_name"

    pdf_path = _full_path(pdf_name)

    try:
        os.makedirs(DATA_DIR, exist_ok=True)

        # Use a common Unicode font when present, with built-in fonts as fallback.
        regular_font = "Helvetica"
        bold_font = "Helvetica-Bold"
        font_candidates = [
            (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ]
        for regular_path, bold_path in font_candidates:
            if os.path.isfile(regular_path):
                pdfmetrics.registerFont(TTFont("CompanyAudit", regular_path))
                regular_font = "CompanyAudit"
                if os.path.isfile(bold_path):
                    pdfmetrics.registerFont(TTFont("CompanyAudit-Bold", bold_path))
                    bold_font = "CompanyAudit-Bold"
                else:
                    bold_font = regular_font
                break

        # One restrained palette is used throughout. Outcome cards use a
        # muted red for non-qualification, amber for review, and teal for a match.
        navy = colors.HexColor("#18324B")
        teal = colors.HexColor("#167C80")
        ink = colors.HexColor("#253746")
        muted = colors.HexColor("#657786")
        line = colors.HexColor("#D9E2E8")
        pale_blue = colors.HexColor("#F2F6F9")
        pale_teal = colors.HexColor("#E8F4F3")
        pale_red = colors.HexColor("#FBEDEC")
        red = colors.HexColor("#A33A35")
        pale_amber = colors.HexColor("#FFF5E3")
        amber = colors.HexColor("#936218")
        white = colors.white

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CompanyAuditTitle", parent=styles["Title"], fontName=bold_font,
            fontSize=20, leading=24, alignment=1, textColor=navy,
            spaceAfter=2 * mm,
        )
        subtitle_style = ParagraphStyle(
            "CompanyAuditSubtitle", parent=styles["Normal"], fontName=regular_font,
            fontSize=9, leading=12, alignment=1, textColor=muted,
            spaceAfter=5 * mm,
        )
        section_style = ParagraphStyle(
            "CompanyAuditSection", parent=styles["Heading2"], fontName=bold_font,
            fontSize=11, leading=14, textColor=navy,
            spaceBefore=4 * mm, spaceAfter=2 * mm, keepWithNext=True,
        )
        body_style = ParagraphStyle(
            "CompanyAuditBody", parent=styles["BodyText"], fontName=regular_font,
            fontSize=9, leading=13, textColor=ink, splitLongWords=True,
        )
        label_style = ParagraphStyle(
            "CompanyAuditLabel", parent=body_style, fontName=bold_font,
            textColor=navy,
        )
        small_style = ParagraphStyle(
            "CompanyAuditSmall", parent=body_style, fontSize=8, leading=10,
            textColor=muted,
        )
        outcome_style = ParagraphStyle(
            "CompanyAuditOutcome", parent=body_style, fontName=bold_font,
            fontSize=13, leading=17, textColor=navy,
        )
        narrative_style = ParagraphStyle(
            "CompanyAuditNarrative", parent=body_style, leftIndent=3 * mm,
            rightIndent=3 * mm, borderColor=line, borderWidth=0.5,
            borderPadding=8, backColor=pale_blue,
        )
        summary_style = ParagraphStyle(
            "CompanyAuditSummary", parent=body_style, fontSize=9,
            leading=13, textColor=ink,
        )

        label_names = {
            "company_name": "Company name",
            "company_industry": "Industry",
            "annual_revenue_sgd": "Annual revenue",
            "group_employment_size": "Group employees",
            "local_shareholding_pct": "Local shareholding",
            "proposal_type": "Proposal type",
            "baseline_annual_energy_expenditure_sgd": "Annual energy expenditure",
            "estimated_retrofit_cost_sgd": "Estimated retrofit cost",
            "reporting_advisory_fee_sgd": "Reporting advisory fee",
            "scope_category": "Emissions scope",
            "primary_intervention_type": "Main intervention",
            "estimated_energy_reduction_pct": "Estimated energy reduction",
            "estimated_lifetime_abatement_tonnes": "Estimated lifetime abatement",
            "detected_exclusion_keywords": "Potential exclusions",
            "implementation_bottleneck": "Implementation constraint",
            "ai_reasoning_summary": "Assessment summary",
            "approved_subsidy_sgd": "Potential grant amount",
            "audit_passed": "Screening result",
            "is_sme": "Meets SME criteria",
            "created_at": "Assessment date",
            "raw_narrative": "Proposal narrative",
        }

        def nice_label(value):
            key = str(value)
            return label_names.get(key, key.replace("_", " ").strip().capitalize())

        def readable_value(value, key=""):
            """Format common values as prose, never as JSON source text."""
            if value is None or value == "":
                return "Not provided"
            if isinstance(value, bool):
                return "Yes" if value else "No"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                lowered = str(key).lower()
                if any(term in lowered for term in (
                    "_sgd", "revenue", "cost", "fee", "expenditure", "subsidy", "grant amount"
                )):
                    return f"SGD {value:,.2f}"
                if "pct" in lowered or "percent" in lowered:
                    return f"{value:,.1f}%"
                if "tonne" in lowered:
                    return f"{value:,.1f} tonnes CO2e"
                return f"{value:,}" if isinstance(value, int) else f"{value:,.2f}"
            if isinstance(value, list):
                return "\n".join(f"- {readable_value(item)}" for item in value) if value else "None recorded"
            if isinstance(value, dict):
                return "\n".join(
                    f"{nice_label(item_key)}: {readable_value(item_value, item_key)}"
                    for item_key, item_value in value.items()
                )
            text = str(value)
            if str(key).lower().replace(" ", "_") == "decision_status":
                status_labels = {
                    "REJECT_NON_SME": "Did not qualify - company criteria",
                    "REJECT_LOW_IMPACT": "Did not qualify - impact threshold",
                    "PRE_APPROVED_SRG": "Potential match - reporting grant",
                    "PRE_APPROVED_TIER_1": "Potential match - base tier",
                    "PRE_APPROVED_TIER_1_ADVANCED": "Potential match - advanced tier",
                    "PROVISIONAL_APPROVAL_TIER_2": "Potential match - provisional",
                    "MANUAL_REVIEW": "Further review required",
                    "MANUAL_EXCLUSION_REVIEW": "Further review required - potential exclusion",
                }
                return status_labels.get(text, text.replace("_", " ").title())
            return text

        def para(value, style=body_style):
            safe = escape(str(value)).replace("\r\n", "\n").replace("\r", "\n")
            return Paragraph(safe.replace("\n", "<br/>"), style)

        def add_detail_table(story, items):
            if not items:
                story.append(para("No information was recorded for this section.", small_style))
                return
            rows = []
            for key, value in items:
                rows.append([
                    para(nice_label(key), label_style),
                    para(readable_value(value, key), body_style),
                ])
            table = Table(rows, colWidths=[53 * mm, 117 * mm], hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), pale_blue),
                ("ROWBACKGROUNDS", (1, 0), (1, -1), [white, colors.HexColor("#FAFBFC")]),
                ("GRID", (0, 0), (-1, -1), 0.35, line),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.extend([table, Spacer(1, 2 * mm)])

        def add_bullets(story, heading, items, color=ink):
            if not items:
                return
            story.append(Paragraph(escape(heading), section_style))
            if not isinstance(items, list):
                items = [items]
            bullet_style = ParagraphStyle(
                "CompanyAuditBullet", parent=body_style, leftIndent=5 * mm,
                firstLineIndent=-3 * mm, textColor=color, spaceAfter=2,
            )
            for item in items:
                story.append(para(f"- {readable_value(item)}", bullet_style))

        def outcome_for(evaluation):
            status = str(evaluation.get("decision_status", ""))
            if status.startswith("MANUAL"):
                return (
                    "Further review required",
                    pale_amber,
                    amber,
                    "The screening identified an item that needs review before an eligibility conclusion can be made.",
                )
            if status.startswith("REJECT"):
                return (
                    "Did not qualify under this screening",
                    pale_red,
                    red,
                    "The recorded assessment did not meet the current screening criteria. See the reasons and next steps below.",
                )
            if evaluation.get("audit_passed") is True:
                return (
                    "Potential grant match identified",
                    pale_teal,
                    teal,
                    "The initial screening found a potential match. Final eligibility and funding remain subject to the grant administrator's review.",
                )
            return (
                "No positive eligibility result recorded",
                pale_amber,
                amber,
                "The saved assessment does not record a positive eligibility result. Review the details below.",
            )

        def add_page_chrome(canvas, doc):
            canvas.saveState()
            canvas.setFillColor(navy)
            canvas.rect(0, A4[1] - 5 * mm, A4[0], 5 * mm, fill=1, stroke=0)
            canvas.setStrokeColor(line)
            canvas.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
            canvas.setFont(regular_font, 8)
            canvas.setFillColor(muted)
            canvas.drawString(20 * mm, 10 * mm, "CONFIDENTIAL - Prepared for the named company")
            canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {doc.page}")
            canvas.restoreState()

        document = SimpleDocTemplate(
            pdf_path, pagesize=A4,
            rightMargin=20 * mm, leftMargin=20 * mm,
            topMargin=14 * mm, bottomMargin=22 * mm,
            title="Company Green Grant Eligibility Assessment",
            author="SME Green Grant Eligibility Auditor",
        )
        story = []
        if not records:
            story.extend([
                Spacer(1, 5 * mm),
                Paragraph("GREEN GRANT ELIGIBILITY ASSESSMENT", title_style),
                Paragraph("Company audit report", subtitle_style),
                para("No audit records were found in the selected JSON file."),
            ])

        for index, record in enumerate(records):
            if index:
                story.append(PageBreak())
            is_nested_record = all(
                isinstance(record.get(section), dict) for section in REQUIRED_RECORD_SECTIONS
            )
            if is_nested_record:
                profile = _section(record, "company_profile")
                proposal = _section(record, "proposal")
                ai_audit = _section(record, "ai_audit")
                evaluation = _section(record, "evaluation")
                record_id = record.get("audit_id", index + 1)
                created_at = record.get("created_at", "")
            else:
                profile = {
                    "company_name": record.get("Company Name", ""),
                    "company_industry": record.get("Company Industry", ""),
                    "annual_revenue_sgd": record.get("Company Total Revenue", 0.0),
                    "group_employment_size": record.get("Total Employees", 0),
                    "local_shareholding_pct": record.get("Local Equity", 0.0),
                    "proposal_type": record.get("Proposal Type", ""),
                    "baseline_annual_energy_expenditure_sgd": record.get("Baseline Energy Expenditure", 0.0),
                    "estimated_retrofit_cost_sgd": record.get("Estimated Retrofit Cost", 0.0),
                    "reporting_advisory_fee_sgd": record.get("Reporting Advisory Fee", 0.0),
                }
                proposal = {"raw_narrative": record.get("Proposal Narrative", "")}
                ai_audit = record.get("AI Audit", {})
                evaluation = record.get("Grant Decision", {})
                record_id = record.get("Audit ID", index + 1)
                created_at = record.get("Created At", "")
                if not isinstance(ai_audit, dict):
                    ai_audit = {}
                if not isinstance(evaluation, dict):
                    evaluation = {}
            outcome, outcome_bg, outcome_color, outcome_explanation = outcome_for(evaluation)

            story.extend([
                Spacer(1, 4 * mm),
                Paragraph("GREEN GRANT ELIGIBILITY ASSESSMENT", title_style),
                Paragraph("Company audit report", subtitle_style),
            ])

            company_name = str(profile.get("company_name") or "Company name not recorded")
            story.append(Paragraph(escape(company_name), section_style))
            try:
                assessment_datetime = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                assessment_date = assessment_datetime.strftime("%Y-%m-%d")
                assessment_time = assessment_datetime.strftime("%H:%M:%S")
            except (TypeError, ValueError):
                assessment_date = "Not recorded"
                assessment_time = "Not recorded"

            story.append(para(f"Audit reference {record_id}", small_style))
            story.append(para(f"Date: {assessment_date} (YYYY-MM-DD)", small_style))
            story.append(para(f"Time: {assessment_time}", small_style))
            story.append(Spacer(1, 3 * mm))

            colored_outcome_style = ParagraphStyle(
                "CompanyAuditOutcomeColored", parent=outcome_style,
                textColor=outcome_color,
            )
            outcome_title = Paragraph(escape(outcome), colored_outcome_style)
            outcome_panel = Table(
                [[outcome_title], [para(outcome_explanation, summary_style)]],
                colWidths=[170 * mm], hAlign="LEFT",
            )
            outcome_panel.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), outcome_bg),
                ("BOX", (0, 0), (-1, -1), 0.8, outcome_color),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]))
            story.extend([outcome_panel, Spacer(1, 2 * mm)])
            story.append(para(
                "This is a preliminary automated screening report, not an official grant decision or funding offer.",
                small_style,
            ))

            story.append(Paragraph("Assessment summary", section_style))
            summary_items = [
                ("Decision status", evaluation.get("decision_status", "Not recorded")),
                ("Meets SME criteria", evaluation.get("is_sme", "Not recorded")),
                ("Potential grant amount", evaluation.get("approved_subsidy_sgd", 0)),
                ("Screening result", evaluation.get("audit_passed", False)),
            ]
            add_detail_table(story, summary_items)

            story.append(Paragraph("Company profile", section_style))
            add_detail_table(story, list(profile.items()))

            story.append(Paragraph("Proposal", section_style))
            narrative = proposal.get("raw_narrative", "")
            if narrative:
                story.append(para(narrative, narrative_style))
            else:
                story.append(para("No proposal narrative was recorded.", small_style))
            other_proposal = [(key, value) for key, value in proposal.items() if key != "raw_narrative"]
            if other_proposal:
                story.append(Spacer(1, 2 * mm))
                add_detail_table(story, other_proposal)

            story.append(Paragraph("Scope and impact assessment", section_style))
            ai_rows = [(key, value) for key, value in ai_audit.items() if key != "ai_reasoning_summary"]
            add_detail_table(story, ai_rows)
            if ai_audit.get("ai_reasoning_summary"):
                story.append(para("Assessment summary", label_style))
                story.append(para(ai_audit["ai_reasoning_summary"], body_style))

            reasons = evaluation.get("reasons", [])
            if not reasons and outcome.startswith("Did not qualify"):
                reasons = ["No detailed reason was recorded in the saved assessment."]
            add_bullets(story, "Why this result was reached", reasons,
                        color=red if outcome.startswith("Did not qualify") else ink)
            add_bullets(story, "Recommended next steps", evaluation.get("recommendations", []))
            add_bullets(story, "Potentially matched grants", evaluation.get("matched_schemes", []))

            other_evaluation = [
                (key, value) for key, value in evaluation.items()
                if key not in {
                    "decision_status", "approved_subsidy_sgd", "audit_passed", "is_sme",
                    "reasons", "recommendations", "matched_schemes",
                }
            ]
            if other_evaluation:
                story.append(Paragraph("Additional assessment details", section_style))
                add_detail_table(story, other_evaluation)

        document.build(story, onFirstPage=add_page_chrome, onLaterPages=add_page_chrome)
        return pdf_name, "exported"
    except Exception as err:
        logger.exception("Could not export audit records from %s to PDF: %s", clean_json_name, err)
        return None, "pdf_error"