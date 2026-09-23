import json
import os

print("Welcome to SME Green Grant Eligibility & Scope Compliance Auditor!")
print("This tool will help you determine if your company is eligible for the SME Green Grant and assess your compliance with the scope of the grant.")
print()
print("This tool is designed to safeguard your data safely and securely. Thank you!")
print()

#Saving Part
def check_for_preexisting_save_file(jsonfile_name):
    # Ensure filename ends with .json if provided
    if jsonfile_name and not jsonfile_name.endswith('.json'):
        jsonfile_name += '.json'

    # If the user didn't provide a name, treat it as starting completely fresh
    if not jsonfile_name:
        print("No filename provided. Starting fresh with a new list.")
        return [], ""

    # Check if the file actually exists on the computer
    if os.path.exists(jsonfile_name):
        while True:
            choicer = input(f"A save file named '{jsonfile_name}' already exists. Do you want to load/append data to this file or create a brand new one? (save/new): ").strip().lower()
            
            if choicer == 'save':
                try:
                    with open(jsonfile_name, 'r', encoding='utf-8') as file:
                        data = json.load(file)
                        # Ensure the loaded data is a list so we can append to it later
                        if not isinstance(data, list):
                            data = [data]
                        print(f"Data successfully loaded from {jsonfile_name}.")
                        return data, jsonfile_name
                except (json.JSONDecodeError, FileNotFoundError):
                    print(f"File {jsonfile_name} is corrupted or empty. Starting fresh with this filename.")
                    return [], jsonfile_name
                    
            elif choicer == 'new':
                print("Starting a brand new session. You will be prompted for a new filename when saving.")
                return [], ""  # Return empty data and clear filename so save_data_to_json prompts them
            else:
                print("Invalid input. Please enter 'save' or 'new'.")
    else:
        print(f"No existing save file found with the name '{jsonfile_name}'. Starting fresh.")
        return [], jsonfile_name

def save_data_to_json(data, jsonfile_name):
    # Keep asking until a valid, non-empty filename is provided
    while not jsonfile_name:
        jsonfile_name = input("Please provide a valid JSON file name to save the data: ").strip()
        if not jsonfile_name:
            print("Filename cannot be blank.")
            
    # Automatically add .json extension if it's missing
    # Check if jsonfile_name exists and is a string before checking the extension
    if jsonfile_name and not str(jsonfile_name).endswith('.json'):
        jsonfile_name = str(jsonfile_name) + '.json'


    try:
        with open(jsonfile_name, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
            print(f"Data successfully saved to {jsonfile_name}.")
            return jsonfile_name
    except Exception as e:
        print(f"An error occurred while saving data to {jsonfile_name}: {e}")
        return jsonfile_name


#Loading Part
def check_overwrite(data, jsonfile_name):

    # Nothing is currently loaded
    if data == [] and jsonfile_name == "":
        return True

    # Something is already loaded
    choice = input(
        "Data is already loaded. Do you want to overwrite it? (y/n): "
    ).strip().lower()

    if choice == "y":
        return True

    print("Returning to main menu.")
    return False

def load_data_from_json(jsonfile_name):
    # Keep asking until a valid, non-empty filename is provided
    while not jsonfile_name:
        jsonfile_name = input("Please provide a valid JSON file name to load the data from: ").strip()
        if not jsonfile_name:
            print("Filename cannot be blank.")
            
    # Automatically add .json extension if it's missing
    # Check if jsonfile_name exists and is a string before checking the extension
    if jsonfile_name and not str(jsonfile_name).endswith('.json'):
        jsonfile_name = str(jsonfile_name) + '.json'

    # Check whether the file exists
    if not os.path.isfile(jsonfile_name):
        print("This file does not exist.")
        return [], jsonfile_name


    try:
        with open(jsonfile_name, 'r', encoding='utf-8') as file:
            data = json.load(file)

        print(f"Data successfully loaded from {jsonfile_name}.")
        return data, jsonfile_name
    
    except Exception as e:
        print(f"An error occurred while loading data from {jsonfile_name}: {e}")
        return [], jsonfile_name