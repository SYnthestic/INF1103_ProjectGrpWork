# Importations
import sys
import os
import json

from io_manager import retrieve_baseline_energy_expenditure, retrieve_company_industry, retrieve_company_name, retrieve_estimated_retrofit_cost, retrieve_local_equity, retrieve_total_employees, retrieve_total_revenue
# from data_manager import 
#  from ai_manager import
# from logic_manager import

# Code
print(
'''
****************************************************
*                                                  *
*                   Welcome to:                    *
*                                                  *
* ~  SME Green Sutainability Eligibility Scheme  ~ *
-------------------------------------------------- *
*                                                  *
*    For the purposes of determining eligibility   *
*  to the SME Green Grant and assessing compliance *
*  WARNING! THIS APP IS PRIMITIVE AND MAY NOT WORK *
*                                                  *
****************************************************
''')
input("Press enter to continue ")
scheme_grant_records = []
ai_manager_data = []
key = 1

while key!=0:
    keyverify = False
    while keyverify == False:
        key = input("Please select your choice (0,1,2,3,4,5,6)\n 0. Exit\n 1. Start\n 2. Save to JSON\n 3. Pull from JSON\n 4. Display Current Records\n 5. AI Processor\n 6. Logic Manager\n")
        if len(key) == 0:
            print("Empty Response!")
        elif key.isnumeric() == False:
            print("Error! Letters detected!!")
        elif key.isspace():
            print("Error! Space only answer not allowed")
        else:
            keyverify = True
            key = int(key)

    match key:
        case 0:
            print("Exiting the program.")
        case 1: # Start checks
            print("Function U/C")
            company_name = retrieve_company_name()
            company_industry = retrieve_company_industry()
            get_total_revenue = retrieve_total_revenue()
            total_employees = retrieve_total_employees()
            get_local_equity = retrieve_local_equity()
            baseline_energy_expensiture = retrieve_baseline_energy_expenditure()
            retrofit_cost = retrieve_estimated_retrofit_cost()
            print(f"Company Name: {company_name}")
            print(f"Company Industry: {company_industry}")
            print(f"Company Total Revenue: {get_total_revenue}")
            print(f"Total Employees: {total_employees}")
            print(f"Local Equity: {get_local_equity}")
            print(f"Baseline Energy Expenditure: {baseline_energy_expensiture}")
            print(f"Estimated Retrofit Cost: {retrofit_cost}")
            scheme_grant_records.append({
                "Company Name": company_name,
                "Company Industry": company_industry,
                "Company Total Revenue": get_total_revenue,
                "Total Employees": total_employees,
                "Local Equity": get_local_equity,
                "Baseline Energy Expenditure": baseline_energy_expensiture,
                "Estimated Retrofit Cost": retrofit_cost
            })
            print("Scheme Grant Records:", scheme_grant_records)
            print(type(scheme_grant_records))
        case 2: #Save to JSON
            print("Function U/C")
            print(type(scheme_grant_records))
        case 3: #Pull from JSON
            print("Function U/C")
            # scheme_grant_records = json.loads(scheme_grant_records)
        case 4: #Display current scheme grant records
            print("Function U/C")
        case 5: #AI Processor
            print("Function U/C")
            ai_manager_data = scheme_grant_records
        case 6: # For the Logic Manager
            print("Function U/C")
        case _:
            print("Error! Unrecognised number option")