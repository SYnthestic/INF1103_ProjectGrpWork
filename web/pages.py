import os

from managers.data_manager import DataManager
from models import ApplicationRecord
from functools import wraps

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, send_from_directory, url_for)
from flask import session as flask_session

from web import service


OTHER_GRANT = "5. Others"
OTHER_TEXT_MAX_LEN = 60   # TODO: copy the real max length from IOManager so the CLI and web offer the same choices.
bp = Blueprint("pages", __name__, template_folder="templates")

# TODO: copy the real lists from IOManager so the CLI and web offer the same choices.
PROPOSAL_TYPES = ["Equipment / Energy Upgrade", "ESG Reporting / Advisory"]
INDUSTRIES = [
    "Logistics", "Manufacturing", "Retail", "Food & Beverage", "Healthcare",
    "Information Technology", "Construction", "Education", "Finance",
    "Hospitality", "Aerospace", "Others",
]
GRANTS = [
    "1. Energy Efficiency Grant (EEG) -Base Tier",
    "2. Energy Efficiency Grant (EEG) -Advanced Tier",
    "3. Enterprise Development Grant (EDG)",
    "4. Sustainability Reporting Programme (SRP)",
    "5. Others",
]
OPTIONAL_NUMBERS = ("Baseline Energy Expenditure", "Estimated Retrofit Cost",
                    "Reporting Advisory Fee")


def page_login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "username" not in flask_session:
            flash("Please log in first.")
            return redirect(url_for("pages.login"))
        return view(*args, **kwargs)
    return wrapper

TEXT_FIELDS = ("Company Name", "Company Industry", "Sustainability Grant",
               "Proposal Narrative")
NUMBER_FIELDS = ("Company Total Revenue", "Total Employees", "Local Equity",
                 "Baseline Energy Expenditure", "Estimated Retrofit Cost",
                 "Reporting Advisory Fee")
LOAD_MESSAGES = {
    "no_name": "Load cancelled.",
    "invalid_name": "That file name contains illegal characters.",
    "not_found": "That file was not found.",
    "invalid_json": "The file is corrupt or unreadable. It was set aside as a .corrupt backup.",
    "invalid_format": "The file is valid JSON but not a list of audit records. It was set aside.",
    "io_error": "The operating system refused to read the file.",
}

PDF_MESSAGES = {
    "missing_dependency": "PDF export needs ReportLab (python -m pip install reportlab).",
    "invalid_pdf_name": "The PDF file name was not valid.",
    "pdf_error": "The PDF could not be created.",
}


def find_audit(audit_id: int):
    audits = current_app.extensions["data"].get_user_audits(flask_session["username"])
    return next((a for a in audits if a.get("audit_id") == audit_id), None)


def workspace():
    return current_app.extensions["workspaces"].get(flask_session["username"])


def user_data() -> DataManager:
    """A DataManager for THIS user's record files. Built per request so
    active_user is never shared between users."""
    shared = current_app.extensions["data"]
    data = DataManager(data_dir=shared.data_dir,
                       exporter=current_app.extensions.get("exporter"))
    data.active_user = flask_session["username"]
    return data


def list_record_files(data: DataManager) -> list[str]:
    folder = data.get_records_folder()
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return sorted(
        n for n in names
        if n.lower().endswith(".json") and os.path.isfile(os.path.join(folder, n))
    )


def back_to_records(message: str):
    flash(message)
    return redirect(url_for("pages.records_page"))


@bp.get("/")
def home():
    target = "pages.history" if "username" in flask_session else "pages.login"
    return redirect(url_for(target))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if "username" in flask_session:
        flash("You are already logged in. Log out first to switch accounts.")
        return redirect(url_for("pages.history"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        data = current_app.extensions["data"]
        logic = current_app.extensions["logic"]
        if not data.is_safe_username(username):
            flash("Username must be 1-64 characters: a-z, 0-9 or _.")
        elif not password:
            flash("Password is required.")
        elif data.user_exists(username):
            flash("That username is taken.")
        elif not data.save_new_user(logic.build_new_user_record(username, password)):
            flash("Could not create the account.")
        else:
            flash("Account created. Please log in.")
            return redirect(url_for("pages.login"))
    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if "username" in flask_session:
        flash("You are already logged in. Log out first to switch accounts.")
        return redirect(url_for("pages.history"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        data = current_app.extensions["data"]
        logic = current_app.extensions["logic"]
        if logic.verify_password(password, data.get_user(username)):
            service.start_session(username)
            return redirect(url_for("pages.history"))
        flash("Invalid username or password.")
    return render_template("login.html")


@bp.post("/logout")
def logout():
    username = flask_session.get("username")
    if username:
        spaces = current_app.extensions["workspaces"]
        ws = spaces.get(username)
        if ws.dirty and ws.records and not request.form.get("force"):
            return render_template("confirm_exit.html")
        spaces.discard(username)
    flask_session.clear()
    return redirect(url_for("pages.login"))

def valid_other_text(text: str) -> bool:
    """Same rule as the CLI: letters and spaces only, within the length limit."""
    return (
        0 < len(text) <= OTHER_TEXT_MAX_LEN
        and text.replace(" ", "").isalpha()
    )

def parse_application_form(form) -> tuple[dict, str | None]:
    """Turns form text into the same record shape the CLI builds."""
    choice = form.get("Company Industry", "")
    if choice == "Others":
        industry = form.get("Industry Other", "").strip()
    elif choice in INDUSTRIES:
        industry = choice
    else:
        industry = ""

    grant_choice = form.get("Sustainability Grant", "")
    if grant_choice == OTHER_GRANT:
        grant = form.get("Grant Other", "").strip()
        if not valid_other_text(grant):
            return {}, "Please specify a valid grant name (letters and spaces only)."
    elif grant_choice in GRANTS:
        grant = grant_choice
    else:
        grant = ""

    record = {
        "Company Name": form.get("Company Name", "").strip(),
        "Company Industry": industry,
        "Proposal Type": form.get("Proposal Type", ""),
        "Sustainability Grant": grant,
        "Proposal Narrative": form.get("Proposal Narrative", "").strip(),
    }
    try:
        record["Company Total Revenue"] = float(form.get("Company Total Revenue", ""))
        record["Total Employees"] = int(float(form.get("Total Employees", "")))
        record["Local Equity"] = float(form.get("Local Equity", ""))
        for key in OPTIONAL_NUMBERS:
            record[key] = float(form.get(key) or 0)
    except ValueError:
        return record, "Revenue, employees, equity and costs must be numbers."
    return record, None


@bp.route("/new", methods=["GET", "POST"])
@page_login_required
def new_audit():
    values = {}
    if request.method == "POST":
        record, error = parse_application_form(request.form)
        if not error:
            audit, error, _ = service.create_audit(flask_session["username"], record)
            if audit:
                ws = workspace()
                ws.records.append(record)
                ws.ai_audit = audit.get("ai_audit") or {}
                ws.dirty = True
                flash("Audit saved to history. The record is also in memory: "
                      "save it to a file from the Records page.")
                return redirect(url_for("pages.detail", audit_id=audit["audit_id"]))
        flash(error or "Something went wrong.")
        values = request.form
    return render_template("new.html", values=values, industries=INDUSTRIES,
                           proposal_types=PROPOSAL_TYPES, grants=GRANTS)


@bp.get("/history")
@page_login_required
def history():
    audits = current_app.extensions["data"].get_user_audits(flask_session["username"])
    return render_template("history.html", audits=audits)


@bp.get("/history/<int:audit_id>")
@page_login_required
def detail(audit_id: int):
    audit = find_audit(audit_id)
    if audit is None:
        return render_template("notfound.html"), 404
    return render_template("detail.html", audit=audit)


@bp.get("/history/<int:audit_id>/pdf")
@page_login_required
def audit_pdf(audit_id: int):
    audit = find_audit(audit_id)              # only this user's own audits
    if audit is None:
        return render_template("notfound.html"), 404

    data = user_data()
    pdf_name, status = data.export_audit_to_pdf(audit)
    if status != "exported":
        flash(PDF_MESSAGES.get(status, "The PDF could not be created."))
        return redirect(url_for("pages.detail", audit_id=audit_id))
    return send_from_directory(
        data.get_records_folder(), pdf_name,
        as_attachment=True, mimetype="application/pdf",
    )

# ---- Records in memory (menu options 2-8) --------------------------------
@bp.get("/records")
@page_login_required
def records_page():
    ws = workspace()
    rows = [ApplicationRecord(r).flat for r in ws.records]
    return render_template("records.html", ws=ws, rows=rows)


@bp.route("/records/save", methods=["GET", "POST"])
@page_login_required
def save_records():
    ws = workspace()
    if not ws.records:
        return back_to_records("There are no records in memory to save.")
    if request.method == "GET":
        return render_template("save.html", filename=ws.jsonfile_name)

    data = user_data()
    name = request.form.get("filename", "").strip()
    if not name:                                  # blank = cancel
        return back_to_records("Save cancelled. Your records are still in memory.")
    clean, status = data.inspect_save_file(name)
    if status in ("no_name", "invalid_name"):
        flash("That file name contains illegal characters.")
        return render_template("save.html", filename=name)

    to_save = ws.records
    # Re-saving to the file already in use just replaces it; any other
    # existing file asks first (replace / add / cancel), like the CLI.
    if status == "exists" and clean != ws.jsonfile_name:
        mode = request.form.get("mode")
        if mode is None:
            return render_template("save_exists.html", clean=clean)
        if mode == "add":
            existing, _, load_status = data.load_data_from_json(clean)
            if load_status != "loaded":
                return back_to_records(f"Could not read {clean}. Nothing was saved.")
            to_save = data.merge_records(existing, ws.records)
        elif mode != "replace":
            return back_to_records("Save cancelled. Your records are still in memory.")

    saved_name, save_status = data.save_data_to_json(to_save, clean)
    if save_status != "saved":
        return back_to_records("Could not save the file.")
    ws.jsonfile_name = saved_name or clean
    ws.dirty = False
    return back_to_records(f"Records saved to {ws.jsonfile_name}.")


@bp.route("/records/load", methods=["GET", "POST"])
@page_login_required
def load_records():
    ws = workspace()
    data = user_data()
    needs_confirm = data.is_data_loaded(ws.records, ws.jsonfile_name)
    files = list_record_files(data)
    if request.method == "GET":
        return render_template("load.html", files=files, selected="",
                               needs_confirm=needs_confirm)

    name = request.form.get("filename", "").strip()
    if not name:                                  # nothing chosen = cancel
        return back_to_records("Load cancelled. Nothing was changed.")
    if needs_confirm and not request.form.get("confirm"):
        flash("Tick the box to confirm replacing the records in memory.")
        return render_template("load.html", files=files, selected=name,
                               needs_confirm=True)

    loaded, clean, status = data.load_data_from_json(name)
    if status != "loaded":
        return back_to_records(LOAD_MESSAGES.get(status, "Could not load the file."))
    ws.records, ws.jsonfile_name = loaded, clean
    ws.ai_audit, ws.dirty = {}, False
    return back_to_records(f"Records loaded successfully from {clean}.")


@bp.route("/records/<int:index>/edit", methods=["GET", "POST"])
@page_login_required
def edit_record(index: int):
    ws = workspace()
    if not 0 <= index < len(ws.records):
        return render_template("notfound.html"), 404
    current = ApplicationRecord(ws.records[index]).flat   # editor uses the flat layout

    def form_page(values):
        return render_template("edit.html", index=index, values=values,
                               text_fields=TEXT_FIELDS, number_fields=NUMBER_FIELDS)

    if request.method == "GET":
        return form_page(current)

    updated = dict(current)
    for key in TEXT_FIELDS:
        updated[key] = request.form.get(key, "").strip()
    try:
        for key in NUMBER_FIELDS:
            number = float(request.form.get(key, ""))
            updated[key] = int(number) if key == "Total Employees" else number
    except ValueError:
        flash("Revenue, employees, equity and costs must be numbers.")
        return form_page(request.form)
    error = service.validate_application(updated)
    if not error and not updated["Sustainability Grant"]:
        error = "Sustainability Grant is required"
    if error:
        flash(error)
        return form_page(request.form)

    data = current_app.extensions["data"]
    ws.records[index] = current
    changed = False
    for key in TEXT_FIELDS + NUMBER_FIELDS:
        if updated[key] != current.get(key):
            ws.records, status = data.update_record_field(
                ws.records, index, key, updated[key]
            )
            changed = changed or status == "updated"
    if not changed:
        return back_to_records("No changes were made.")
    ws.dirty = True
    return back_to_records(f"Record updated: {updated['Company Name']}.")


@bp.post("/records/<int:index>/delete")
@page_login_required
def delete_record(index: int):
    ws = workspace()
    if not 0 <= index < len(ws.records):
        return render_template("notfound.html"), 404
    name = ApplicationRecord(ws.records[index]).company_name
    ws.records, status = current_app.extensions["data"].delete_record(ws.records, index)
    if status != "deleted":
        return back_to_records("The record was not changed.")
    ws.ai_audit, ws.dirty = {}, True
    return back_to_records(f"Record deleted: {name}.")


@bp.post("/records/ai")
@page_login_required
def run_ai():
    ws = workspace()
    if not ws.records:
        return back_to_records("There are no records in memory.")
    ai = current_app.extensions["ai"]
    wrapped = ApplicationRecord(ws.records[-1])
    try:
        audit = ai.get_ai_response(wrapped.narrative, lambda *a, **k: None)
    except Exception:
        current_app.logger.exception("AI call raised")
        return back_to_records("The AI call failed. Please try again.")
    if ai.ai_call_failed(audit):
        return back_to_records("The AI call failed. Please try again.")
    ws.ai_audit = audit
    return render_template("result.html", title="AI audit",
                           company=wrapped.company_name, data=audit)


@bp.post("/records/logic")
@page_login_required
def run_logic():
    ws = workspace()
    if not ws.records:
        return back_to_records("There are no records in memory.")
    if not ws.ai_audit:
        return back_to_records("There is no AI audit yet. Run the AI Manager first.")
    wrapped = ApplicationRecord(ws.records[-1])
    try:
        result = current_app.extensions["logic"].evaluate_grant_application(
            wrapped.to_profile(), ws.ai_audit
        )
    except Exception:
        current_app.logger.exception("Grant evaluation raised")
        return back_to_records("The grant evaluation failed.")
    return render_template("result.html", title="Grant decision",
                           company=wrapped.company_name, data=result)