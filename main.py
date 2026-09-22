# Importations
import sys
import os
import json

from io_manager import retrieve_company_industry, retrieve_company_name, retrieve_total_revenue

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
            print(f"Company Name: {company_name}")
            print(f"Company Industry: {company_industry}")
            print(f"Company Total Revenue: {get_total_revenue}")
            scheme_grant_records.append({
                "Company Name": company_name,
                "Company Industry": company_industry,
                "Company Total Revenue": get_total_revenue
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
        case 6: # For the Logic Manager
            print("Function U/C")
        case _:
            print("Error! Unrecognised number option")