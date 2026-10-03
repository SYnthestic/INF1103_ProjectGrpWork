import json
import os
from datetime import datetime

# Invalid characters for filenames
INVALID_FILENAME_CHARS = '/\\:*?"<>|'

# Data save will be stored in JSON format. The following functions help manage the data files.
def normalise_filename(jsonfile_name):
    """Strips whitespace and makes sure the name ends with .json."""
    jsonfile_name = str(jsonfile_name).strip()
    if jsonfile_name and not jsonfile_name.endswith('.json'):
        jsonfile_name += '.json'
    return jsonfile_name

# Check if the filename is valid (no folders or special characters)
def is_valid_filename(jsonfile_name):
    """A bare filename only: no folders or special characters."""
    return not any(char in jsonfile_name for char in INVALID_FILENAME_CHARS)


# Audit Record management:
# Generate a unique ID for a new audit record
def generate_audit_id(records):
    if not records:
        return 1
    
    highest_id = 0

    for record in records:
        audit_id = record.get("audit_id", 0)

        if isinstance(audit_id, int) and audit_id > highest_id:
            highest_id = audit_id

    return highest_id + 1

# Create Audit record in JSON format
def create_audit_record(
    audit_id,
    user_profile,
    proposal,
    ai_audit,
    evaluation
):
    """Combine all assessment information into one audit record."""

    audit_record = {
        "audit_id": audit_id,
        "created_at": datetime.now().isoformat(),

        "company_profile": user_profile,

        "proposal": {
            "raw_narrative": proposal
        },

        "ai_audit": ai_audit,

        "evaluation": evaluation
    }

    return audit_record

# Add audit record to the current record list
def add_audit_record(records, audit_record):
    """Add a completed audit record to the current record list."""

    if not isinstance(records, list):
        records = []

    records.append(audit_record)

    return records

# End

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

# Save data to JSON and do filename validation
def save_data_to_json(data, jsonfile_name):
    # Keep asking until a valid, non-empty filename is provided
    while not jsonfile_name:
        jsonfile_name = input("Please provide a valid JSON file name to save the data: ").strip()

        if not jsonfile_name:
            print("Filename cannot be blank.")

    jsonfile_name = normalise_filename(jsonfile_name)

    if not is_valid_filename(jsonfile_name):
        print("Invalid filename. Please avoid special characters.")
        return None
    
    try:
        with open(jsonfile_name, 'w', encoding='utf-8') as file:
            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False
            )
        print(f"Data successfully saved to {jsonfile_name}.")
        return jsonfile_name
    
    except OSError as error:
        print(
            f"An error occurred while saving data "
            f"to {jsonfile_name}: {error}"
        )

        return None
            

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

# load data from JSON and do filename validation
def load_data_from_json(jsonfile_name):
    # Keep asking until a valid, non-empty filename is provided
    while not jsonfile_name:
        jsonfile_name = input("Please provide a valid JSON file name to load the data from: ").strip()
        if not jsonfile_name:
            print("Filename cannot be blank.")

    jsonfile_name = normalise_filename(jsonfile_name)

    if not is_valid_filename(jsonfile_name):
        print("Invalid filename. Please avoid special characters.")
        return [], jsonfile_name

    # Check whether the file exists
    if not os.path.isfile(jsonfile_name):
        print(f"The file '{jsonfile_name}' does not exist.")
        return [], jsonfile_name

    try:
        with open(
            jsonfile_name,
            'r',
            encoding='utf-8'
        ) as file:

            data = json.load(file)

        # Make sure the loaded data is a list
        if not isinstance(data, list):
            data = [data]

        print(
            f"Data successfully loaded from {jsonfile_name}."
        )

        return data, jsonfile_name

    except json.JSONDecodeError:
        print(
            f"The file '{jsonfile_name}' contains invalid JSON."
        )

        return [], jsonfile_name

    except OSError as error:
        print(
            f"An error occurred while loading "
            f"{jsonfile_name}: {error}"
        )

        return [], jsonfile_name
            