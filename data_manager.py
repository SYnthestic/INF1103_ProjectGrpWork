import json
import logging
import os
from datetime import datetime

print("Welcome to SME Green Grant Eligibility & Scope Compliance Auditor!")
print("This tool will help you determine if your company is eligible for the SME Green Grant and assess your compliance with the scope of the grant.")
print()
print("This tool is designed to safeguard your data safely and securely. Thank you!")
print()

# All save files live in a "data" folder next to this file, regardless of
# which directory the program is launched from. (In Docker this resolves
# to /app/data, which matches the -v "$(pwd)/data:/app/data" volume mount.)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))

INVALID_FILENAME_CHARS = '/\\:*?"<>|'

def normalise_filename(jsonfile_name):
    """Strips whitespace and makes sure the name ends with .json."""
    jsonfile_name = str(jsonfile_name).strip()
    if jsonfile_name and not jsonfile_name.endswith('.json'):
        jsonfile_name += '.json'
    return jsonfile_name


def is_valid_filename(jsonfile_name):
    """A bare filename only: no folders or special characters."""
    return not any(char in jsonfile_name for char in INVALID_FILENAME_CHARS)


def get_data_path(jsonfile_name):
    """Full path of a save file inside the data folder."""
    return os.path.join(DATA_DIR, jsonfile_name)


#Saving Part
def check_for_preexisting_save_file(jsonfile_name):
    jsonfile_name = normalise_filename(jsonfile_name) if jsonfile_name else ""

    # If the user didn't provide a name, treat it as starting completely fresh
    if not jsonfile_name:
        print("No filename provided. Starting fresh with a new list.")
        return [], ""

    filepath = get_data_path(jsonfile_name)

    # Check if the file actually exists on the computer
    if os.path.exists(filepath):
        while True:
            choicer = input(f"A save file named '{jsonfile_name}' already exists. Do you want to load/append data to this file or create a brand new one? (save/new): ").strip().lower()

            if choicer == 'save':
                try:
                    with open(filepath, 'w+', encoding='utf-8') as file:
                        data = json.load(file)
                        # Ensure the loaded data is a list so we can append to it later
                        if not isinstance(data, list):
                            data = [data]
                        print(f"Data successfully loaded from {os.path.abspath(filepath)}.")
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
    while True:
        # Keep asking until a valid, non-empty filename is provided
        while not jsonfile_name:
            jsonfile_name = input("Please provide a valid JSON file name to save the data: ").strip()
            if not jsonfile_name:
                print("Filename cannot be blank.")

        jsonfile_name = normalise_filename(jsonfile_name)

        # Reject folder separators and special characters up front
        if not is_valid_filename(jsonfile_name):
            print(f"'{jsonfile_name}' is not a valid file name. Please avoid these characters: {INVALID_FILENAME_CHARS}")
            jsonfile_name = ""
            continue

        filepath = get_data_path(jsonfile_name)

        try:
            # Create the data folder on first use
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as file:
                json.dump(data, file, indent=4, ensure_ascii=False)
                print(f"Data successfully saved to {os.path.abspath(filepath)}.")
                return jsonfile_name
        except (OSError, IOError) as e:
            print(f"An error occurred while saving data to {jsonfile_name}: {e}")
            jsonfile_name = ""


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
    while True:
        # Keep asking until a valid, non-empty filename is provided
        while not jsonfile_name:
            jsonfile_name = input("Please provide a valid JSON file name to load the data from: ").strip()
            if not jsonfile_name:
                print("Filename cannot be blank.")

        jsonfile_name = normalise_filename(jsonfile_name)

        if not is_valid_filename(jsonfile_name):
            print(f"'{jsonfile_name}' is not a valid file name. Please avoid these characters: {INVALID_FILENAME_CHARS}")
            jsonfile_name = ""
            continue

        break

    filepath = get_data_path(jsonfile_name)

    # Check whether the file exists
    if not os.path.isfile(filepath):
        print(f"This file does not exist. Save files are kept in: {DATA_DIR}")
        return [], jsonfile_name

    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            data = json.load(file)

        print(f"Data successfully loaded from {os.path.abspath(filepath)}.")
        return data, jsonfile_name

    except Exception as e:
        print(f"An error occurred while loading data from {jsonfile_name}: {e}")
        return [], jsonfile_name

def update_record_by_index(data, index, updated_record, jsonfile_name):
    list_index = index - 1
    data[list_index] = updated_record
    
    print("\nRecord successfully updated.")
    
    if jsonfile_name:
        from data_manager import save_data_to_json
        save_data_to_json(data, jsonfile_name)
        
    return data, jsonfile_name