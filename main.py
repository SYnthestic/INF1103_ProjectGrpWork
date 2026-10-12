import sys
import time
import os
import json
from openai import OpenAI

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
from sme_interface_stores.sme_interface_gui import *


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
    if logic.verify_password(password, stored_user):
        in_and_out.show_login_success(username)
        return username

    in_and_out.show_login_failed()
    return None


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
                ai_audit_data = ai.get_ai_response(proposal_narrative)
                in_and_out.display_ai_audit(ai_audit_data)

                user_profile = in_and_out.convert_record_to_profile(scheme_grant_records[-1])
                result = logic.evaluate_grant_application(user_profile, ai_audit_data)
                in_and_out.display_grant_decision(result)

                # Every completed audit is kept in the user's history.
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
            case 5: #Update. Tia, this is your target
                print("Update Function U/C")
            case 6: #Delete. Tia's target no.2
                print("Delete Function U/C")
            case 7: #AI Processor
                if len(scheme_grant_records) == 0:
                    in_and_out.display_no_records_message() 
                else:
                    current_record = scheme_grant_records[-1]
                    narrative = current_record.get("Proposal Narrative", "")
                    ai_audit_data = ai.get_ai_response(narrative)
                    in_and_out.display_ai_audit(ai_audit_data)
            case 8: # For the Logic Manager
                if len(scheme_grant_records) == 0:
                    in_and_out.display_no_records_message()
                elif not ai_audit_data:
                    in_and_out.display_no_ai_audit()
                else:
                    current_record = scheme_grant_records[-1]
                    user_profile = in_and_out.convert_record_to_profile(current_record)
                    result = logic.evaluate_grant_application(user_profile, ai_audit_data)
                    in_and_out.display_grant_decision(result)
            case in_and_out.MENU_LOGOUT: # 10: Back to the login screen
                in_and_out.show_logged_out(current_user)
            case _:
                in_and_out.show_wrong_option_error()