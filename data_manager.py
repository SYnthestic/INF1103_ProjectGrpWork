import json
import logging
import os
from datetime import datetime

# Stay silent unless someone configures logging (otherwise Python's default
# handler would write warnings straight to the terminal).
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Invalid characters for filenames
INVALID_FILENAME_CHARS = '/\\:*?"<>|'

# Where save files live. Override with the DATA_DIR environment variable
# (e.g. point it at a mounted volume when running in Docker).
DATA_DIR = os.environ.get("DATA_DIR", ".")

# File loaded automatically on startup.
DEFAULT_SAVE_FILE = "audit_records.json"

# Every saved audit record must contain these sections, each as a dict.
REQUIRED_RECORD_SECTIONS = ("company_profile", "proposal", "ai_audit", "evaluation")


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

def normalise_filename(jsonfile_name):
    """Strips whitespace and makes sure the name ends with .json
    (any capitalisation of the extension is accepted)."""
    jsonfile_name = str(jsonfile_name).strip()
    if jsonfile_name and not jsonfile_name.lower().endswith('.json'):
        jsonfile_name += '.json'
    return jsonfile_name


def is_valid_filename(jsonfile_name):
    """A bare filename only: no folders, control characters, or empty stem."""
    if any(char in jsonfile_name for char in INVALID_FILENAME_CHARS):
        return False
    if any(ord(char) < 32 for char in jsonfile_name):
        return False
    stem = jsonfile_name[:-len('.json')] if jsonfile_name.lower().endswith('.json') else jsonfile_name
    # Rejects ".json", "..json", " .json" and similar nameless files.
    return stem.strip(" .") != ""


def _full_path(jsonfile_name):
    return os.path.join(DATA_DIR, jsonfile_name)


# ---------------------------------------------------------------------------
# Record helpers
# ---------------------------------------------------------------------------

def is_valid_audit_record(record):
    """True if the record is a dict and every required section is a dict."""
    if not isinstance(record, dict):
        return False
    return all(isinstance(record.get(section), dict) for section in REQUIRED_RECORD_SECTIONS)


def _section(record, section_name):
    """Safe access to a record section: always returns a dict."""
    if not isinstance(record, dict):
        return {}
    section = record.get(section_name)
    return section if isinstance(section, dict) else {}


# ---------------------------------------------------------------------------
# Audit record management
# ---------------------------------------------------------------------------

def generate_audit_id(records):
    """Next unique integer ID for a new audit record."""
    if not isinstance(records, list) or not records:
        return 1

    highest_id = 0
    for record in records:
        audit_id = record.get("audit_id", 0) if isinstance(record, dict) else 0
        if isinstance(audit_id, int) and not isinstance(audit_id, bool) and audit_id > highest_id:
            highest_id = audit_id

    return highest_id + 1


def create_audit_record(audit_id, user_profile, proposal, ai_audit, evaluation):
    """Combine all assessment information into one audit record."""
    return {
        "audit_id": audit_id,
        "created_at": datetime.now().isoformat(),
        "company_profile": user_profile,
        "proposal": {
            "raw_narrative": proposal
        },
        "ai_audit": ai_audit,
        "evaluation": evaluation
    }


def add_audit_record(records, audit_record):
    """Add a completed audit record to the current record list."""
    if not isinstance(records, list):
        records = []
    records.append(audit_record)
    return records


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def inspect_save_file(jsonfile_name):
    """
    Checks a filename WITHOUT reading the file.

    Returns (clean_name, status) where status is one of:
        "no_name"       nothing was given          (clean_name is "")
        "invalid_name"  has illegal characters     (clean_name is "")
        "exists"        a save file is already there
        "not_found"     no such file yet           (clean_name is still usable)
    """
    name = normalise_filename(jsonfile_name)
    if not name:
        return "", "no_name"
    if not is_valid_filename(name):
        return "", "invalid_name"
    if os.path.isfile(_full_path(name)):
        return name, "exists"
    return name, "not_found"


def _backup_corrupt_file(path):
    """Moves a bad file aside so a later save cannot silently destroy it."""
    try:
        os.replace(path, path + ".corrupt")
    except OSError as err:
        logger.error("Could not back up corrupt file %s: %s", path, err)


def load_data_from_json(jsonfile_name):
    """
    Loads records from a JSON save file.

    Returns (data, clean_name, status). data is ALWAYS a list.
    status is one of:
        "loaded"          success
        "no_name"         nothing was given
        "invalid_name"    illegal characters in the name
        "not_found"       file does not exist
        "invalid_json"    file is corrupt/unreadable (set aside as .corrupt)
        "invalid_format"  valid JSON but not a list of audit records (set aside)
        "io_error"        the OS refused to read the file
    """
    name = normalise_filename(jsonfile_name)
    if not name:
        return [], "", "no_name"
    if not is_valid_filename(name):
        return [], "", "invalid_name"

    path = _full_path(name)
    if not os.path.isfile(path):
        return [], name, "not_found"

    try:
        with open(path, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except ValueError:  # JSONDecodeError and UnicodeDecodeError
        logger.error("%s contains invalid JSON.", path)
        _backup_corrupt_file(path)
        return [], name, "invalid_json"
    except (OSError, RecursionError) as err:
        logger.error("Could not read %s: %s", path, err)
        return [], name, "io_error"

    # A single record on its own is treated as a one-item list.
    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list) or not all(is_valid_audit_record(r) for r in data):
        logger.error("%s is not a list of audit records.", path)
        _backup_corrupt_file(path)
        return [], name, "invalid_format"

    return data, name, "loaded"


def is_data_loaded(data, jsonfile_name):
    """True if there is already data/filename in memory (io_manager should
    then ask the user before overwriting it)."""
    return not (data == [] and jsonfile_name == "")


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

def save_data_to_json(data, jsonfile_name):
    """
    Saves records to a JSON file.

    Writes to a temporary file first and then swaps it in, so a crash midway
    can never leave a half-written (corrupt) save file.

    Returns (saved_name_or_None, status) where status is one of:
        "saved", "no_name", "invalid_name", "io_error"
    """
    name = normalise_filename(jsonfile_name)
    if not name:
        return None, "no_name"
    if not is_valid_filename(name):
        return None, "invalid_name"

    path = _full_path(name)
    tmp_path = path + ".tmp"
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(tmp_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
        os.replace(tmp_path, path)
        return name, "saved"
    except (OSError, TypeError, ValueError) as err:
        logger.error("Could not save to %s: %s", path, err)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return None, "io_error"


# ---------------------------------------------------------------------------
# Filtering / querying
# ---------------------------------------------------------------------------

def filter_by_decision_status(records, decision_status):
    """Records whose evaluation decision_status matches exactly.
    Example: filter_by_decision_status(records, "PRE_APPROVED_TIER_1")"""
    return [
        r for r in records
        if _section(r, "evaluation").get("decision_status") == decision_status
    ]


def filter_approved_records(records):
    """Records where the audit passed."""
    return [
        r for r in records
        if _section(r, "evaluation").get("audit_passed") is True
    ]


def find_records_by_company(records, company_name):
    """Case-insensitive exact match on company name."""
    wanted = str(company_name).strip().lower()
    return [
        r for r in records
        if str(_section(r, "company_profile").get("company_name", "")).strip().lower() == wanted
    ]


def available_decision_statuses(records):
    """Sorted list of the distinct decision statuses present in the records
    (lets io_manager offer only filters that can match something)."""
    statuses = {
        _section(r, "evaluation").get("decision_status")
        for r in records
    }
    return sorted(status for status in statuses if isinstance(status, str) and status)


# ---------------------------------------------------------------------------
# Bridge back to io_manager's display format
# ---------------------------------------------------------------------------

def audit_record_to_display_format(audit_record):
    """
    Converts a saved audit record into the capitalised keys that
    io_manager.display_applied_grants() uses. Needed so records loaded from
    JSON can be listed exactly like records entered in the current session.
    """
    profile = _section(audit_record, "company_profile")
    return {
        "Company Name": profile.get("company_name", ""),
        "Company Industry": profile.get("company_industry", ""),
        "Company Total Revenue": profile.get("annual_revenue_sgd", 0.0),
        "Total Employees": profile.get("group_employment_size", 0),
        "Local Equity": profile.get("local_shareholding_pct", 0.0),
        "Proposal Type": profile.get("proposal_type", ""),
        "Proposal Narrative": _section(audit_record, "proposal").get("raw_narrative", ""),
        "Baseline Energy Expenditure": profile.get("baseline_annual_energy_expenditure_sgd", 0.0),
        "Estimated Retrofit Cost": profile.get("estimated_retrofit_cost_sgd", 0.0),
        "Reporting Advisory Fee": profile.get("reporting_advisory_fee_sgd", 0.0),
    }