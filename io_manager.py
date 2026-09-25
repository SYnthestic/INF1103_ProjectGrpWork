print("Welcome to SME Sustainability Grant Eligibility & Scope Compliance Auditor!")
print("This tool will help you determine if your company is eligible for the SME Sustainability Grant and assess your compliance with the scope of the grant.")
print()
print("Please provide the following information about your company to proceed with the assessment. Thankyou!")
print()

# input of Company's name
def retrieve_company_name():
    while True:
        company_name = input("Enter your Company's Name: ")
        if company_name.strip() == "":
            print("Company Name cannot be empty. Please try again.")
        else:
            return company_name

if __name__ == "__main__":
    company_name = retrieve_company_name()
    print(f"Company's Name entered: {company_name}")

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

if __name__ == "__main__":
    company_industry = retrieve_company_industry()
    print(f"Company's Industry Sector entered: {company_industry}")

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

if __name__ == "__main__":
    total_revenue = retrieve_total_revenue()
    print(f"Company's Total Revenue entered: SGD {total_revenue:,.2f}")

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

if __name__ == "__main__":
    total_employees = retrieve_total_employees()
    print(f"Company's Total Number of Employees entered: {total_employees}")

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

if __name__ == "__main__":
    local_equity = retrieve_local_equity()
    print(f"Local Equity entered: {local_equity}%")

# Input of Baseline Annual Energy Expenditure
def retrieve_baseline_energy_expenditure():
    while True:
            raw_value = input("Enter baseline annual energy expenditure (in SGD): ").strip()
            if raw_value == "":
                print("Baseline annual energy expenditure cannot be empty. Please try again.")
                continue
            try:
                baseline_energy_expenditure = float(raw_value)
                if baseline_energy_expenditure <= 0:
                    print("Baseline annual energy expenditure cannot be zero or negative. Please try again.")
                    continue
                else:
                    return baseline_energy_expenditure
            except ValueError:
                print("Invalid input. Please enter a numeric value for baseline annual energy expenditure.")

if __name__ == "__main__":
    baseline_energy_expenditure = retrieve_baseline_energy_expenditure()
    print(f"Baseline Annual Energy Expenditure entered: SGD {baseline_energy_expenditure:,.2f}")

# Input of Estimated Retrofit Cost
def retrieve_estimated_retrofit_cost():
    while True:
            raw_value = input("Enter estimated retrofit cost (in SGD): ").strip()
            if raw_value == "":
                print("Estimated retrofit cost cannot be empty. Please try again.")
                continue
            try:
                estimated_retrofit_cost = float(raw_value)
                if estimated_retrofit_cost <= 0:
                    print("Estimated retrofit cost cannot be zero or negative. Please try again.")
                    continue
                else:
                    return estimated_retrofit_cost
            except ValueError:
                print("Invalid input. Please enter a numeric value for estimated retrofit cost.")

if __name__ == "__main__":
    estimated_retrofit_cost = retrieve_estimated_retrofit_cost()
    print(f"Estimated Retrofit Cost entered: SGD {estimated_retrofit_cost:,.2f}")

# Sustainability Grant that Company's want to apply
def retrieve_sustainability_grant():
    valid_grants = ['1. Energy Efficiency Grant (EEG) -Base Tier', '2. Energy Efficiency Grant (EEG) -Advanced Tier', '3. Enterprise Development Grant (EDG)', '4. Sustainability Reporting Programme (SRP)', '5. Others']
    while True:
        print('\nWhich Sustainability Grant would your company like to apply for?')
        for grant in valid_grants:
            print(grant)

        grant_choice = input(f"Enter the number corresponding to your choice (1-5): ").strip()
        
        if grant_choice not in ['1', '2', '3', '4', '5']:
            print("Invalid choice. Please select a valid option (1-5).")
            continue

        if grant_choice == "":
            print("Sustainability Grant choice cannot be empty. Please select a valid option from 1 to 5.")
            continue

        if grant_choice == '5':
            while True:
                other_grant = input("Please specify the Sustainability Grant that is not stated in the options: ").strip()
                if other_grant == "":
                    print("Sustainability Grant cannot be empty. Please provide a valid grant name.")
                elif not other_grant.replace(" ", "").isalpha():
                    print("Invalid input. Please enter a valid grant name.")
                else:
                    return other_grant
        
        else:
                selected_grant = valid_grants[int(grant_choice) - 1]
                return selected_grant

if __name__ == "__main__":
    sustainability_grant = retrieve_sustainability_grant()
    print(f"Sustainability Grant selected: {sustainability_grant}")


#For displaying list of grants already applied for by the company
def display_applied_grants(scheme_grant_records):
    print("List of Grants Already Applied For:")
    for i, grant in enumerate(scheme_grant_records, start=1):
        print(f'''{i}. {grant['Company Name']} - {grant['Company Industry']} | Total Revenue: {grant['Company Total Revenue']} | Total Employees: {grant['Total Employees']} | Local Equity: {grant['Local Equity']} | Baseline Energy Expenditure: {grant['Baseline Energy Expenditure']} | Estimated Retrofit Cost: {grant['Estimated Retrofit Cost']}''')
    return scheme_grant_records