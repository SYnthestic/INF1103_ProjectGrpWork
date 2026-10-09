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


# Print calls from data manager
FILE_STATUS_MESSAGES = {
    "saved": "Data successfully saved to {name}.",
    "loaded": "Data successfully loaded from {name}.",
    "no_name": "No filename provided.",
    "invalid_name": "Invalid filename. Please avoid special characters.",
    "not_found": "The file '{name}' does not exist.",
    "invalid_json": "The file '{name}' is corrupted or contains invalid JSON. Starting fresh.",
    "invalid_format": "The file '{name}' is not a valid list of audit records. Starting fresh.",
    "io_error": "A file error occurred while accessing '{name}'.",
}


def display_file_status(status, jsonfile_name=""):
    message = FILE_STATUS_MESSAGES.get(status, "Unknown file status.")
    print(message.format(name=jsonfile_name))


def prompt_for_filename(action):
    """action is 'save' or 'load'."""
    while True:
        name = input(f"Please provide a valid JSON file name to {action} the data: ").strip()
        if name:
            return name
        print("Filename cannot be blank.")


def choose_save_or_new(jsonfile_name):
    """Returns 'save' (load/append to the existing file) or 'new'."""
    while True:
        choice = input(
            f"A save file named '{jsonfile_name}' already exists. "
            "Do you want to load/append data to this file or create a brand new one? (save/new): "
        ).strip().lower()
        if choice in ("save", "new"):
            return choice
        print("Invalid input. Please enter 'save' or 'new'.")


def confirm_overwrite_loaded_data():
    choice = input("Data is already loaded. Do you want to overwrite it? (y/n): ").strip().lower()
    if choice == "y":
        return True
    print("Returning to main menu.")
    return False