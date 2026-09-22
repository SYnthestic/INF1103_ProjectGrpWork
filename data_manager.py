import json


print("Welcome to SME Green Grant Eligibility & Scope Compliance Auditor!")
print("This tool will help you determine if your company is eligible for the SME Green Grant and assess your compliance with the scope of the grant.")
print()
print("This tool is designed to safeguard your data safely and securely. Thank you!")
print()

def check_for_preexisting_save_file(jsonfile_name):
    if jsonfile_name == '':
        try:
            with open(jsonfile_name, 'r') as file:
                data = json.load(file)
                print(f"Data successfully loaded from {jsonfile_name}.")
                return data
        except FileNotFoundError:
            print(f"No existing save file found with the name {jsonfile_name}. Starting fresh.")

def save_data_to_json(data, jsonfile_name):
    while jsonfile_name == '':
        jsonfile_name = input("Please provide a valid JSON file name to save the data: ")
        if jsonfile_name == '':
            jsonfile_name = input("Please provide a valid JSON file name to save the data: ")
        else:
            jsonfile_name = jsonfile_name + '.json'
    try:
        with open(jsonfile_name, 'w') as file:
            json.dump(data, file, indent=4)
            print(f"Data successfully saved to {jsonfile_name}.")
    except Exception as e:
        print(f"An error occurred while saving data to {jsonfile_name}: {e}")