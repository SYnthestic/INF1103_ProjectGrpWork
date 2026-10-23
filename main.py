"""Controller: passes data between the four managers. It has no print()
or input(); everything the user sees goes through the I/O Manager."""

import sys
from abc import ABC, abstractmethod
from collections.abc import Callable
from types import TracebackType
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

import ai_manager
import data_manager
import io_manager
import logic_manager

Record = dict[str, Any]
Records = list[Record]
AiAudit = dict[str, Any]


# ========================================================
# Shared objects
# ========================================================
class Services:
    """The four managers, handed to every controller class instead of being
    imported as globals. Tests can pass mocks, and the modules can later be
    replaced by manager classes without touching the controllers (association)."""

    def __init__(self, io=io_manager, data=data_manager, ai=ai_manager, logic=logic_manager):
        self.io = io
        self.dm = data
        self.ai = ai
        self.logic = logic


class Session:
    """State of one logged-in user. The username cannot be changed."""

    def __init__(self, username: str):
        self._username = username
        self.records: Records = []
        self.ai_audit: AiAudit = {}
        self.jsonfile_name: str = ""
        self.ending: str | None = None  # None, "exit" or "logout"

    @property
    def username(self) -> str:
        return self._username


# ========================================================
# Services used by several actions
# ========================================================
class AuditService:
    """AI Manager -> Logic Manager for one record."""

    def __init__(self, services: Services):
        self._s = services

    def attempt(self, step: Callable[..., Any], *args: Any) -> tuple[bool, Any]:
        """Runs one risky step. Returns (True, result), or (False, None) after
        showing a message. Ctrl+C and end of input still exit cleanly."""
        try:
            return True, step(*args)
        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as error:
            self._s.io.show_unexpected_error(error)
            return False, None

    def ask_ai(self, narrative: str) -> AiAudit:
        # The waiting screen belongs to the I/O Manager, so it is handed over
        # as a function and the AI Manager never prints.
        return self._s.ai.get_ai_response(narrative, self._s.io.run_ai_analysis_bar)

    def run_audit(self, record: Record) -> tuple[AiAudit, dict[str, Any] | None]:
        io = self._s.io
        narrative = io.flat_record(record).get("Proposal Narrative", "")
        ok, ai_audit = self.attempt(self.ask_ai, narrative)
        if not ok:
            return {}, None
        io.display_ai_audit(ai_audit)

        ok, result = self.attempt(
            self._s.logic.evaluate_grant_application,
            io.convert_record_to_profile(record),
            ai_audit,
        )
        if not ok:
            return ai_audit, None
        io.display_grant_decision(result)
        return ai_audit, result


class RecordStorage:
    """Saving and loading record files: I/O asks -> Data stores -> I/O reports."""

    def __init__(self, services: Services):
        self._s = services

    def save(self, records: Records, jsonfile_name: str) -> str:
        io, dm = self._s.io, self._s.dm
        if not jsonfile_name:
            jsonfile_name = io.retrieve_json_filename(dm.INVALID_FILENAME_CHARS)

        clean_name, status = dm.inspect_save_file(jsonfile_name)
        if status in ("no_name", "invalid_name"):
            io.display_save_result(status, jsonfile_name)
            return ""

        to_save = records
        if status == "exists":
            action = io.ask_existing_file_action(clean_name)
            if action == "cancel":
                return clean_name
            if action == "add":
                existing, _, load_status = dm.load_data_from_json(clean_name)
                if load_status != "loaded":
                    io.display_load_result(load_status, clean_name)
                    return clean_name
                to_save = dm.merge_records(existing, records)

        saved_name, save_status = dm.save_data_to_json(to_save, clean_name)
        io.display_save_result(save_status, clean_name)
        return saved_name or clean_name

    def load(self, records: Records, jsonfile_name: str) -> tuple[Records, str]:
        io, dm = self._s.io, self._s.dm
        if dm.is_data_loaded(records, jsonfile_name) and not io.confirm_overwrite_records():
            return records, jsonfile_name

        name = io.retrieve_json_filename(dm.INVALID_FILENAME_CHARS, 3)  # 3 = 'load' disk
        loaded, clean_name, status = dm.load_data_from_json(name)
        io.display_load_result(status, clean_name or name)
        return (loaded, clean_name) if status == "loaded" else (records, jsonfile_name)


# ========================================================
# Menu actions: one class per menu option
# ========================================================
class Action(ABC):
    """Abstract base for every menu option."""

    def __init__(self, services: Services, key: int):
        self._s = services
        self._key = key

    @abstractmethod
    def run(self, session: Session) -> None: ...


class NewApplicationAction(Action):
    """Collect an application, audit it, keep it in history, offer to save."""

    def __init__(self, services, key, audits: AuditService, storage: RecordStorage):
        super().__init__(services, key)
        self._audits = audits
        self._storage = storage

    def _collect(self) -> Record:
        io = self._s.io
        company_name = io.retrieve_company_name()
        company_industry = io.retrieve_company_industry()
        total_revenue = io.retrieve_total_revenue()
        total_employees = io.retrieve_total_employees()
        local_equity = io.retrieve_local_equity()
        proposal_type = io.retrieve_proposal_type()
        sustainability_grant = io.retrieve_sustainability_grant()
        proposal_narrative = io.retrieve_proposal_narrative()

        if proposal_type == "Equipment / Energy Upgrade":
            baseline = io.retrieve_baseline_energy_expenditure()
            retrofit = io.retrieve_estimated_retrofit_cost()
            fee = 0.0
        else:
            baseline = retrofit = 0.0
            fee = io.retrieve_reporting_advisory_fee()

        io.display_company_profile(
            company_name, company_industry, total_revenue, total_employees,
            local_equity, proposal_type, sustainability_grant, proposal_narrative,
            baseline, retrofit, fee,
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
            "Baseline Energy Expenditure": baseline,
            "Estimated Retrofit Cost": retrofit,
            "Reporting Advisory Fee": fee,
        }

    def run(self, session: Session) -> None:
        io, dm = self._s.io, self._s.dm
        session.records.append(self._collect())
        io.display_applied_grants(session.records, self._key)

        session.ai_audit, result = self._audits.run_audit(session.records[-1])

        if result is None:
            pass  # a step raised; the error was already shown
        elif self._s.ai.ai_call_failed(session.ai_audit):
            io.show_audit_not_saved_ai_failed()
        else:
            saved = dm.append_user_audit(
                session.username, session.records[-1], session.ai_audit, result
            )
            io.show_audit_saved_to_history(saved)

        if io.confirm_save_to_json():
            session.jsonfile_name = self._storage.save(session.records, session.jsonfile_name)


class SaveAction(Action):
    def __init__(self, services, key, storage: RecordStorage):
        super().__init__(services, key)
        self._storage = storage

    def run(self, session: Session) -> None:
        session.jsonfile_name = self._storage.save(session.records, session.jsonfile_name)


class LoadAction(Action):
    def __init__(self, services, key, storage: RecordStorage):
        super().__init__(services, key)
        self._storage = storage

    def run(self, session: Session) -> None:
        session.records, session.jsonfile_name = self._storage.load(
            session.records, session.jsonfile_name
        )


class DisplayAction(Action):
    def run(self, session: Session) -> None:
        self._s.io.display_applied_grants(session.records, self._key)


class UpdateAction(Action):
    def run(self, session: Session) -> None:
        io, dm = self._s.io, self._s.dm
        records = session.records
        if not records:
            io.display_no_records_message()
            return

        index = io.select_record_index(records, "update")
        field = None if index is None else io.select_field_to_edit(records[index])
        if field is None:
            return

        records[index] = io.flat_record(records[index])
        value = io.retrieve_field_value(field)
        session.records, status = dm.update_record_field(records, index, field, value)

        if status == "updated":
            io.show_record_updated(session.records[index].get("Company Name") or "N/A", field)
        else:
            io.show_record_not_changed()


class DeleteAction(Action):
    def run(self, session: Session) -> None:
        io, dm = self._s.io, self._s.dm
        records = session.records
        if not records:
            io.display_no_records_message()
            return

        index = io.select_record_index(records, "delete")
        if index is None:
            return

        name = io.flat_record(records[index]).get("Company Name") or "N/A"
        if not io.confirm_delete_record(name):
            io.show_record_not_changed()
            return

        session.records, status = dm.delete_record(records, index)
        if status == "deleted":
            io.show_record_deleted(name)
        else:
            io.show_record_not_changed()


class RerunAiAction(Action):
    def __init__(self, services, key, audits: AuditService):
        super().__init__(services, key)
        self._audits = audits

    def run(self, session: Session) -> None:
        io = self._s.io
        if not session.records:
            io.display_no_records_message()
            return
        narrative = io.flat_record(session.records[-1]).get("Proposal Narrative", "")
        ok, new_audit = self._audits.attempt(self._audits.ask_ai, narrative)
        if ok:
            session.ai_audit = new_audit
            io.display_ai_audit(new_audit)


class RerunLogicAction(Action):
    def __init__(self, services, key, audits: AuditService):
        super().__init__(services, key)
        self._audits = audits

    def run(self, session: Session) -> None:
        io = self._s.io
        if not session.records:
            io.display_no_records_message()
        elif not session.ai_audit:
            io.display_no_ai_audit()
        else:
            profile = io.convert_record_to_profile(session.records[-1])
            ok, result = self._audits.attempt(
                self._s.logic.evaluate_grant_application, profile, session.ai_audit
            )
            if ok:
                io.display_grant_decision(result)


class HistoryAction(Action):
    """Past audits of the logged-in user, with filtering and PDF export."""

    def _apply_filter(self, audits: list[Record]) -> list[Record] | None:
        io, dm = self._s.io, self._s.dm
        chosen = io.retrieve_history_filter(dm.available_audit_statuses(audits))
        if chosen is None:
            return None
        kind, value = chosen
        if kind == "status":
            matches = dm.filter_audits_by_status(audits, value)
        else:
            matches = dm.search_audits_by_company(audits, value)
        if not matches:
            io.show_no_matching_audits()
            return None
        return matches

    def _export(self, audit: Record) -> None:
        io, dm = self._s.io, self._s.dm
        if io.confirm_export_pdf():
            file_name, status = dm.export_audit_to_pdf(audit)
            io.show_pdf_result(status, file_name, dm.get_records_folder())

    def run(self, session: Session) -> None:
        io = self._s.io
        audits = self._s.dm.get_user_audits(session.username)
        shown = audits
        while True:
            if not io.display_audit_history(shown, session.username, filtered=shown is not audits):
                return
            action, index = io.choose_history_action(shown)
            if action == "back":
                return
            if action == "filter":
                shown = self._apply_filter(audits) or audits
                continue
            io.display_audit_detail(shown[index])
            self._export(shown[index])
            io.wait_for_return()
            return


class LogoutAction(Action):
    def run(self, session: Session) -> None:
        self._s.io.show_logged_out(session.username)
        self._s.dm.set_active_user(None)
        session.ending = "logout"


class ExitAction(Action):
    def run(self, session: Session) -> None:
        self._s.io.show_goodbye()
        session.ending = "exit"


# ========================================================
# Login screen
# ========================================================
class AuthController:
    """I/O collects -> Logic hashes/verifies -> Data stores."""

    def __init__(self, services: Services):
        self._s = services

    def create_account(self) -> None:
        io, dm = self._s.io, self._s.dm
        username = io.retrieve_new_username()
        while dm.user_exists(username):
            io.show_username_taken(username)
            username = io.retrieve_new_username()

        password = io.retrieve_new_password()
        record = self._s.logic.build_new_user_record(username, password)
        if dm.save_new_user(record):
            io.show_account_created(username)
        else:
            io.show_account_save_failed()

    def login(self) -> str | None:
        io = self._s.io
        username = io.retrieve_username()
        password = io.retrieve_password()
        stored = self._s.dm.get_user(username)
        # The format check also guards against a hand-edited users.json
        # holding a name that cannot be used for the user's folder.
        if io.is_valid_username(username) and self._s.logic.verify_password(password, stored):
            io.show_login_success(username)
            return username
        io.show_login_failed()
        return None

    def login_screen(self) -> str | None:
        """Returns the username, or None if the user chose to exit."""
        io = self._s.io
        while True:
            match io.get_auth_choice():
                case 0:
                    io.show_goodbye()
                    return None
                case 1:
                    username = self.login()
                    if username is not None:
                        return username
                case 2:
                    self.create_account()
                case _:
                    io.show_wrong_option_error()


# ========================================================
# The application
# ========================================================
class Application:
    """Owns the services and the menu, and runs the program."""

    def __init__(self, services: Services | None = None):
        self._s = services or Services()
        self._auth = AuthController(self._s)
        self._menu = self._build_menu()

    def _build_menu(self) -> dict[int, Action]:
        s, io = self._s, self._s.io
        audits = AuditService(s)
        storage = RecordStorage(s)
        actions = [
            ExitAction(s, 0),
            NewApplicationAction(s, 1, audits, storage),
            SaveAction(s, 2, storage),
            LoadAction(s, 3, storage),
            DisplayAction(s, 4),
            UpdateAction(s, 5),
            DeleteAction(s, 6),
            RerunAiAction(s, 7, audits),
            RerunLogicAction(s, 8, audits),
            HistoryAction(s, io.MENU_AUDIT_HISTORY),
            LogoutAction(s, io.MENU_LOGOUT),
        ]
        return {action._key: action for action in actions}

    def run_session(self, username: str) -> bool:
        """True = back to the login screen, False = leave the program."""
        io, dm = self._s.io, self._s.dm
        dm.set_active_user(username)
        io.show_audit_count(len(dm.get_user_audits(username)))
        session = Session(username)

        while session.ending is None:
            action = self._menu.get(io.get_menu_choice(username))
            if action is None:
                io.show_wrong_option_error()
            else:
                action.run(session)  # polymorphism: no branching on the type
        return session.ending == "logout"

    def run(self) -> None:
        io = self._s.io
        self._s.dm.setup_logging()
        io.show_welcome_sequence()
        io.wait_for_continue()

        while True:
            username = self._auth.login_screen()
            if username is None or not self.run_session(username):
                break


def _handle_uncaught(exc_type: type[BaseException], exc: BaseException,
                     tb: TracebackType | None) -> None:
    """Clean exit on Ctrl+C or end of input; other errors keep their traceback."""
    if issubclass(exc_type, KeyboardInterrupt):
        io_manager.show_interrupted()
    elif issubclass(exc_type, EOFError):
        io_manager.show_input_ended()
    else:
        sys.__excepthook__(exc_type, exc, tb)


def main() -> None:
    sys.excepthook = _handle_uncaught
    Application().run()


if __name__ == "__main__":
    main()