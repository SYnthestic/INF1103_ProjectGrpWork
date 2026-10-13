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


sys.excepthook = _handle_uncaught


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


def run_audit(record):
    """AI Manager -> Logic Manager for one record, displaying both results.
    Returns (ai_audit, result); result is None if a step failed."""
    ok, ai_audit = attempt(ai.get_ai_response, in_and_out.flat_record(record).get("Proposal Narrative", ""))
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


def audit_history_flow(username):
    audits = dm.get_user_audits(username)
    if not in_and_out.display_audit_history(audits, username):
        return
    index = in_and_out.select_audit_record(audits)
    if index is not None:
        in_and_out.display_audit_detail(audits[index])


# Code
in_and_out.show_welcome_sequence()
# Test the fixed engine
continue_button()

running = True
while running:
    # ---------- Login screen ----------
    current_user = None
    while current_user is None and running:
        auth_choice = in_and_out.get_auth_choice()
        match auth_choice:
            case 0:
                in_and_out.show_goodbye()
                running = False
            case 1:
                current_user = login_flow()
            case 2:
                create_account_flow()
            case _:
                in_and_out.show_wrong_option_error()

    if not running:
        break

    # ---------- Fresh session state for each login ----------
    # Saved record files (options 2/3) live in this user's own folder.
    dm.set_active_user(current_user)
    scheme_grant_records = []
    ai_audit_data = {}
    jsonfile_name = ""

    key = None
    while key != 0 and key != in_and_out.MENU_LOGOUT:
        key = in_and_out.get_menu_choice(current_user)

        match key:
            case 0:
                in_and_out.show_goodbye()
                running = False
            case 1: # Start checks
                company_name = in_and_out.retrieve_company_name()
                company_industry = in_and_out.retrieve_company_industry()
                get_total_revenue = in_and_out.retrieve_total_revenue()
                total_employees = in_and_out.retrieve_total_employees()
                get_local_equity = in_and_out.retrieve_local_equity()
                proposal_type = in_and_out.retrieve_proposal_type()
                sustainability_grant = in_and_out.retrieve_sustainability_grant()   # NEW
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
                    company_name, company_industry, get_total_revenue, total_employees,
                    get_local_equity, proposal_type, sustainability_grant,          # NEW
                    proposal_narrative, baseline_energy_expenditure, retrofit_cost,
                    reporting_advisory_fee
                )
                scheme_grant_records.append({
                    "Company Name": company_name,
                    "Company Industry": company_industry,
                    "Company Total Revenue": get_total_revenue,
                    "Total Employees": total_employees,
                    "Local Equity": get_local_equity,
                    "Proposal Type": proposal_type,
                    "Sustainability Grant": sustainability_grant,                   # NEW
                    "Proposal Narrative": proposal_narrative,
                    "Baseline Energy Expenditure": baseline_energy_expenditure,
                    "Estimated Retrofit Cost": retrofit_cost,
                    "Reporting Advisory Fee": reporting_advisory_fee
                })
                in_and_out.display_applied_grants(scheme_grant_records, key)
            

                # Automatically run the AI Manager and Logic Manager on the
                # record just collected, instead of requiring the user to
                # separately select options 5 and 6.
                ai_audit_data, result = run_audit(scheme_grant_records[-1])

                # Every completed audit is kept in the user's history, unless
                # the AI call itself failed (missing API key, timeout, unusable
                # answer) - that result is only a placeholder, not a real audit.
                if result is None:
                    pass  # a step raised; the error was already shown
                elif ai.ai_call_failed(ai_audit_data):
                    in_and_out.show_audit_not_saved_ai_failed()
                else:
                    saved_audit = dm.append_user_audit(current_user, scheme_grant_records[-1], ai_audit_data, result)
                    in_and_out.show_audit_saved_to_history(saved_audit)

                # end of case 1
                if in_and_out.confirm_save_to_json():
                    jsonfile_name = in_and_out.save_records(scheme_grant_records, jsonfile_name)
            case 2:  # Save to JSON
                jsonfile_name = in_and_out.save_records(scheme_grant_records, jsonfile_name)
            case 3:  # Pull from JSON
                scheme_grant_records, jsonfile_name = in_and_out.load_records(
                    scheme_grant_records, jsonfile_name
                )
            case 4: #Display current scheme grant records. Definitely I/O Manager's job. Can try editing and deleting records too. 
                        #Display part is IO job. Editing and deleting them is Data Manager's job
                        in_and_out.display_applied_grants(scheme_grant_records, key)
            case 5:  # Update
                index = in_and_out.select_record(scheme_grant_records, key, "update")
                if index is not None:
                    updated = in_and_out.retrieve_updated_record(scheme_grant_records[index - 1])
                    scheme_grant_records, jsonfile_name, status = dm.update_record_by_index(
                        scheme_grant_records, index, updated, jsonfile_name
                    )
                    in_and_out.display_edit_result(status, updated.get("Company Name", "Unknown"))

            case 6:  # Delete
                index = in_and_out.select_record(scheme_grant_records, key, "delete")
                if index is not None:
                    name = scheme_grant_records[index - 1].get("Company Name", "Unknown")
                    if in_and_out.confirm_delete(name):
                        scheme_grant_records, jsonfile_name, status = dm.delete_record_by_index(
                            scheme_grant_records, index, jsonfile_name
                        )
                        in_and_out.display_edit_result(status, name)
            case 7: #AI Processor
                if len(scheme_grant_records) == 0:
                    in_and_out.display_no_records_message() 
                else:
                    narrative = in_and_out.flat_record(scheme_grant_records[-1]).get("Proposal Narrative", "")
                    ok, new_audit = attempt(ai.get_ai_response, narrative)
                    if ok:
                        ai_audit_data = new_audit
                        in_and_out.display_ai_audit(ai_audit_data)
            case 8: # For the Logic Manager
                if len(scheme_grant_records) == 0:
                    in_and_out.display_no_records_message()
                elif not ai_audit_data:
                    in_and_out.display_no_ai_audit()
                else:
                    user_profile = in_and_out.convert_record_to_profile(scheme_grant_records[-1])
                    ok, result = attempt(logic.evaluate_grant_application, user_profile, ai_audit_data)
                    if ok:
                        in_and_out.display_grant_decision(result)
            case in_and_out.MENU_AUDIT_HISTORY: # 9: Past audits of the logged-in user
                audit_history_flow(current_user)
            case in_and_out.MENU_LOGOUT: # 10: Back to the login screen
                in_and_out.show_logged_out(current_user)
                dm.set_active_user(None)
            case _:
                in_and_out.show_wrong_option_error()