print("Welcome to SME Green Grant Eligibility & Scope Compliance Auditor!")
print("This tool will help you determine if your company is eligible for the SME Green Grant and assess your compliance with the scope of the grant.")
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
        elif not other_industry.isalpha():
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