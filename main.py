import sys
import time
import os
import json
from openai import OpenAI
from art import *

# Load OPENROUTER_API_KEY from a local .env file when running outside
# Docker. Inside Docker the variable is injected via --env-file instead.
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

from io_manager import (
    key_verifier,
    display_company_profile,
    display_applied_grants,
    retrieve_baseline_energy_expenditure,
    retrieve_company_industry,
    retrieve_company_name,
    retrieve_estimated_retrofit_cost,
    retrieve_local_equity,
    retrieve_total_employees,
    retrieve_total_revenue,
    retrieve_proposal_type,
    retrieve_proposal_narrative,
    retrieve_reporting_advisory_fee,
    convert_record_to_profile,
    confirm_save_to_json,
    display_ai_audit,
    display_grant_decision,
    display_no_records_message,
    display_no_ai_audit,
)
from data_manager import check_for_preexisting_save_file, load_data_from_json, save_data_to_json, check_overwrite
from ai_manager import get_ai_response
from logic_manager import evaluate_grant_application
from sme_interface_stores.sme_interface_gui import *

# Code
print_hello()
woman_says_hi()
print_sustainability_banner()
woman_says_hi()
# Test the fixed engine
press_enter_to_continue()
scheme_grant_records = []
ai_audit_data = {}
jsonfile_name = ""
key = 1

key = None
while key != 0:
    key = None
    while key is None:
        print_boxed_menu()
        key = key_verifier(input("➔ "))

    match key:
        case 0:
            print_goodbye()
        case 1: # Start checks
            company_name = retrieve_company_name()
            company_industry = retrieve_company_industry()
            get_total_revenue = retrieve_total_revenue()
            total_employees = retrieve_total_employees()
            get_local_equity = retrieve_local_equity()
            proposal_type = retrieve_proposal_type()
            proposal_narrative = retrieve_proposal_narrative()

            # Only ask for the cost fields relevant to the declared
            # proposal type, rather than asking every applicant for
            # both an energy/retrofit budget and a reporting fee.
            if proposal_type == "Equipment / Energy Upgrade":
                baseline_energy_expensiture = retrieve_baseline_energy_expenditure()
                retrofit_cost = retrieve_estimated_retrofit_cost()
                reporting_advisory_fee = 0.0
            else:
                baseline_energy_expensiture = 0.0
                retrofit_cost = 0.0
                reporting_advisory_fee = retrieve_reporting_advisory_fee()

            display_company_profile(company_name, company_industry, get_total_revenue, total_employees, get_local_equity, proposal_type, baseline_energy_expensiture, retrofit_cost, reporting_advisory_fee)
            scheme_grant_records.append({
                "Company Name": company_name,
                "Company Industry": company_industry,
                "Company Total Revenue": get_total_revenue,
                "Total Employees": total_employees,
                "Local Equity": get_local_equity,
                "Proposal Type": proposal_type,
                "Proposal Narrative": proposal_narrative,
                "Baseline Energy Expenditure": baseline_energy_expensiture,
                "Estimated Retrofit Cost": retrofit_cost,
                "Reporting Advisory Fee": reporting_advisory_fee
            })
            print("Scheme Grant Records:", scheme_grant_records)
            print(type(scheme_grant_records))

            # Automatically run the AI Manager and Logic Manager on the
            # record just collected, instead of requiring the user to
            # separately select options 5 and 6.
            ai_audit_data = get_ai_response(proposal_narrative)
            display_ai_audit(ai_audit_data)

            user_profile = convert_record_to_profile(scheme_grant_records[-1])
            result = evaluate_grant_application(user_profile, ai_audit_data)
            display_grant_decision(result)

            if confirm_save_to_json():
                existing_records, jsonfile_name = check_for_preexisting_save_file(jsonfile_name)
                scheme_grant_records = existing_records + scheme_grant_records
                jsonfile_name = save_data_to_json(scheme_grant_records, jsonfile_name)
                print(jsonfile_name)
                print_save_disk_block_deep_blue()
        case 2: #Save to JSON
            existing_records, jsonfile_name = check_for_preexisting_save_file(jsonfile_name)
            scheme_grant_records = existing_records + scheme_grant_records
            jsonfile_name = save_data_to_json(scheme_grant_records, jsonfile_name)
            print(jsonfile_name)
            print_save_disk_block_deep_blue()
        case 3: #Pull from JSON
            if check_overwrite(scheme_grant_records, jsonfile_name):
                scheme_grant_records, jsonfile_name = load_data_from_json(jsonfile_name)
        case 4: #Display current scheme grant records. Definitely I/O Manager's job. Can try editing and deleting records too. 
            #Display part is IO jpb. Editing and deleting them is Data Manager's job
            display_applied_grants(scheme_grant_records)
        case 5: #AI Processor
            if len(scheme_grant_records) == 0:
                display_no_records_message()
                print_return_keycap()
            else:
                current_record = scheme_grant_records[-1]
                narrative = current_record.get("Proposal Narrative", "")
                ai_audit_data = get_ai_response(narrative)
                display_ai_audit(ai_audit_data)
        case 6: # For the Logic Manager
            if len(scheme_grant_records) == 0:
                display_no_records_message()
                print_return_keycap()
            elif not ai_audit_data:
                display_no_ai_audit()
                print_return_keycap()
            else:
                current_record = scheme_grant_records[-1]
                user_profile = convert_record_to_profile(current_record)
                result = evaluate_grant_application(user_profile, ai_audit_data)
                display_grant_decision(result)
        case _:
            print_wrong_sign_red()
            print_return_keycap()