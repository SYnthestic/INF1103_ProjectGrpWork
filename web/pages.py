from functools import wraps

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, url_for)
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


@bp.get("/")
def home():
    target = "pages.history" if "username" in flask_session else "pages.login"
    return redirect(url_for(target))


@bp.route("/register", methods=["GET", "POST"])
def register():
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
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        data = current_app.extensions["data"]
        logic = current_app.extensions["logic"]
        if logic.verify_password(password, data.get_user(username)):
            flask_session.clear()               # fresh session on login
            flask_session["username"] = username
            return redirect(url_for("pages.history"))
        flash("Invalid username or password.")
    return render_template("login.html")


@bp.post("/logout")
def logout():
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
    audits = current_app.extensions["data"].get_user_audits(flask_session["username"])
    audit = next((a for a in audits if a.get("audit_id") == audit_id), None)
    if audit is None:
        return render_template("notfound.html"), 404
    return render_template("detail.html", audit=audit)