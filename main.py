import sys


# Load OPENROUTER_API_KEY from a local .env file when running outside
# Docker. Inside Docker the variable is injected via --env-file instead.
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass


import io_manager as in_and_out
import data_manager as dm
import ai_manager as ai
import logic_manager as logic
from sme_interface_stores.sme_interface_gui import continue_button


# ========================================================
# Clean exit on Ctrl+C / end of input
# ========================================================
# Without this, pressing Ctrl+C at any prompt (or running Docker without
# -it, so there is no keyboard input) ends the program with a long
# traceback. Every other error still shows its normal traceback.
def _handle_uncaught(exc_type, exc, tb):
    if issubclass(exc_type, KeyboardInterrupt):
        print("\n\nInterrupted. Goodbye!")
    elif issubclass(exc_type, EOFError):
        print("\n\nNo more input available. If you run the app in Docker, "
              "start it with 'docker run -it ...' so you can type into it.")
    else:
        sys.__excepthook__(exc_type, exc, tb)



# ========================================================
# Account flows: I/O collects -> Logic hashes/verifies -> Data stores
# ========================================================
def create_account_flow():
    username = in_and_out.retrieve_new_username()
    while dm.user_exists(username):
        in_and_out.show_username_taken(username)
        username = in_and_out.retrieve_new_username()

    password = in_and_out.retrieve_new_password()
    user_record = logic.build_new_user_record(username, password)

    if dm.save_new_user(user_record):
        in_and_out.show_account_created(username)
    else:
        in_and_out.show_account_save_failed()


def login_flow():
    """Returns the logged-in username, or None if login failed."""
    username = in_and_out.retrieve_username()
    password = in_and_out.retrieve_password()

    stored_user = dm.get_user(username)
    # The format check also guards against a hand-edited users.json holding
    # a name that cannot be used for the user's folder.
    if in_and_out.is_valid_username(username) and logic.verify_password(password, stored_user):
        in_and_out.show_login_success(username)
        return username

    in_and_out.show_login_failed()
    return None


def attempt(step, *args):
    """Runs one risky step (AI call, grant logic). Returns (True, result), or
    (False, None) after showing a short message if it raised, so one
    unexpected error can no longer end the whole program. Ctrl+C and end of
    input are passed through so they still exit cleanly."""
    try:
        return True, step(*args)
    except (KeyboardInterrupt, EOFError):
        raise
    except Exception as error:
        in_and_out.show_unexpected_error(error)
        return False, None


def ask_ai(narrative):
    """AI Manager call. The waiting screen belongs to the I/O Manager, so it
    is handed over as a function and the AI Manager never prints."""
    return ai.get_ai_response(narrative, in_and_out.run_ai_analysis_bar)


def run_audit(record):
    """AI Manager -> Logic Manager for one record, displaying both results.
    Returns (ai_audit, result); result is None if a step failed."""
    narrative = in_and_out.flat_record(record).get("Proposal Narrative", "")
    ok, ai_audit = attempt(ask_ai, narrative)
    if not ok:
        return {}, None
    in_and_out.display_ai_audit(ai_audit)

    ok, result = attempt(
        logic.evaluate_grant_application, in_and_out.convert_record_to_profile(record), ai_audit
    )
    if not ok:
        return ai_audit, None
    in_and_out.display_grant_decision(result)
    return ai_audit, result


def update_record_flow(records, jsonfile_name, key):
    """Option 5: I/O picks the record and collects the new values, the Data
    Manager applies the change. Returns (records, jsonfile_name)."""
    index = in_and_out.select_record(records, key, "update")
    if index is None:
        return records, jsonfile_name
    updated = in_and_out.retrieve_updated_record(records[index - 1])
    records, jsonfile_name, status = dm.update_record_by_index(records, index, updated, jsonfile_name)
    in_and_out.display_edit_result(status, updated.get("Company Name", "Unknown"))
    return records, jsonfile_name


def delete_record_flow(records, jsonfile_name, key):
    """Option 6: confirm with the user, then the Data Manager deletes."""
    index = in_and_out.select_record(records, key, "delete")
    if index is None:
        return records, jsonfile_name
    name = records[index - 1].get("Company Name", "Unknown")
    if not in_and_out.confirm_delete(name):
        return records, jsonfile_name
    records, jsonfile_name, status = dm.delete_record_by_index(records, index, jsonfile_name)
    in_and_out.display_edit_result(status, name)
    return records, jsonfile_name


def audit_history_flow(username):
    audits = dm.get_user_audits(username)
    if not in_and_out.display_audit_history(audits, username):
        return
    index = in_and_out.select_audit_record(audits)
    if index is not None:
        in_and_out.display_audit_detail(audits[index])


# ========================================================
# Saving and loading records: I/O asks -> Data stores/reads -> I/O reports
# ========================================================
def save_records_flow(records, jsonfile_name):
    """Asks for a file name if needed, merges with an existing file if the
    user agrees, saves, and returns the (possibly updated) jsonfile_name."""
    if not jsonfile_name:
        jsonfile_name = in_and_out.retrieve_json_filename(dm.INVALID_FILENAME_CHARS)

    clean_name, status = dm.inspect_save_file(jsonfile_name)
    if status in ("no_name", "invalid_name"):
        in_and_out.display_save_result(status, jsonfile_name)
        return ""

    to_save = records
    if status == "exists":
        if not in_and_out.confirm_append_to_existing_file(clean_name):
            return clean_name
        existing, _, load_status = dm.load_data_from_json(clean_name)
        if load_status != "loaded":
            in_and_out.display_load_result(load_status, clean_name)
            return clean_name
        to_save = dm.merge_records(existing, records)

    saved_name, save_status = dm.save_data_to_json(to_save, clean_name)
    in_and_out.display_save_result(save_status, clean_name)
    return saved_name or clean_name


def load_records_flow(records, jsonfile_name):
    """Confirms before replacing records in memory, loads, shows the result,
    and returns (records, jsonfile_name). On failure both are unchanged."""
    if dm.is_data_loaded(records, jsonfile_name) and not in_and_out.confirm_overwrite_records():
        return records, jsonfile_name

    name = in_and_out.retrieve_json_filename(dm.INVALID_FILENAME_CHARS, 3)  # 3 = show the 'load' disk
    loaded, clean_name, status = dm.load_data_from_json(name)
    in_and_out.display_load_result(status, clean_name or name)

    if status == "loaded":
        return loaded, clean_name
    return records, jsonfile_name


# ========================================================
# Menu option 1: collect a new application and audit it
# ========================================================
def collect_application():
    """Asks the I/O Manager for every field and returns one record."""
    company_name = in_and_out.retrieve_company_name()
    company_industry = in_and_out.retrieve_company_industry()
    total_revenue = in_and_out.retrieve_total_revenue()
    total_employees = in_and_out.retrieve_total_employees()
    local_equity = in_and_out.retrieve_local_equity()
    proposal_type = in_and_out.retrieve_proposal_type()
    sustainability_grant = in_and_out.retrieve_sustainability_grant()
    proposal_narrative = in_and_out.retrieve_proposal_narrative()

    if proposal_type == "Equipment / Energy Upgrade":
        baseline_energy_expenditure = in_and_out.retrieve_baseline_energy_expenditure()
        retrofit_cost = in_and_out.retrieve_estimated_retrofit_cost()
        reporting_advisory_fee = 0.0
    else:
        baseline_energy_expenditure = 0.0
        retrofit_cost = 0.0
        reporting_advisory_fee = in_and_out.retrieve_reporting_advisory_fee()

    in_and_out.display_company_profile(
        company_name, company_industry, total_revenue, total_employees,
        local_equity, proposal_type, sustainability_grant,
        proposal_narrative, baseline_energy_expenditure, retrofit_cost,
        reporting_advisory_fee
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
        "Baseline Energy Expenditure": baseline_energy_expenditure,
        "Estimated Retrofit Cost": retrofit_cost,
        "Reporting Advisory Fee": reporting_advisory_fee,
    }


def new_application_flow(session, key):
    """Menu option 1: collect, audit with AI + Logic, keep in history, and
    offer to save the record to a JSON file."""
    session["records"].append(collect_application())
    in_and_out.display_applied_grants(session["records"], key)

    # The AI Manager and Logic Manager run automatically on the record just
    # collected (menu options 7 and 8 re-run them by hand).
    session["ai_audit"], result = run_audit(session["records"][-1])

    # Every completed audit is kept in the user's history, unless the AI call
    # itself failed (missing API key, timeout, unusable answer) - that result
    # is only a placeholder, not a real audit.
    if result is None:
        pass  # a step raised; the error was already shown
    elif ai.ai_call_failed(session["ai_audit"]):
        in_and_out.show_audit_not_saved_ai_failed()
    else:
        saved_audit = dm.append_user_audit(
            session["username"], session["records"][-1], session["ai_audit"], result
        )
        in_and_out.show_audit_saved_to_history(saved_audit)

    if in_and_out.confirm_save_to_json():
        session["jsonfile_name"] = save_records_flow(session["records"], session["jsonfile_name"])


def rerun_ai_flow(session):
    """Menu option 7: run the AI Manager again on the latest record."""
    if not session["records"]:
        in_and_out.display_no_records_message()
        return
    narrative = in_and_out.flat_record(session["records"][-1]).get("Proposal Narrative", "")
    ok, new_audit = attempt(ask_ai, narrative)
    if ok:
        session["ai_audit"] = new_audit
        in_and_out.display_ai_audit(new_audit)


def rerun_logic_flow(session):
    """Menu option 8: run the Logic Manager again on the latest record."""
    if not session["records"]:
        in_and_out.display_no_records_message()
    elif not session["ai_audit"]:
        in_and_out.display_no_ai_audit()
    else:
        user_profile = in_and_out.convert_record_to_profile(session["records"][-1])
        ok, result = attempt(logic.evaluate_grant_application, user_profile, session["ai_audit"])
        if ok:
            in_and_out.display_grant_decision(result)


# ========================================================
# One logged-in session
# ========================================================
def run_session(username):
    """Shows the main menu until the user logs out (returns True, so the
    login screen comes back) or exits the program (returns False)."""
    # Saved record files (options 2/3) live in this user's own folder.
    dm.set_active_user(username)
    session = {"username": username, "records": [], "ai_audit": {}, "jsonfile_name": ""}

    while True:
        key = in_and_out.get_menu_choice(username)

        match key:
            case 0:
                in_and_out.show_goodbye()
                return False
            case 1:
                new_application_flow(session, key)
            case 2:  # Save to JSON
                session["jsonfile_name"] = save_records_flow(session["records"], session["jsonfile_name"])
            case 3:  # Pull from JSON
                session["records"], session["jsonfile_name"] = load_records_flow(
                    session["records"], session["jsonfile_name"]
                )
            case 4:  # Display the current records
                in_and_out.display_applied_grants(session["records"], key)
            case 5:  # Update
                session["records"], session["jsonfile_name"] = update_record_flow(
                    session["records"], session["jsonfile_name"], key
                )
            case 6:  # Delete
                session["records"], session["jsonfile_name"] = delete_record_flow(
                    session["records"], session["jsonfile_name"], key
                )
            case 7:
                rerun_ai_flow(session)
            case 8:
                rerun_logic_flow(session)
            case in_and_out.MENU_AUDIT_HISTORY:  # 9: Past audits of the logged-in user
                audit_history_flow(username)
            case in_and_out.MENU_LOGOUT:  # 10: Back to the login screen
                in_and_out.show_logged_out(username)
                dm.set_active_user(None)
                return True
            case _:
                in_and_out.show_wrong_option_error()


def login_screen():
    """Shows the login screen until someone logs in. Returns the username,
    or None if the user chose to exit."""
    while True:
        match in_and_out.get_auth_choice():
            case 0:
                in_and_out.show_goodbye()
                return None
            case 1:
                username = login_flow()
                if username is not None:
                    return username
            case 2:
                create_account_flow()
            case _:
                in_and_out.show_wrong_option_error()


def main():
    sys.excepthook = _handle_uncaught
    in_and_out.show_welcome_sequence()
    continue_button()

    while True:
        username = login_screen()
        if username is None:
            break
        if not run_session(username):
            break


if __name__ == "__main__":
    main()
