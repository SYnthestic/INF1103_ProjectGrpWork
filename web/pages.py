"""The HTML pages of the web version: the grants home page, accounts, a new
audit, history (with PDF download) and the records in memory (the terminal's
menu options 2-8)."""

import os
from typing import Any

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from managers import DataManager
from models import ApplicationRecord
from web.display import ResultPresenter
from web.routes import Route, RouteGroup
from web.service import AccountRules, ApplicationValidator
from web.workspace import Workspace


class PageRoutes(RouteGroup):
    """Every HTML page. Pages that need an account send visitors to the login
    page first."""

    name = "pages"
    template_folder = "templates"

    OTHER_GRANT = "5. Others"
    OTHER_TEXT_MAX_LEN = 60
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
    OPTIONAL_NUMBERS = (
        "Baseline Energy Expenditure",
        "Estimated Retrofit Cost",
        "Reporting Advisory Fee",
    )
    TEXT_FIELDS = (
        "Company Name",
        "Company Industry",
        "Sustainability Grant",
        "Proposal Narrative",
    )
    NUMBER_FIELDS = (
        "Company Total Revenue",
        "Total Employees",
        "Local Equity",
        "Baseline Energy Expenditure",
        "Estimated Retrofit Cost",
        "Reporting Advisory Fee",
    )
    LOAD_MESSAGES = {
        "no_name": "Load cancelled.",
        "invalid_name": "That file name contains illegal characters.",
        "not_found": "That file was not found.",
        "invalid_json": "The file is corrupt or unreadable. It was set aside as a .corrupt backup.",
        "invalid_format": "The file is valid JSON but not a list of audit records. It was set aside.",
        "io_error": "The operating system refused to read the file.",
        "decrypt_failed": "The file could not be decrypted: the encryption key is wrong "
        "or the file was modified. It was left unchanged.",
        "not_encrypted": "The file is not encrypted, so it was not trusted. Run "
        "'python main.py --encrypt-existing-data' once to encrypt existing files.",
        "encrypted_no_key": "The file is encrypted, but no encryption key is in use.",
    }
    PDF_MESSAGES = {
        "missing_dependency": "PDF export needs ReportLab (python -m pip install reportlab).",
        "invalid_pdf_name": "The PDF file name was not valid.",
        "pdf_error": "The PDF could not be created.",
    }

    def __init__(
        self,
        presenter: ResultPresenter | None = None,
        account_rules: AccountRules | None = None,
        validator: ApplicationValidator | None = None,
    ) -> None:
        self._presenter = presenter or ResultPresenter()
        self._account_rules = account_rules or AccountRules()
        self._validator = validator or ApplicationValidator()

    def routes(self) -> list[Route]:
        get, post, both = ("GET",), ("POST",), ("GET", "POST")
        return [
            Route("/", self.home, get),
            Route("/register", self.register, both),
            Route("/login", self.login, both),
            Route("/logout", self.logout, post),
            Route("/new", self.new_audit, both, login=True),
            Route("/history", self.history, get, login=True),
            Route("/history/<int:audit_id>", self.detail, get, login=True),
            Route("/history/<int:audit_id>/pdf", self.audit_pdf, get, login=True),
            Route("/records", self.records_page, get, login=True),
            Route("/records/save", self.save_records, both, login=True),
            Route("/records/load", self.load_records, both, login=True),
            Route("/records/<int:index>/edit", self.edit_record, both, login=True),
            Route("/records/<int:index>/delete", self.delete_record, post, login=True),
            Route("/records/ai", self.run_ai, post, login=True),
            Route("/records/logic", self.run_logic, post, login=True),
        ]

    def not_logged_in(self) -> Any:
        flash("Please log in first.")
        return redirect(url_for("pages.login"))

    def on_register(self, blueprint: Blueprint) -> None:
        """Lets the templates show decisions, money and labelled rows."""
        blueprint.record_once(lambda state: self._presenter.install(state.app))

    # ----- helpers shared by the pages -----
    def workspace(self) -> Workspace:
        return self.workspaces.get(self.username)

    def find_audit(self, audit_id: int) -> dict[str, Any] | None:
        audits = self.data.get_user_audits(self.username)
        return next((a for a in audits if a.get("audit_id") == audit_id), None)

    def user_data(self) -> DataManager:
        """A DataManager for THIS user's record files. Built per request so
        active_user is never shared between users."""
        shared = self.data
        data = DataManager(
            data_dir=shared.data_dir, exporter=self.exporter, cipher=shared.cipher
        )
        data.active_user = self.username
        return data

    @staticmethod
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

    @staticmethod
    def back_to_records(message: str) -> Any:
        flash(message)
        return redirect(url_for("pages.records_page"))

    def already_logged_in(self) -> Any:
        flash("You are already logged in. Log out first to switch accounts.")
        return redirect(url_for("pages.history"))

    # ----- reading the application form -----
    def valid_other_text(self, text: str) -> bool:
        """Same rule as the CLI: letters and spaces only, within the length limit."""
        return 0 < len(text) <= self.OTHER_TEXT_MAX_LEN and text.replace(" ", "").isalpha()

    def parse_application_form(self, form: Any) -> tuple[dict[str, Any], str | None]:
        """Turns form text into the same record shape the CLI builds."""
        choice = form.get("Company Industry", "")
        if choice == "Others":
            industry = form.get("Industry Other", "").strip()
        elif choice in self.INDUSTRIES:
            industry = choice
        else:
            industry = ""

        grant_choice = form.get("Sustainability Grant", "")
        if grant_choice == self.OTHER_GRANT:
            grant = form.get("Grant Other", "").strip()
            if not self.valid_other_text(grant):
                return {}, "Please specify a valid grant name (letters and spaces only)."
        elif grant_choice in self.GRANTS:
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
        error = self.read_numbers(form, record, record["Proposal Type"])
        if error:
            return record, error
        return record, self._validator.problem(record, strict_costs=True)

    def read_numbers(self, form: Any, record: dict[str, Any], proposal_type: Any) -> str | None:
        """Copies the number fields from `form` into `record` (finite numbers
        only; Total Employees as a whole number). Money fields this kind of
        proposal does not use are set to 0, as in the terminal."""
        used_money = self._validator.money_fields_for(proposal_type)
        for key in self.NUMBER_FIELDS:
            if key in self.OPTIONAL_NUMBERS and key not in used_money:
                record[key] = 0.0
                continue
            text = form.get(key, "")
            value = self._validator.form_number(text)
            if value is None:
                if key in self.OPTIONAL_NUMBERS and not str(text).strip():
                    value = 0.0  # left blank: checked against the rules below
                else:
                    return "Revenue, employees, equity and costs must be numbers."
            record[key] = value
        employees = record["Total Employees"]
        if employees != int(employees):
            return "Total Employees must be a whole number above 0"
        record["Total Employees"] = int(employees)
        return None

    # ----- home and accounts -----
    def home(self) -> Any:
        """The home page (the logo links here): the grants the auditor checks,
        with the conditions currently in force. Open to everyone."""
        self.audit_service.use_saved_rules()
        return render_template("home.html", config=self.logic.rule_config)

    def register(self) -> Any:
        if self.username is not None:
            return self.already_logged_in()
        if request.method == "POST":
            username = self._account_rules.clean_username(request.form.get("username", ""))
            password = request.form.get("password", "")
            problem = self._account_rules.problem(username, password)
            if problem:
                flash(problem)
            elif self._account_rules.is_taken(self.data, self.logic, username):
                flash("That username is taken.")
            elif not self.data.save_new_user(self.logic.build_new_user_record(username, password)):
                flash("Could not create the account.")
            else:
                flash("Account created. Please log in.")
                return redirect(url_for("pages.login"))
        return render_template("register.html")

    def login(self) -> Any:
        if self.username is not None:
            return self.already_logged_in()
        if request.method == "POST":
            username = self._account_rules.clean_username(request.form.get("username", ""))
            password = request.form.get("password", "")
            if self.logic.verify_password(password, self.data.get_user(username)):
                self.start_session(username)
                return redirect(url_for("pages.history"))
            flash("Invalid username or password.")
        return render_template("login.html")

    def logout(self) -> Any:
        username = self.username
        if username:
            ws = self.workspaces.get(username)
            if ws.dirty and ws.records and not request.form.get("force"):
                return render_template("confirm_exit.html")
            self.workspaces.discard(username)
        self.end_session()
        return redirect(url_for("pages.login"))

    # ----- a new audit and the history -----
    def new_audit(self) -> Any:
        values: Any = {}
        if request.method == "POST":
            record, error = self.parse_application_form(request.form)
            if not error:
                audit, error, _ = self.audit_service.create_audit(self.username, record)
                if audit:
                    ws = self.workspace()
                    ws.records.append(record)
                    ws.ai_audit = audit.get("ai_audit") or {}
                    ws.dirty = True
                    flash("Audit saved to history. The record is also in memory: "
                          "save it to a file from the Records page.")
                    return redirect(url_for("pages.detail", audit_id=audit["audit_id"]))
            flash(error or "Something went wrong.")
            values = request.form
        return render_template(
            "new.html",
            values=values,
            industries=self.INDUSTRIES,
            proposal_types=self.PROPOSAL_TYPES,
            grants=self.GRANTS,
        )

    def history(self) -> Any:
        return render_template("history.html", audits=self.data.get_user_audits(self.username))

    def detail(self, audit_id: int) -> Any:
        audit = self.find_audit(audit_id)
        if audit is None:
            return render_template("notfound.html"), 404
        application = ApplicationRecord(audit.get("application") or {}).flat
        return render_template("detail.html", audit=audit, application=application)

    def audit_pdf(self, audit_id: int) -> Any:
        audit = self.find_audit(audit_id)  # only this user's own audits
        if audit is None:
            return render_template("notfound.html"), 404
        data = self.user_data()
        pdf_name, status = data.export_audit_to_pdf(audit)
        if status != "exported":
            flash(self.PDF_MESSAGES.get(status, "The PDF could not be created."))
            return redirect(url_for("pages.detail", audit_id=audit_id))
        return send_from_directory(
            data.get_records_folder(), pdf_name,
            as_attachment=True, mimetype="application/pdf",
        )

    # ----- records in memory (menu options 2-8) -----
    def records_page(self) -> Any:
        ws = self.workspace()
        rows = [ApplicationRecord(r).flat for r in ws.records]
        return render_template("records.html", ws=ws, rows=rows)

    def save_records(self) -> Any:
        ws = self.workspace()
        if not ws.records:
            return self.back_to_records("There are no records in memory to save.")
        if request.method == "GET":
            return render_template("save.html", filename=ws.jsonfile_name)

        data = self.user_data()
        name = request.form.get("filename", "").strip()
        if not name:  # blank = cancel
            return self.back_to_records("Save cancelled. Your records are still in memory.")
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
                    return self.back_to_records(f"Could not read {clean}. Nothing was saved.")
                to_save = data.merge_records(existing, ws.records)
            elif mode != "replace":
                return self.back_to_records("Save cancelled. Your records are still in memory.")

        saved_name, save_status = data.save_data_to_json(to_save, clean)
        if save_status != "saved":
            return self.back_to_records("Could not save the file.")
        ws.jsonfile_name = saved_name or clean
        ws.dirty = False
        return self.back_to_records(f"Records saved to {ws.jsonfile_name}.")

    def load_records(self) -> Any:
        ws = self.workspace()
        data = self.user_data()
        needs_confirm = data.is_data_loaded(ws.records, ws.jsonfile_name)
        files = self.list_record_files(data)
        if request.method == "GET":
            return render_template("load.html", files=files, selected="",
                                   needs_confirm=needs_confirm)

        name = request.form.get("filename", "").strip()
        if not name:  # nothing chosen = cancel
            return self.back_to_records("Load cancelled. Nothing was changed.")
        if needs_confirm and not request.form.get("confirm"):
            flash("Tick the box to confirm replacing the records in memory.")
            return render_template("load.html", files=files, selected=name,
                                   needs_confirm=True)

        loaded, clean, status = data.load_data_from_json(name)
        if status != "loaded":
            return self.back_to_records(self.LOAD_MESSAGES.get(status, "Could not load the file."))
        ws.records, ws.jsonfile_name = loaded, clean
        ws.ai_audit, ws.dirty = {}, False
        return self.back_to_records(f"Records loaded successfully from {clean}.")

    def edit_record(self, index: int) -> Any:
        ws = self.workspace()
        if not 0 <= index < len(ws.records):
            return render_template("notfound.html"), 404
        current = ApplicationRecord(ws.records[index]).flat  # editor uses the flat layout

        def form_page(values: Any) -> Any:
            return render_template("edit.html", index=index, values=values,
                                   text_fields=self.TEXT_FIELDS,
                                   number_fields=self.NUMBER_FIELDS)

        if request.method == "GET":
            return form_page(current)

        updated = dict(current)
        for key in self.TEXT_FIELDS:
            updated[key] = request.form.get(key, "").strip()
        error = self.read_numbers(request.form, updated, updated.get("Proposal Type"))
        if error:
            flash(error)
            return form_page(request.form)
        error = self._validator.problem(updated, strict_costs=True)
        if not error and not updated["Sustainability Grant"]:
            error = "Sustainability Grant is required"
        if error:
            flash(error)
            return form_page(request.form)

        ws.records[index] = current
        changed = False
        for key in self.TEXT_FIELDS + self.NUMBER_FIELDS:
            if updated[key] != current.get(key):
                ws.records, status = self.data.update_record_field(
                    ws.records, index, key, updated[key]
                )
                changed = changed or status == "updated"
        if not changed:
            return self.back_to_records("No changes were made.")
        ws.dirty = True
        return self.back_to_records(f"Record updated: {updated['Company Name']}.")

    def delete_record(self, index: int) -> Any:
        ws = self.workspace()
        if not 0 <= index < len(ws.records):
            return render_template("notfound.html"), 404
        name = ApplicationRecord(ws.records[index]).company_name
        ws.records, status = self.data.delete_record(ws.records, index)
        if status != "deleted":
            return self.back_to_records("The record was not changed.")
        ws.ai_audit, ws.dirty = {}, True
        return self.back_to_records(f"Record deleted: {name}.")

    def run_ai(self) -> Any:
        ws = self.workspace()
        if not ws.records:
            return self.back_to_records("There are no records in memory.")
        audit = self.audit_service.ask_ai(ws.records[-1])
        if audit is None:
            return self.back_to_records("The AI call failed. Please try again.")
        ws.ai_audit = audit
        return render_template("result.html", title="AI audit", kind="ai",
                               company=ApplicationRecord(ws.records[-1]).company_name,
                               data=audit)

    def run_logic(self) -> Any:
        ws = self.workspace()
        if not ws.records:
            return self.back_to_records("There are no records in memory.")
        if not ws.ai_audit:
            return self.back_to_records("There is no AI audit yet. Run the AI Manager first.")
        result = self.audit_service.decide(ws.records[-1], ws.ai_audit)
        if result is None:
            return self.back_to_records("The grant evaluation failed.")
        return render_template("result.html", title="Grant decision", kind="decision",
                               company=ApplicationRecord(ws.records[-1]).company_name,
                               data=result)
