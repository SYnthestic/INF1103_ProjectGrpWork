"""Controller: wires the four managers together and runs the menus.

    IOManager     collects and validates input, shows every screen
    AIManager     turns a proposal narrative into a validated JSON audit
    LogicManager  applies the grant rules to the AI-enriched record
    DataManager   saves and loads records, accounts and audit history

The Application is the only class that knows all four. It is handed them
(aggregation), so tests can pass in doubles and nothing here creates a
manager's internals. Run with:  python main.py
"""

import sys
from collections.abc import Callable
from types import TracebackType
from typing import Any

#The 4 managers are imported here so the Application can be tested with doubles.
from managers.ai_manager import AIManager
from managers.data_manager import DataManager
from managers.io_manager import IOManager
from managers.logic_manager import LogicManager

#These are imported here so the Application can be tested with doubles.
from models import ApplicationRecord, Proposal
from session import AiAudit, Record, Records, Session


class Application:
    """The program: login screen, main menu and every menu option."""

    def __init__(
        self,
        io: IOManager | None = None,
        ai: AIManager | None = None,
        logic: LogicManager | None = None,
        data: DataManager | None = None,
    ) -> None:
        self._io = io or IOManager()
        self._ai = ai or AIManager()
        self._logic = logic or LogicManager()
        self._data = data or DataManager()

    @property
    def io(self) -> IOManager:
        return self._io

    @property
    def ai(self) -> AIManager:
        return self._ai

    @property
    def logic(self) -> LogicManager:
        return self._logic

    @property
    def data(self) -> DataManager:
        return self._data

    # ========================================================
    # Start-up and clean exit
    # ========================================================
    @staticmethod
    def load_environment() -> None:
        """Loads OPENROUTER_API_KEY from a local .env file when running outside
        Docker. Inside Docker the variable is injected via --env-file instead."""
        try:
            from dotenv import load_dotenv

            load_dotenv(override=True)
        except ImportError:
            pass

    @classmethod
    def launch(cls) -> None:
        """Entry point used by `python main.py`."""
        cls.load_environment()
        cls().run()

    def handle_uncaught(
        self,
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        """Clean exit on Ctrl+C / end of input. Without this, Ctrl+C at any
        prompt (or running Docker without -it, so there is no keyboard input)
        ends the program with a long traceback. Every other error still shows
        its normal traceback."""
        if issubclass(exc_type, KeyboardInterrupt):
            self._io.show_interrupted()
        elif issubclass(exc_type, EOFError):
            self._io.show_input_ended()
        else:
            sys.__excepthook__(exc_type, exc, tb)

    # ========================================================
    # Account flows: I/O collects -> Logic hashes/verifies -> Data stores
    # ========================================================
    def create_account_flow(self) -> None:
        username = self._io.retrieve_new_username()
        while self._data.user_exists(username):
            self._io.show_username_taken(username)
            username = self._io.retrieve_new_username()

        password = self._io.retrieve_new_password()
        user_record = self._logic.build_new_user_record(username, password)

        if self._data.save_new_user(user_record):
            self._io.show_account_created(username)
        else:
            self._io.show_account_save_failed()

    def login_flow(self) -> str | None:
        """Returns the logged-in username, or None if login failed."""
        username = self._io.retrieve_username()
        password = self._io.retrieve_password()

        stored_user = self._data.get_user(username)
        # The format check also guards against a hand-edited users.json holding
        # a name that cannot be used for the user's folder.
        if self._io.is_valid_username(username) and self._logic.verify_password(
            password, stored_user
        ):
            self._io.show_login_success(username)
            return username

        self._io.show_login_failed()
        return None

    # ========================================================
    # Running the AI and Logic managers on a record
    # ========================================================
    def attempt(self, step: Callable[..., Any], *args: Any) -> tuple[bool, Any]:
        """Runs one risky step (AI call, grant logic). Returns (True, result),
        or (False, None) after showing a short message if it raised, so one
        unexpected error can no longer end the whole program. Ctrl+C and end
        of input are passed through so they still exit cleanly."""
        try:
            return True, step(*args)
        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as error:
            self._io.show_unexpected_error(error)
            return False, None

    def ask_ai(self, narrative: str) -> AiAudit:
        """AI Manager call. The waiting screen belongs to the I/O Manager, so
        it is handed over as a function and the AI Manager never prints."""
        return self._ai.get_ai_response(narrative, self._io.run_ai_analysis_bar)

    def run_audit(self, record: Record) -> tuple[AiAudit, dict[str, Any] | None]:
        """AI Manager -> Logic Manager for one record, displaying both results.
        Returns (ai_audit, result); result is None if a step failed."""
        wrapped = ApplicationRecord(record)
        ok, ai_audit = self.attempt(self.ask_ai, wrapped.narrative)
        if not ok:
            return {}, None
        self._io.display_ai_audit(ai_audit)

        ok, result = self.attempt(
            self._logic.evaluate_grant_application, wrapped.to_profile(), ai_audit
        )
        if not ok:
            return ai_audit, None
        self._io.display_grant_decision(result)
        return ai_audit, result

    # ========================================================
    # Audit history
    # ========================================================
    def apply_history_filter(self, audits: list[Record]) -> list[Record] | None:
        """Asks the user for a filter; the Data Manager does the filtering.
        Returns the matching audits, or None if cancelled / nothing matched."""
        statuses = self._data.available_audit_statuses(audits)
        chosen = self._io.retrieve_history_filter(statuses)
        if chosen is None:
            return None
        kind, value = chosen
        if kind == "status":
            matches = self._data.filter_audits_by_status(audits, value)
        else:
            matches = self._data.search_audits_by_company(audits, value)
        if not matches:
            self._io.show_no_matching_audits()
            return None
        return matches

    def export_audit_flow(self, audit: Record) -> None:
        """Offers a PDF report for one audit, built from the saved history entry."""
        if self._io.confirm_export_pdf():
            file_name, status = self._data.export_audit_to_pdf(audit)
            self._io.show_pdf_result(status, file_name, self._data.get_records_folder())

    def audit_history_flow(self, username: str) -> None:
        audits = self._data.get_user_audits(username)
        shown = audits
        while True:
            if not self._io.display_audit_history(
                shown, username, filtered=shown is not audits
            ):
                return
            action, index = self._io.choose_history_action(shown)
            if action == "back":
                return
            if action == "filter":
                shown = self.apply_history_filter(audits) or audits
                continue
            self._io.display_audit_detail(shown[index])
            self.export_audit_flow(shown[index])
            self._io.wait_for_return()
            return

    # ========================================================
    # Saving and loading records: I/O asks -> Data stores/reads -> I/O reports
    # ========================================================
    def save_records_flow(
    self, records: Records, jsonfile_name: str
) -> tuple[str, bool]:
        """Asks for a file name if needed, merges with an existing file if the
        user agrees, saves, and returns (jsonfile_name, saved).
        On cancel or failure the original name is returned with saved=False."""
        target = jsonfile_name
        if not target:
            target = self._io.retrieve_json_filename(
                self._data.INVALID_FILENAME_CHARS, for_loading=False
            )
            if target is None:                       # blank entry = cancel
                self._io.display_save_result("no_name", "")
                return jsonfile_name, False

        clean_name, status = self._data.inspect_save_file(target)
        if status in ("no_name", "invalid_name"):
            self._io.display_save_result(status, target)
            return jsonfile_name, False

        to_save = records
        if status == "exists":
            action = self._io.ask_existing_file_action(clean_name)
            if action == "cancel":
                return jsonfile_name, False
            if action == "add":
                existing, _, load_status = self._data.load_data_from_json(clean_name)
                if load_status != "loaded":
                    self._io.display_load_result(load_status, clean_name)
                    return jsonfile_name, False
                to_save = self._data.merge_records(existing, records)
            # "replace": the file will hold exactly the records in memory

        saved_name, save_status = self._data.save_data_to_json(to_save, clean_name)
        self._io.display_save_result(save_status, clean_name)
        return (saved_name or clean_name), save_status == "saved"

    def offer_save_before_leaving(self, session: Session) -> bool:
        """Returns True if it is OK to leave (nothing unsaved, saved, or the
        user chose not to save). False if the user cancelled the save."""
        if not (session.dirty and session.records):
            return True
        if not self._io.confirm_unsaved_exit():      # answered "n": leave without saving
            return True
        session.jsonfile_name, saved = self.save_records_flow(
            session.records, session.jsonfile_name
        )
        if saved:
            session.dirty = False
            return True
        self._io.show_leave_cancelled()   # e.g. "Save cancelled. Your records are still in memory."
        return False                               # cancelled or failed: stay
    
    def load_records_flow(
    self, records: Records, jsonfile_name: str
) -> tuple[Records, str]:
        """Prompts for a file name, confirms before replacing records in memory,
        loads, shows the result, and returns (records, jsonfile_name).
        On cancel or failure both are unchanged."""
        new_name = self._io.retrieve_json_filename(
            self._data.INVALID_FILENAME_CHARS, for_loading=True
        )
        if new_name is None:                      # blank entry = cancel, no prompt
            self._io.display_load_result("no_name", "")
            return records, jsonfile_name


        if self._data.is_data_loaded(records, jsonfile_name) and (
            not self._io.confirm_overwrite_records()
        ):
            return records, jsonfile_name         # user answered "n"

        loaded, clean_name, status = self._data.load_data_from_json(new_name)
        self._io.display_load_result(status, clean_name or new_name)

        if status == "loaded":
            return loaded, clean_name
        return records, jsonfile_name

    # ========================================================
    # Menu option 1: collect a new application and audit it
    # ========================================================
    def collect_application(self) -> Record:
        """Asks the I/O Manager for every field and returns one record. The
        proposal kind decides which extra details are asked for."""
        io = self._io
        company_name = io.retrieve_company_name()
        company_industry = io.retrieve_company_industry()
        total_revenue = io.retrieve_total_revenue()
        total_employees = io.retrieve_total_employees()
        local_equity = io.retrieve_local_equity()
        proposal_type = io.retrieve_proposal_type()
        sustainability_grant = io.retrieve_sustainability_grant()
        proposal_narrative = io.retrieve_proposal_narrative()

        details = Proposal.for_type(proposal_type).collect_details(io)

        io.display_company_profile(
            company_name,
            company_industry,
            total_revenue,
            total_employees,
            local_equity,
            proposal_type,
            sustainability_grant,
            proposal_narrative,
            details["Baseline Energy Expenditure"],
            details["Estimated Retrofit Cost"],
            details["Reporting Advisory Fee"],
        )
        return {
            "Company Name": company_name,
            "Company Industry": company_industry,
            "Company Total Revenue": total_revenue,
            "Total Employees": total_employees,
            "Local Equity": local_equity,
            "Proposal Type": proposal_type,
            "Sustainability Grant": sustainability_grant,
            "Proposal Narrative": proposal_narrative,
            "Baseline Energy Expenditure": details["Baseline Energy Expenditure"],
            "Estimated Retrofit Cost": details["Estimated Retrofit Cost"],
            "Reporting Advisory Fee": details["Reporting Advisory Fee"],
        }

    def new_application_flow(self, session: Session, key: int) -> None:
        """Menu option 1: collect, audit with AI + Logic, keep in history, and
        offer to save the record to a JSON file."""
        session.records.append(self.collect_application())
        session.dirty = True
        self._io.display_applied_grants(session.records, key)

        # The AI Manager and Logic Manager run automatically on the record just
        # collected (menu options 7 and 8 re-run them by hand).
        session.ai_audit, result = self.run_audit(session.records[-1])

        # Every completed audit is kept in the user's history, unless the AI call
        # itself failed (missing API key, timeout, unusable answer): that result
        # is only a placeholder, not a real audit.
        if result is None:
            pass  # a step raised; the error was already shown
        elif self._ai.ai_call_failed(session.ai_audit):
            self._io.show_audit_not_saved_ai_failed()
        else:
            saved_audit = self._data.append_user_audit(
                session.username, session.records[-1], session.ai_audit, result
            )
            self._io.show_audit_saved_to_history(saved_audit)

        if self._io.confirm_save_to_json():
            session.jsonfile_name, saved = self.save_records_flow(
                session.records, session.jsonfile_name
            )
            if saved:
                session.dirty = False

    def update_record_flow(self, session: Session) -> None:
        """Menu option 5: change one detail of one record in memory."""
        records = session.records
        if not records:
            self._io.display_no_records_message()
            return

        index = self._io.select_record_index(records, "update")
        field = None if index is None else self._io.select_field_to_edit(records[index])
        if field is None:
            return

        # Records loaded from a file may use the nested layout; the editor works
        # on the flat layout the screens use.
        records[index] = ApplicationRecord(records[index]).flat
        value = self._io.retrieve_field_value(field)
        session.records, status = self._data.update_record_field(
            records, index, field, value
        )

        if status == "updated":
            session.dirty = True
            self._io.show_record_updated(
                session.records[index].get("Company Name") or "N/A", field
            )
        else:
            self._io.show_record_not_changed()

    def delete_record_flow(self, session: Session) -> None:
        """Menu option 6: remove one record from memory."""
        records = session.records
        if not records:
            self._io.display_no_records_message()
            return

        index = self._io.select_record_index(records, "delete")
        if index is None:
            return

        name = ApplicationRecord(records[index]).company_name
        if not self._io.confirm_delete_record(name):
            self._io.show_record_not_changed()
            return

        session.records, status = self._data.delete_record(records, index)
        if status == "deleted":
            session.dirty = True
            self._io.show_record_deleted(name)
        else:
            self._io.show_record_not_changed()

    def rerun_ai_flow(self, session: Session) -> None:
        """Menu option 7: run the AI Manager again on the latest record."""
        if not session.records:
            self._io.display_no_records_message()
            return
        narrative = ApplicationRecord(session.records[-1]).narrative
        ok, new_audit = self.attempt(self.ask_ai, narrative)
        if ok:
            session.ai_audit = new_audit
            self._io.display_ai_audit(new_audit)

    def rerun_logic_flow(self, session: Session) -> None:
        """Menu option 8: run the Logic Manager again on the latest record."""
        if not session.records:
            self._io.display_no_records_message()
        elif not session.ai_audit:
            self._io.display_no_ai_audit()
        else:
            user_profile = ApplicationRecord(session.records[-1]).to_profile()
            ok, result = self.attempt(
                self._logic.evaluate_grant_application, user_profile, session.ai_audit
            )
            if ok:
                self._io.display_grant_decision(result)

    # ========================================================
    # One logged-in session
    # ========================================================
    def run_session(self, username: str) -> bool:
        """Shows the main menu until the user logs out (returns True, so the
        login screen comes back) or exits the program (returns False)."""
        # Saved record files (options 2/3) live in this user's own folder.
        self._data.active_user = username
        self._io.show_audit_count(len(self._data.get_user_audits(username)))
        session = Session(username)

        while True:
            key = self._io.get_menu_choice(username)

            match key:
                case 0:
                    if not self.offer_save_before_leaving(session):
                        continue                                  # back to the menu
                    self._io.show_goodbye()
                    return False
                case 1:
                    self.new_application_flow(session, key)
                case 2:  # Save to JSON
                    session.jsonfile_name, saved = self.save_records_flow(
                        session.records, session.jsonfile_name
                    )
                    if saved:
                        session.dirty = False
                case 3: #Pull from JSON
                    before = session.records
                    session.records, session.jsonfile_name = self.load_records_flow(
                        session.records, session.jsonfile_name
                    )
                    if session.records is not before:
                        session.dirty = False
                case 4:  # Display the current records
                    self._io.display_applied_grants(session.records, key)
                case 5:  # Update a record
                    self.update_record_flow(session)
                case 6:  # Delete a record
                    self.delete_record_flow(session)
                case 7:
                    self.rerun_ai_flow(session)
                case 8:
                    self.rerun_logic_flow(session)
                case IOManager.MENU_AUDIT_HISTORY:  # 9: past audits of this user
                    self.audit_history_flow(username)
                case IOManager.MENU_LOGOUT:  # 10: back to the login screen
                    if not self.offer_save_before_leaving(session):
                        continue
                    self._io.show_logged_out(username)
                    self._data.active_user = None
                    return True
                case _:
                    self._io.show_wrong_option_error()

    def login_screen(self) -> str | None:
        """Shows the login screen until someone logs in. Returns the username,
        or None if the user chose to exit."""
        while True:
            match self._io.get_auth_choice():
                case 0:
                    self._io.show_goodbye()
                    return None
                case 1:
                    username = self.login_flow()
                    if username is not None:
                        return username
                case 2:
                    self.create_account_flow()
                case _:
                    self._io.show_wrong_option_error()

    def run(self) -> None:
        sys.excepthook = self.handle_uncaught
        self._data.setup_logging()
        self._io.show_welcome_sequence()
        self._io.wait_for_continue()

        while True:
            username = self.login_screen()
            if username is None:
                break
            if not self.run_session(username):
                break


if __name__ == "__main__":
    Application.launch()