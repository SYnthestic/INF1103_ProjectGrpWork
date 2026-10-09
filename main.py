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


# Code
in_and_out.show_welcome_sequence()
# Test the fixed engine
continue_button()
scheme_grant_records = []
ai_audit_data = {}
jsonfile_name = ""

in_and_out.show_welcome_banner()

key = None
while key != 0:
    key = in_and_out.get_menu_choice()

    match key:
        case 0:
            in_and_out.show_goodbye()
        case 1: # Start checks
            company_name = in_and_out.retrieve_company_name()
            company_industry = in_and_out.retrieve_company_industry()
            get_total_revenue = in_and_out.retrieve_total_revenue()
            total_employees = in_and_out.retrieve_total_employees()
            get_local_equity = in_and_out.retrieve_local_equity()
            proposal_type = in_and_out.retrieve_proposal_type()
            proposal_narrative = in_and_out.retrieve_proposal_narrative()

            # Only ask for the cost fields relevant to the declared
            # proposal type, rather than asking every applicant for
            # both an energy/retrofit budget and a reporting fee.
            if proposal_type == "Equipment / Energy Upgrade":
                baseline_energy_expensiture = in_and_out.retrieve_baseline_energy_expenditure()
                retrofit_cost = in_and_out.retrieve_estimated_retrofit_cost()
                reporting_advisory_fee = 0.0
            else:
                baseline_energy_expensiture = 0.0
                retrofit_cost = 0.0
                reporting_advisory_fee = in_and_out.retrieve_reporting_advisory_fee()

            in_and_out.display_company_profile(company_name, company_industry, get_total_revenue, total_employees, get_local_equity, proposal_type, proposal_narrative, baseline_energy_expensiture, retrofit_cost, reporting_advisory_fee)
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
            in_and_out.display_applied_grants(scheme_grant_records, key)
            

            # Automatically run the AI Manager and Logic Manager on the
            # record just collected, instead of requiring the user to
            # separately select options 5 and 6.
            ai_audit_data = ai.get_ai_response(proposal_narrative)
            in_and_out.display_ai_audit(ai_audit_data)

            user_profile = in_and_out.convert_record_to_profile(scheme_grant_records[-1])
            result = logic.evaluate_grant_application(user_profile, ai_audit_data)
            in_and_out.display_grant_decision(result)

            if in_and_out.confirm_save_to_json():
                existing_records, jsonfile_name = dm.check_for_preexisting_save_file(jsonfile_name)
                scheme_grant_records = existing_records + scheme_grant_records
                jsonfile_name = dm.save_data_to_json(scheme_grant_records, jsonfile_name)
                in_and_out.print_jsonfilename(jsonfile_name)
                in_and_out.print_save_disk_block_deep_blue()
        case 2: #Save to JSON
            existing_records, jsonfile_name = dm.check_for_preexisting_save_file(jsonfile_name)
            scheme_grant_records = existing_records + scheme_grant_records
            jsonfile_name = dm.save_data_to_json(scheme_grant_records, jsonfile_name)
            in_and_out.print_jsonfilename(jsonfile_name)
            in_and_out.print_save_disk_block_deep_blue()
        case 3: #Pull from JSON
            if dm.check_overwrite(scheme_grant_records, jsonfile_name):
                scheme_grant_records, jsonfile_name = dm.load_data_from_json(jsonfile_name)

        case 4: 
            # Display part is IO job. Editing and deleting them is Data Manager's job
            in_and_out.display_applied_grants(scheme_grant_records, key)
            
            if len(scheme_grant_records) > 0:
                print("\n[1] Edit a record")
                print("[2] Delete a record")
                print("[0] Return to main menu")
                
                sub_choice = in_and_out.key_verifier(input("➔ "))
                
                if sub_choice == 1:
                    index = in_and_out.retrieve_record_index_to_delete(len(scheme_grant_records))
                    if index != 0:
                        current_record = scheme_grant_records[index - 1]
                        updated_record = in_and_out.retrieve_updated_record(current_record)
                        
                        # Removed the data_manager. prefix here
                        scheme_grant_records, jsonfile_name = in_and_out.update_record_by_index(
                            scheme_grant_records, index, updated_record, jsonfile_name
                        )
                elif sub_choice == 2:
                    index = in_and_out.retrieve_record_index_to_delete(len(scheme_grant_records))
                    if index != 0:
                        # Removed the data_manager. prefix here
                        scheme_grant_records, jsonfile_name = in_and_out.delete_record_by_index(
                            scheme_grant_records, index, jsonfile_name
                        )