from sme_interface_stores import sme_interface_gui as gui
import random
import sys
import os
import time

print("Welcome to SME Sustainability Grant Eligibility & Scope Compliance Auditor!")
print("This tool will help you determine if your company is eligible for the SME Sustainability Grant and assess your compliance with the scope of the grant.")
print()
print("Please provide the following information about your company to proceed with the assessment. Thankyou!")
print()

# Shows welcome sequence with ASCII art and sustainability banner
def show_welcome_sequence():
    print(gui.hello())
    print(gui.woman_says_hi())
    print(gui.sustainability_banner())
    print(gui.woman_says_hi())

# Verifies that the input is a valid integer key for the menu options.
def key_verifier(key):
    key = key.strip()

    if not key:
        print("Empty Response!")
        return None
    if not (key.isascii() and key.isdigit()):
        print("Error! Please enter a number.")
        return None

    return int(key)

def get_menu_choice():
    key = None
    while key is None:
        print(gui.boxed_menu())
        key = key_verifier(input("➔   "))
    return key


def display_company_profile(company_name, company_industry, total_revenue, total_employees, local_equity, proposal_type, baseline_energy_expenditure, estimated_retrofit_cost, reporting_advisory_fee):
    print(f"Company Name: {company_name}")
    print(f"Company Industry: {company_industry}")
    print(f"Company Total Revenue: {total_revenue}")
    print(f"Total Employees: {total_employees}")
    print(f"Local Equity: {local_equity}")
    print(f"Proposal Type: {proposal_type}")
    print(f"Baseline Energy Expenditure: {baseline_energy_expenditure}")
    print(f"Estimated Retrofit Cost: {estimated_retrofit_cost}")
    print(f"Reporting Advisory Fee: {reporting_advisory_fee}")

# input of Company's name
def retrieve_company_name():
    while True:
        company_name = input("Enter your Company's Name: ")
        if company_name.strip() == "":
            print("Company Name cannot be empty. Please try again.")
        else:
            return company_name

# input of Company's industry
def retrieve_company_industry():
    valid_industries = ["Logistics", "Manufacturing", "Retail", "Food & Beverage", "Healthcare", "Information Technology", "Construction", "Education", "Finance", "Hospitality", "Aerospace", "Others"]

    while True:
        company_industry = input(f"Enter your Company's Industry Sector (choose from {', '.join(valid_industries)}): ").strip().title()

        if company_industry.strip() == "":
            print("Company Industry Sector cannot be empty. Please try again.")
        elif company_industry not in valid_industries:
            print("Invalid. Please select a valid Industry Sector.")
        elif company_industry == "Others":
            return get_valid_other_industry()
        else:
            return company_industry

def get_valid_other_industry():
    while True:
        other_industry = input("Please specify your Company's Industry Sector: ").strip().title()
        if other_industry == "":
            print("Industry Sector cannot be empty. Please try again.")
        elif not other_industry.replace(" ", "").isalpha():
            print("Invalid. Please provide a valid Industry Sector containing only alphabetic characters.")
        else:
            return other_industry

# input of Company's Total Revenue
def retrieve_total_revenue():
    while True:
        try:
            total_revenue = float(input("Enter your Company's Total Revenue (in SGD): "))
            if total_revenue < 0:
                print("Total Revenue cannot be negative. Please try again.")
            elif total_revenue == 0:
                print("Total Revenue cannot be zero. Please try again.")
            else:
                return total_revenue
        except ValueError:
            print("Invalid input. Please enter a numeric value for total revenue.")

# input of Company's Total Number of Employees
def retrieve_total_employees():
    while True:
        try:
            total_employees = int(input("Enter your Company's Total Number of Employees: "))
            if total_employees < 0:
                print("Total Number of Employees cannot be negative. Please try again.")
            elif total_employees == 0:
                print("Total Number of Employees cannot be zero. Please try again.")
            else:
                return total_employees
        except ValueError:
            print("Invalid input. Please enter a numeric value for total number of employees.")

# input of Company's Local Equity
def retrieve_local_equity():
    while True:
        raw_value = input("Enter equity % owned by Singapore Citizens/PRs: ").strip()
        if raw_value == "":
            print("Equity % cannot be empty. Please try again.")
            continue
        try:
            local_equity = float(raw_value)
            if local_equity <= 0 or local_equity > 100:
                print("Equity % must be a value between 0 and 100. Please try again.")
                continue
            else:
                return local_equity
        except ValueError:
            print("Invalid input. Please enter a numeric value for your local equity.")

# NEW: applicant self-declares which kind of proposal this is, so we
# only collect the cost fields that are actually relevant, and so
# ai_manager.py gets a strong prior instead of guessing purely from
# free-text narrative.
def retrieve_proposal_type():
    valid_types = {
        "1": "Equipment / Energy Upgrade",
        "2": "ESG Reporting / Advisory",
    }

    while True:
        choice = input('''What type of proposal is this?\n
                1. Equipment / Energy Upgrade (e.g. fleet electrification, HVAC retrofit, lighting)\n
                2. ESG Reporting / Advisory (e.g. inaugural sustainability report, external assurance)\n
                    Enter 1 or 2: ''').strip()

        if choice in valid_types:
            return valid_types[choice]
        else:
            print("Invalid choice. Please enter 1 or 2.")

# Input of Baseline Annual Energy Expenditure
def retrieve_baseline_energy_expenditure():
    while True:
        raw_value = input("Enter baseline annual energy expenditure (in SGD): ").strip()
        if raw_value == "":
            print("Baseline annual energy expenditure cannot be empty. Please try again.")
            continue
        try:
            baseline_energy_expenditure = float(raw_value)
            if baseline_energy_expenditure < 0:
                print("Baseline annual energy expenditure cannot be negative. Please try again.")
                continue
            else:
                return baseline_energy_expenditure
        except ValueError:
            print("Invalid input. Please enter a numeric value for baseline annual energy expenditure.")

# Input of Estimated Retrofit Cost
def retrieve_estimated_retrofit_cost():
    while True:
        raw_value = input("Enter estimated retrofit cost (in SGD): ").strip()
        if raw_value == "":
            print("Estimated retrofit cost cannot be empty. Please try again.")
            continue
        try:
            estimated_retrofit_cost = float(raw_value)
            if estimated_retrofit_cost < 0:
                print("Estimated retrofit cost cannot be negative. Please try again.")
                continue
            else:
                return estimated_retrofit_cost
        except ValueError:
            print("Invalid input. Please enter a numeric value for estimated retrofit cost.")

# NEW: free-text description of the proposed upgrade. This is the raw
# narrative ai_manager.py needs in order to classify GHG scope, detect
# exclusion keywords, and estimate abatement — currently nothing in
# main.py or io_manager.py collects this at all.
def retrieve_proposal_narrative():
    print("Describe your proposed sustainability/energy upgrade in your own words.")
    print("(e.g. what equipment is being replaced, the fuel/energy source involved,")
    print(" and whether any components are second-hand, refurbished, or modified.)")
    while True:
        narrative = input("Proposal Description: ").strip()
        if narrative == "":
            print("Proposal description cannot be empty. Please try again.")
        else:
            return narrative

# Input of Reporting/Advisory Fee (only collected for ESG Reporting / Advisory proposals)
def retrieve_reporting_advisory_fee():
    while True:
        raw_value = input("Enter estimated external ESG reporting/advisory fee (in SGD): ").strip()
        if raw_value == "":
            print("Reporting/advisory fee cannot be empty. Please try again.")
            continue
        try:
            reporting_advisory_fee = float(raw_value)
            if reporting_advisory_fee < 0:
                print("Reporting/advisory fee cannot be negative. Please try again.")
                continue
            else:
                return reporting_advisory_fee
        except ValueError:
            print("Invalid input. Please enter a numeric value for the reporting/advisory fee.")

# For displaying list of grants already applied for by the company
def display_applied_grants(scheme_grant_records, key):
    red = "\033[91m"
    reset = "\033[0m"
    if len(scheme_grant_records) == 0:
        print(f"\n {red}⚠️  SYSTEM NOTICE: You do not have any grants applied.{reset}\n")
        # Now this will execute perfectly without a NameError!
        gui.print_return_keycap()
        return
    elif key == 1:
        print("Scheme Grant Records:")
        for i, grant in enumerate(scheme_grant_records, start=1):
            print(f'''{i}. {grant['Company Name']} - {grant['Company Industry']} | Total Revenue: {grant['Company Total Revenue']} | Total Employees: {grant['Total Employees']} | Local Equity: {grant['Local Equity']} | Proposal Type: {grant.get('Proposal Type', 'N/A')} | Baseline Energy Expenditure: {grant['Baseline Energy Expenditure']} | Estimated Retrofit Cost: {grant['Estimated Retrofit Cost']} | Reporting Advisory Fee: {grant.get('Reporting Advisory Fee', 0.0)}''')
        print(type(scheme_grant_records))
        gui.ai_button_art()
    else:
        print("List of Grants Already Applied For:")
        for i, grant in enumerate(scheme_grant_records, start=1):
            print(f'''{i}. {grant['Company Name']} - {grant['Company Industry']} | Total Revenue: {grant['Company Total Revenue']} | Total Employees: {grant['Total Employees']} | Local Equity: {grant['Local Equity']} | Proposal Type: {grant.get('Proposal Type', 'N/A')} | Baseline Energy Expenditure: {grant['Baseline Energy Expenditure']} | Estimated Retrofit Cost: {grant['Estimated Retrofit Cost']} | Reporting Advisory Fee: {grant.get('Reporting Advisory Fee', 0.0)}''')
        gui.print_return_keycap()
    return scheme_grant_records

# Bridges main.py's case-1 record format (capitalised, display-oriented
# keys, built one company at a time into scheme_grant_records) onto the
# snake_case keys logic_manager.py's evaluate_grant_application()
# actually reads. main.py's case 1 now stores Proposal Type and
# Reporting Advisory Fee directly on the record, so no extra
# parameters are needed here.
def convert_record_to_profile(record):
    return {
        "company_name": record.get("Company Name", ""),
        "company_industry": record.get("Company Industry", ""),
        "annual_revenue_sgd": record.get("Company Total Revenue", 0.0),
        "group_employment_size": record.get("Total Employees", 0),
        "local_shareholding_pct": record.get("Local Equity", 0.0),
        "proposal_type": record.get("Proposal Type", "Equipment / Energy Upgrade"),
        "baseline_annual_energy_expenditure_sgd": record.get("Baseline Energy Expenditure", 0.0),
        "estimated_retrofit_cost_sgd": record.get("Estimated Retrofit Cost", 0.0),
        "reporting_advisory_fee_sgd": record.get("Reporting Advisory Fee", 0.0),
    }


# Y/N confirmation for whether to save the just-processed record to
# JSON, used right after the automated AI + Logic audit in main.py.
def confirm_save_to_json():
    while True:
        choice = input("Save this record to JSON now? (y/n): ").strip().lower()
        if choice == "y":
            return True
        elif choice == "n":
            return False
        else:
            print("Invalid input. Please enter 'y' or 'n'.")

# Prints the JSON filename to the console after saving, so main.py doesn't have to know the details of how io_manager.py handles the display.
def print_jsonfilename(jsonfile_name):
    print(f"Data successfully saved to {jsonfile_name}.")

# Just an icon to let you know the save was successful, without having to print the full path every time.
def print_save_disk_block_deep_blue():
    print(gui.save_disk_block_deep_blue())

# Renders the AI Manager's structured output for the CLI. All console
# print statements in the codebase belong in io_manager.py per the
# architecture, so ai_manager.py and logic_manager.py never print
# directly — they just return data for this layer to display.
def display_ai_audit(ai_audit):
    print()
    print("AI Audit Result:")
    for key, value in ai_audit.items():
        print(f"  {key}: {value}")

# Runs whenever AI Manager is using the get_ai_response() function. It gives one bar for every second passed
def run_ai_analysis_bar(stop_event, timeout_seconds=60):
    """
    Animates the progress bar. Stops instantly if stop_event is flagged 
    or when it hits the maximum timeout.
    """
    cyan = "\033[96m"
    reset = "\033[0m"
    
    print("\nAnalysing your proposal with the AI Manager, please wait...\n")
    sys.stdout.write("\033[?25l")  # Hide text cursor
    sys.stdout.flush()
    
    try:
        # Loop for the maximum allowed duration
        for i in range(1, timeout_seconds + 1):
            # Check if the API background thread has finished and flagged us to stop
            if stop_event.is_set():
                break
                
            percent = int((i / timeout_seconds) * 100)
            progress_bar = f"\r   Time Taken: [{cyan}{'█' * i}{' ' * (timeout_seconds - i)}{reset}] {percent}% ({i}/{timeout_seconds}s)"
            
            sys.stdout.write(progress_bar)
            sys.stdout.flush()
            time.sleep(1)
    finally:
        # Restore terminal text cursor
        sys.stdout.write("\033[?25h\n\n")
        sys.stdout.flush()


# Renders the Logic Manager's decision for the CLI.
def display_grant_decision(result):
    print()
    print("=" * 60)
    print("GRANT ELIGIBILITY DECISION")
    print("=" * 60)
    print(f"SME Eligible     : {'YES' if result['is_sme'] else 'NO'}")
    print(f"Decision Status  : {result['decision_status']}")
    print(f"Audit Passed     : {result['audit_passed']}")
    print(f"Approved Subsidy : SGD {result['approved_subsidy_sgd']:,.2f}")

    if result["matched_schemes"]:
        print()
        print("Matched Schemes:")
        for scheme in result["matched_schemes"]:
            print(f"  - {scheme}")

    if result["reasons"]:
        print()
        print("Reasons:")
        for reason in result["reasons"]:
            print(f"  - {reason}")

    if result["recommendations"]:
        print()
        print("Recommendations:")
        for rec in result["recommendations"]:
            print(f"  - {rec}")

    print("=" * 60)

# Coordinator that collects every input and maps it onto the exact dict
# keys logic_manager.py's evaluate_grant_application() expects.
# Cost fields are now collected conditionally based on proposal_type,
# so applicants aren't asked for costs that don't apply to their case.
def build_user_profile():
    company_name = retrieve_company_name()
    company_industry = retrieve_company_industry()
    total_revenue = retrieve_total_revenue()
    total_employees = retrieve_total_employees()
    local_equity = retrieve_local_equity()
    proposal_type = retrieve_proposal_type()

    if proposal_type == "Equipment / Energy Upgrade":
        baseline_energy_expenditure = retrieve_baseline_energy_expenditure()
        estimated_retrofit_cost = retrieve_estimated_retrofit_cost()
        reporting_advisory_fee = 0.0
    else:
        baseline_energy_expenditure = 0.0
        estimated_retrofit_cost = 0.0
        reporting_advisory_fee = retrieve_reporting_advisory_fee()

    user_profile = {
        "company_name": company_name,
        "company_industry": company_industry,
        "annual_revenue_sgd": total_revenue,
        "group_employment_size": total_employees,
        "local_shareholding_pct": local_equity,
        "proposal_type": proposal_type,
        "baseline_annual_energy_expenditure_sgd": baseline_energy_expenditure,
        "estimated_retrofit_cost_sgd": estimated_retrofit_cost,
        "reporting_advisory_fee_sgd": reporting_advisory_fee,
    }

    return user_profile

def display_no_records_message():
    print("No records yet. Please select option 1 first.")
    gui.print_return_keycap()

def display_no_ai_audit():
    print("No AI audit yet. Please run option 5 first.")
    gui.print_return_keycap()

# ASCII related
# io_manager.py
def show_wrong_option_error():
    print(gui.wrong_sign_red())
    gui.print_return_keycap()

# 
def show_goodbye():
    print(gui.goodbye_art())


if __name__ == "__main__":
    user_profile = build_user_profile()
    print()
    print("Profile collected:")
    for key, value in user_profile.items():
        print(f"  {key}: {value}")