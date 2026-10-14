from typing import Any
from collections.abc import Callable, Iterator
import json
import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime

# Type aliases (plain dicts/lists - the project uses no classes)
Record = dict[str, Any]
Records = list[Record]
AiAudit = dict[str, Any]

# Stay silent unless someone configures logging (otherwise Python's default
# handler would write warnings straight to the terminal).
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

LOG_FILE = "app.log"

# Invalid characters for filenames
INVALID_FILENAME_CHARS = '/\\:*?"<>|'

# Where save files live. Override with the DATA_DIR environment variable
# (e.g. point it at a mounted volume when running in Docker).
DATA_DIR = os.environ.get("DATA_DIR", ".")

# Legacy default filename for callers that still use a shared save file.
DEFAULT_SAVE_FILE = "audit_records.json"

# Every saved audit record must contain these sections, each as a dict.
REQUIRED_RECORD_SECTIONS = ("company_profile", "proposal", "ai_audit", "evaluation")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging() -> bool:
    """Sends the app's log messages (AI failures, unreadable files, ...) to
    DATA_DIR/app.log so problems can be looked into afterwards while the app
    carries on. Safe to call more than once. Returns True if logging to the
    file is on; if the file cannot be opened the app simply runs without it."""
    root = logging.getLogger()
    path = os.path.abspath(_full_path(LOG_FILE))
    for handler in root.handlers:
        if getattr(handler, "baseFilename", None) == path:
            return True
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
    except OSError:
        return False
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    return True


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

def normalise_filename(jsonfile_name: str) -> str:
    """Strips whitespace and makes sure the name ends with .json
    (any capitalisation of the extension is accepted)."""
    jsonfile_name = str(jsonfile_name).strip()
    if jsonfile_name and not jsonfile_name.lower().endswith('.json'):
        jsonfile_name += '.json'
    return jsonfile_name


def is_valid_filename(jsonfile_name: str) -> bool:
    """A bare filename only: no folders, control characters, or empty stem."""
    if any(char in jsonfile_name for char in INVALID_FILENAME_CHARS):
        return False
    if any(ord(char) < 32 for char in jsonfile_name):
        return False
    stem = jsonfile_name[:-len('.json')] if jsonfile_name.lower().endswith('.json') else jsonfile_name
    # Rejects ".json", "..json", " .json" and similar nameless files.
    return stem.strip(" .") != ""


def _full_path(jsonfile_name: str) -> str:
    """Path of a shared file in DATA_DIR (users.json, audit_history.json)."""
    return os.path.join(DATA_DIR, jsonfile_name)


# ---------------------------------------------------------------------------
# Per-user record files
# ---------------------------------------------------------------------------
# Saved record files (menu options 2/3 and the PDF export) are kept in
# DATA_DIR/records/<username>/ so one user can never load, overwrite or
# list another user's files. main.py calls set_active_user() at login and
# set_active_user(None) at logout. With no active user (e.g. tests or old
# scripts) the files stay in DATA_DIR itself, as before.

RECORDS_DIR_NAME = "records"
_USERNAME_FOR_PATH = re.compile(r"[a-z0-9_]{1,64}")
_active_user = None
def _is_safe_username(username) -> bool:
    # move the exact condition from set_active_user here
    return (
        isinstance(username, str)
        and 0 < len(username) <= 64
        and re.fullmatch(r"[a-z0-9_]+", username) is not None
    )

def set_active_user(username: str | None) -> None:
    """Chooses whose folder the record files are saved to / loaded from.
    Pass None to go back to no active user."""
    if username is not None and not _is_safe_username(username):
        raise ValueError("unsafe username")
    global _active_user
    if username is None:
        _active_user = None
        return
    if not isinstance(username, str) or not _USERNAME_FOR_PATH.fullmatch(username):
        # Never build a folder name from anything unexpected (e.g. "..").
        raise ValueError("Invalid username for a records folder.")
    _active_user = username


def get_active_user() -> str | None:
    return _active_user


def _records_dir() -> str:
    if _active_user is None:
        return DATA_DIR
    return os.path.join(DATA_DIR, RECORDS_DIR_NAME, _active_user)


def _record_path(jsonfile_name: str) -> str:
    return os.path.join(_records_dir(), jsonfile_name)


def generate_company_save_filename(company_name: str) -> str:
    """Return a stable, safe JSON filename for one company.

    Repeated assessments for the same company use this same JSON/PDF pair;
    different company names produce separate pairs.
    """
    company_name = str(company_name or "Company").strip()
    safe_name = "".join(
        "_" if char in INVALID_FILENAME_CHARS or ord(char) < 32 else char
        for char in company_name
    )
    safe_name = re.sub(r"\s+", " ", safe_name).strip(" .")[:100].rstrip(" .")
    if not safe_name:
        safe_name = "Company"
    return f"audit_{safe_name}.json"


# ---------------------------------------------------------------------------
# Record helpers
# ---------------------------------------------------------------------------

def is_valid_audit_record(record: Any) -> bool:
    """Accept both canonical audit records and the current IO Manager record shape."""
    if not isinstance(record, dict):
        return False

    # Canonical records used by the newer manager architecture.
    if all(isinstance(record.get(section), dict) for section in REQUIRED_RECORD_SECTIONS):
        return True

    # Flat, display-oriented records created by the attached main.py.
    return "Company Name" in record and (
        "Proposal Narrative" in record or "Company Total Revenue" in record
    )


def _section(record: Any, section_name: str) -> dict[str, Any]:
    """Safe access to a record section: always returns a dict."""
    if not isinstance(record, dict):
        return {}
    section = record.get(section_name)
    return section if isinstance(section, dict) else {}


# ---------------------------------------------------------------------------
# Audit record management
# ---------------------------------------------------------------------------

def generate_audit_id(records: Any) -> int:
    """Return the next ID for either nested or flat audit records."""
    if not isinstance(records, list) or not records:
        return 1

    highest_id = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        audit_id = record.get("audit_id", record.get("Audit ID", 0))
        if isinstance(audit_id, int) and not isinstance(audit_id, bool):
            highest_id = max(highest_id, audit_id)
    return highest_id + 1


def create_audit_record(audit_id: int, user_profile: dict[str, Any], proposal: dict[str, Any], ai_audit: AiAudit, evaluation: dict[str, Any]) -> Record:
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


def add_audit_record(records: Records, audit_record: Record) -> Records:
    """Add a completed audit record to the current record list."""
    if not isinstance(records, list):
        records = []
    records.append(audit_record)
    return records


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def inspect_save_file(jsonfile_name: str) -> tuple[str, str]:
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
    if os.path.isfile(_record_path(name)):
        return name, "exists"
    return name, "not_found"


def _backup_corrupt_file(path: str) -> None:
    """Moves a bad file aside so a later save cannot silently destroy it."""
    try:
        os.replace(path, path + ".corrupt")
    except OSError as err:
        logger.error("Could not back up corrupt file %s: %s", path, err)


def load_data_from_json(jsonfile_name: str) -> tuple[Records, str, str]:
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

    path = _record_path(name)
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

def is_data_loaded(data: Records, jsonfile_name: str) -> bool:
    """True if there is already data/filename in memory (io_manager should
    then ask the user before overwriting it)."""
    return not (data == [] and jsonfile_name == "")


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

def save_data_to_json(data: Records, jsonfile_name: str) -> tuple[str | None, str]:
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

    path = _record_path(name)
    tmp_path = path + ".tmp"
    try:
        os.makedirs(_records_dir(), exist_ok=True)
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
# User accounts and per-user audit history
# ---------------------------------------------------------------------------
# users.json         -> {username: {password_hash, salt, ...}}
# audit_history.json -> {username: [audit_record, audit_record, ...]}
#
# The Data Manager only reads and writes these files. It never hashes or
# checks passwords (Logic Manager's job) and never prints prompts (I/O
# Manager's job). NOTE: storage is plain JSON for now and is NOT secure -
# only the passwords are protected (by hashing).

USERS_FILE = "users.json"
AUDIT_HISTORY_FILE = "audit_history.json"


def read_json_file(filename: str, default: Any) -> Any:
    """Returns the parsed contents of a data file, or `default` if the file
    does not exist yet. Returns None if the file exists but cannot be read,
    so callers never overwrite data they failed to load. A corrupt file is
    set aside as .corrupt, like the record save files."""
    path = _full_path(filename)
    if not os.path.isfile(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except ValueError:  # JSONDecodeError and UnicodeDecodeError
        logger.error("%s contains invalid JSON.", path)
        _backup_corrupt_file(path)
        return default
    except (OSError, RecursionError) as err:
        logger.error("Could not read %s: %s", path, err)
        return None
    if not isinstance(data, type(default)):
        logger.error("%s does not have the expected format.", path)
        _backup_corrupt_file(path)
        return default
    return data


def write_json_file(filename: str, data: Any) -> bool:
    """Writes data to a temporary file first and then swaps it in, so a crash
    midway can never leave a half-written file behind.
    Returns True on success, False otherwise."""
    path = _full_path(filename)
    tmp_path = path + ".tmp"
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(tmp_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
        os.replace(tmp_path, path)
        return True
    except (OSError, TypeError, ValueError) as err:
        logger.error("Could not save to %s: %s", path, err)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False


# ---------- Locking ----------
# users.json and audit_history.json are read, changed and rewritten as a
# whole. If two copies of the app (e.g. two containers sharing one folder)
# did that at the same moment, one change would be lost. A small ".lock"
# file, created atomically, makes the second one wait its turn.
LOCK_TIMEOUT_SECONDS = 5.0
LOCK_STALE_SECONDS = 30.0


@contextmanager
def _file_lock(filename: str) -> Iterator[bool]:
    """Yields True once this process holds the lock for `filename`, or
    False if it could not be obtained within LOCK_TIMEOUT_SECONDS (the
    caller then reports a failed save instead of risking a lost update).
    A lock older than LOCK_STALE_SECONDS (left by a crashed run) is
    removed."""
    lock_path = _full_path(filename) + ".lock"
    held = False
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(descriptor)
                held = True
                break
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(lock_path) > LOCK_STALE_SECONDS:
                        os.remove(lock_path)
                        continue
                except OSError:
                    pass  # lock vanished or cannot be inspected: just retry
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
    except OSError as err:
        logger.error("Could not lock %s: %s", filename, err)
    try:
        yield held
    finally:
        if held:
            try:
                os.remove(lock_path)
            except OSError:
                pass


# ---------- Users ----------
def load_users() -> dict[str, Any]:
    """All stored users as {username: record}, or None if unreadable."""
    return read_json_file(USERS_FILE, {})


def get_user(username: str) -> dict[str, Any] | None:
    """Returns the stored user record for `username`, or None."""
    users = load_users()
    if users is None:
        return None
    record = users.get(username)
    return record if isinstance(record, dict) else None


def user_exists(username: str) -> bool:
    """True if the username is already in users.json (even if its record
    is damaged, so it can never be silently overwritten)."""
    users = load_users()
    return users is not None and username in users


def save_new_user(user_record: dict[str, Any]) -> bool:
    """Adds a new user (built by logic_manager.build_new_user_record).
    Returns False if the username is already taken or the write failed."""
    with _file_lock(USERS_FILE) as locked:
        if not locked:
            return False
        users = load_users()
        if users is None:
            return False
        username = user_record["username"]
        if username in users:
            return False

        stored = dict(user_record)
        stored["created_at"] = datetime.now().isoformat(timespec="seconds")
        users[username] = stored
        return write_json_file(USERS_FILE, users)


# ---------- Audit history ----------
def load_audit_history() -> dict[str, Any]:
    """All saved audits as {username: [audit, ...]}, or None if unreadable."""
    return read_json_file(AUDIT_HISTORY_FILE, {})


def get_user_audits(username: str) -> list[Record]:
    """All audits saved by `username`, oldest first."""
    if not _is_safe_username(username):
        return []
    history = load_audit_history()
    audits = history.get(username, []) if history else []
    if not isinstance(audits, list):
        return []
    # Ignore damaged entries so the screens only ever see audit dicts.
    return [audit for audit in audits if isinstance(audit, dict)]


def append_user_audit(username: str, application: Record, ai_audit: AiAudit, result: dict[str, Any] | None) -> Record | None:
    """Saves one completed audit (inputs + AI output + decision) under the
    logged-in user. Returns the saved record, or None on failure."""
    if not _is_safe_username(username):
        raise ValueError("unsafe username")
    with _file_lock(AUDIT_HISTORY_FILE) as locked:
        if not locked:
            return None
        history = load_audit_history()
        if history is None:
            return None
        user_audits = history.get(username)
        if not isinstance(user_audits, list):
            user_audits = []
            history[username] = user_audits

        audit_record = {
            "audit_id": generate_audit_id(user_audits),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "application": application,
            "ai_audit": ai_audit,
            "result": result,
        }
        user_audits.append(audit_record)

        if write_json_file(AUDIT_HISTORY_FILE, history):
            return audit_record
        return None


# ---------------------------------------------------------------------------
# Filtering / querying
# ---------------------------------------------------------------------------

def filter_by_decision_status(records: Records, decision_status: str) -> Records:
    """Records whose evaluation decision_status matches exactly.
    Example: filter_by_decision_status(records, "PRE_APPROVED_TIER_1")"""
    return [
        r for r in records
        if _section(r, "evaluation").get("decision_status") == decision_status
    ]


def filter_approved_records(records: Records) -> Records:
    """Records where the audit passed."""
    return [
        r for r in records
        if _section(r, "evaluation").get("audit_passed") is True
    ]


def find_records_by_company(records: Records, company_name: str) -> Records:
    """Case-insensitive exact match on company name."""
    wanted = str(company_name).strip().lower()
    return [
        r for r in records
        if str(_section(r, "company_profile").get("company_name", "")).strip().lower() == wanted
    ]


def available_decision_statuses(records: Records) -> list[str]:
    """Sorted list of the distinct decision statuses present in the records
    (lets io_manager offer only filters that can match something)."""
    statuses = {
        _section(r, "evaluation").get("decision_status")
        for r in records
    }
    return sorted(status for status in statuses if isinstance(status, str) and status)

def merge_records(existing: Records, new_records: Records) -> Records:
    """Existing records first, then any new ones not already present."""
    return existing + [r for r in new_records if r not in existing]


# ---------------------------------------------------------------------------
# Editing and deleting records in memory (menu options 5 and 6)
# ---------------------------------------------------------------------------
# These work on the display-layout records ("Company Name", ...) that the
# session keeps. They return a NEW list and never change the one passed in,
# so a failed edit can't leave half-changed data behind.

EDITABLE_RECORD_FIELDS = (
    "Company Name",
    "Company Industry",
    "Company Total Revenue",
    "Total Employees",
    "Local Equity",
    "Sustainability Grant",
    "Proposal Narrative",
    "Baseline Energy Expenditure",
    "Estimated Retrofit Cost",
    "Reporting Advisory Fee",
)


def _valid_index(records: Any, index: Any) -> bool:
    return (
        isinstance(records, list)
        and isinstance(index, int)
        and not isinstance(index, bool)
        and 0 <= index < len(records)
    )


def update_record_field(records: Records, index: int, field: str, value: Any) -> tuple[Records, str]:
    """Returns (new_records, status). status is "updated", "bad_index",
    "bad_field" or "not_editable" (the record is not in the display layout)."""
    if not _valid_index(records, index):
        return records, "bad_index"
    if field not in EDITABLE_RECORD_FIELDS:
        return records, "bad_field"
    if not isinstance(records[index], dict) or "Company Name" not in records[index]:
        return records, "not_editable"

    changed = dict(records[index])
    changed[field] = value
    return records[:index] + [changed] + records[index + 1:], "updated"


def delete_record(records: Records, index: int) -> tuple[Records, str]:
    """Returns (new_records, status). status is "deleted" or "bad_index"."""
    if not _valid_index(records, index):
        return records, "bad_index"
    return records[:index] + records[index + 1:], "deleted"


# ---------------------------------------------------------------------------
# Filtering the audit history (option 9)
# ---------------------------------------------------------------------------

def audit_decision_status(audit: Any) -> str:
    """The decision status stored in one history entry, or "" if missing."""
    status = _section(audit, "result").get("decision_status")
    return status if isinstance(status, str) else ""


def available_audit_statuses(audits: list[Record]) -> list[str]:
    """Sorted distinct decision statuses in the history (so the I/O Manager
    only offers filters that can match something)."""
    return sorted({audit_decision_status(audit) for audit in audits} - {""})


def filter_audits_by_status(audits: list[Record], decision_status: str) -> list[Record]:
    """History entries whose decision status matches exactly."""
    return [audit for audit in audits if audit_decision_status(audit) == decision_status]


def search_audits_by_company(audits: list[Record], text: str) -> list[Record]:
    """History entries whose company name contains `text` (ignoring case)."""
    wanted = str(text).strip().lower()
    return [
        audit for audit in audits
        if wanted in str(_section(audit, "application").get("Company Name", "")).lower()
    ]


# ---------------------------------------------------------------------------
# PDF export of one saved audit (option 9)
# ---------------------------------------------------------------------------

def audit_to_report_record(audit: Record) -> Record:
    """Turns one audit-history entry into the flat record layout the PDF
    report already understands: the application's own keys plus the AI result
    and the grant decision, so the report shows the full, final outcome."""
    report = dict(_section(audit, "application"))
    report["AI Audit"] = _section(audit, "ai_audit")
    report["Grant Decision"] = _section(audit, "result")
    report["Audit ID"] = audit.get("audit_id", 1) if isinstance(audit, dict) else 1
    report["Created At"] = audit.get("timestamp", "") if isinstance(audit, dict) else ""
    return report


def audit_pdf_filename(audit: Record) -> str:
    """A safe default PDF name such as 'audit_3_Apex Haulage.pdf'."""
    company = _section(audit, "application").get("Company Name", "")
    safe_company = generate_company_save_filename(company)[len("audit_"):-len(".json")]
    audit_id = audit.get("audit_id", "") if isinstance(audit, dict) else ""
    return f"audit_{audit_id}_{safe_company}.pdf"


def export_audit_to_pdf(audit: Record) -> tuple[str | None, str]:
    """Writes the PDF report for one history entry into the user's records
    folder. Returns (pdf_filename, status), as export_records_to_pdf does."""
    if not isinstance(audit, dict) or not audit:
        return None, "pdf_error"
    return export_records_to_pdf([audit_to_report_record(audit)], "audit", audit_pdf_filename(audit))


def get_records_folder() -> str:
    """Folder the active user's saved files and PDFs go into (for messages)."""
    return os.path.abspath(_records_dir())


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

def export_json_to_pdf(jsonfile_name: str, pdf_filename: str | None = None) -> tuple[str | None, str]:
    """Create a polished, company-facing assessment report from saved JSON.

    The report includes every audit record in the source file. It is saved in
    DATA_DIR and uses the JSON filename stem by default.

    Returns (pdf_filename, status). A successful export returns "exported".
    Requires ReportLab: python -m pip install reportlab
    """
    records, clean_json_name, load_status = load_data_from_json(jsonfile_name)
    if load_status != "loaded":
        return None, load_status
    return export_records_to_pdf(records, clean_json_name, pdf_filename)


# ========================================================
# PDF report: text helpers (no ReportLab needed)
# ========================================================
REPORT_LABEL_NAMES = {
    "company_name": "Company name",
    "company_industry": "Industry",
    "annual_revenue_sgd": "Annual revenue",
    "group_employment_size": "Group employees",
    "local_shareholding_pct": "Local shareholding",
    "proposal_type": "Proposal type",
    "sustainability_grant": "Sustainability Grant",
    "baseline_annual_energy_expenditure_sgd": "Annual energy expenditure",
    "estimated_retrofit_cost_sgd": "Estimated retrofit cost",
    "reporting_advisory_fee_sgd": "Reporting advisory fee",
    "scope_category": "Emissions scope",
    "primary_intervention_type": "Main intervention",
    "estimated_energy_reduction_pct": "Estimated energy reduction",
    "estimated_lifetime_abatement_tonnes": "Estimated lifetime abatement",
    "detected_exclusion_keywords": "Potential exclusions",
    "implementation_bottleneck": "Implementation constraint",
    "ai_reasoning_summary": "AI-generated proposal analysis",
    "approved_subsidy_sgd": "Potential grant amount",
    "audit_passed": "Screening result",
    "is_sme": "Meets SME criteria",
    "created_at": "Assessment date",
    "raw_narrative": "Proposal narrative",
}

REPORT_STATUS_LABELS = {
    "REJECT_NON_SME": "Did not qualify - company criteria",
    "REJECT_LOW_IMPACT": "Did not qualify - impact threshold",
    "PRE_APPROVED_SRG": "Potential match - reporting grant",
    "PRE_APPROVED_TIER_1": "Potential match - base tier",
    "PRE_APPROVED_TIER_1_ADVANCED": "Potential match - advanced tier",
    "PROVISIONAL_APPROVAL_TIER_2": "Potential match - provisional",
    "MANUAL_REVIEW": "Further review required",
    "MANUAL_EXCLUSION_REVIEW": "Further review required - potential exclusion",
}


def _nice_label(value: Any) -> str:
    key = str(value)
    return REPORT_LABEL_NAMES.get(key, key.replace("_", " ").strip().capitalize())


def _readable_value(value: Any, key: str = "") -> str:
    """Format common values as prose, never as JSON source text."""
    if value is None or value == "":
        return "Not provided"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        lowered = str(key).lower()
        if any(term in lowered for term in (
            "_sgd", "revenue", "cost", "fee", "expenditure", "subsidy", "grant amount"
        )):
            return f"SGD {value:,.2f}"
        if "pct" in lowered or "percent" in lowered:
            return f"{value:,.1f}%"
        if "tonne" in lowered:
            return f"{value:,.1f} tonnes CO2e"
        return f"{value:,}" if isinstance(value, int) else f"{value:,.2f}"
    if isinstance(value, list):
        return "\n".join(f"- {_readable_value(item)}" for item in value) if value else "None recorded"
    if isinstance(value, dict):
        return "\n".join(
            f"{_nice_label(item_key)}: {_readable_value(item_value, item_key)}"
            for item_key, item_value in value.items()
        )
    text = str(value)
    if str(key).lower().replace(" ", "_") == "decision_status":
        return REPORT_STATUS_LABELS.get(text, text.replace("_", " ").title())
    return text


def _outcome_for(evaluation: dict[str, Any]) -> tuple[str, str, str]:
    """Returns (headline, colour name, explanation) for the outcome panel.
    The colour name is looked up in the report theme."""
    status = str(evaluation.get("decision_status", ""))
    if status.startswith("MANUAL"):
        return (
            "Further review required",
            "amber",
            "The screening identified an item that needs review before an eligibility conclusion can be made.",
        )
    if status.startswith("REJECT"):
        return (
            "Did not qualify under this screening",
            "red",
            "The recorded assessment did not meet the current screening criteria. See the reasons and next steps below.",
        )
    if evaluation.get("audit_passed") is True:
        return (
            "Potential grant match identified",
            "teal",
            "The initial screening found a potential match. Final eligibility and funding remain subject to the grant administrator's review.",
        )
    return (
        "No positive eligibility result recorded",
        "amber",
        "The saved assessment does not record a positive eligibility result. Review the details below.",
    )


def _screening_result_for(evaluation: dict[str, Any]) -> str:
    """Translate the logic status into a clear reader-facing outcome."""
    status = str(evaluation.get("decision_status", "")).upper()
    if status.startswith("MANUAL"):
        return "Further review required"
    if status.startswith("REJECT"):
        return "Did not qualify"
    if evaluation.get("audit_passed") is True:
        return "Passed"
    if not status:
        return "Not recorded"
    # An unfamiliar or incomplete status should not be presented as
    # a rejection or a pass; route it to review in the report wording.
    return "Further review required"


def _is_nested_record(record: Record) -> bool:
    return all(isinstance(record.get(section), dict) for section in REQUIRED_RECORD_SECTIONS)


def _report_sections(record: Record, index: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Any, Any]:
    """Returns (profile, proposal, ai_audit, evaluation, record_id, created_at)
    for either record layout (nested audit record or the flat menu record)."""
    if _is_nested_record(record):
        return (
            _section(record, "company_profile"),
            _section(record, "proposal"),
            _section(record, "ai_audit"),
            _section(record, "evaluation"),
            record.get("audit_id", index + 1),
            record.get("created_at", ""),
        )
    profile = {
        "company_name": record.get("Company Name", ""),
        "company_industry": record.get("Company Industry", ""),
        "annual_revenue_sgd": record.get("Company Total Revenue", 0.0),
        "group_employment_size": record.get("Total Employees", 0),
        "local_shareholding_pct": record.get("Local Equity", 0.0),
        "proposal_type": record.get("Proposal Type", ""),
        "sustainability_grant": record.get("Sustainability Grant", ""),
        "baseline_annual_energy_expenditure_sgd": record.get("Baseline Energy Expenditure", 0.0),
        "estimated_retrofit_cost_sgd": record.get("Estimated Retrofit Cost", 0.0),
        "reporting_advisory_fee_sgd": record.get("Reporting Advisory Fee", 0.0),
    }
    proposal = {"raw_narrative": record.get("Proposal Narrative", "")}
    ai_audit = record.get("AI Audit", {})
    evaluation = record.get("Grant Decision", {})
    if not isinstance(ai_audit, dict):
        ai_audit = {}
    if not isinstance(evaluation, dict):
        evaluation = {}
    return (profile, proposal, ai_audit, evaluation,
            record.get("Audit ID", index + 1), record.get("Created At", ""))


def _report_company_name(records: Records) -> str:
    """The name printed in the page footer (taken from the first record)."""
    name = "the named company"
    if records:
        first = records[0]
        if _is_nested_record(first):
            name = str(_section(first, "company_profile").get("company_name") or name).strip()
        else:
            name = str(first.get("Company Name") or name).strip()
    return name


def _assessment_date_time(created_at: Any) -> tuple[str, str]:
    try:
        moment = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        return moment.strftime("%Y-%m-%d"), moment.strftime("%H:%M:%S")
    except (TypeError, ValueError):
        return "Not recorded", "Not recorded"


def _resolve_pdf_name(source_name: str, pdf_filename: str | None) -> str | None:
    """Returns the PDF file name to use, or None when it is not a safe name."""
    if pdf_filename is None or not str(pdf_filename).strip():
        pdf_name = os.path.splitext(source_name)[0] + ".pdf"
    else:
        pdf_name = str(pdf_filename).strip()
        if not pdf_name.lower().endswith(".pdf"):
            pdf_name += ".pdf"

    pdf_stem = os.path.splitext(pdf_name)[0]
    if (
        not pdf_stem.strip(" .")
        or os.path.basename(pdf_name) != pdf_name
        or any(char in pdf_name for char in INVALID_FILENAME_CHARS)
        or any(ord(char) < 32 for char in pdf_name)
    ):
        return None
    return pdf_name


# ========================================================
# PDF report: layout (needs ReportLab, imported when used)
# ========================================================
def _register_report_fonts() -> tuple[str, str]:
    """Embed Times New Roman when available so the report keeps the requested
    typeface on other computers. In Docker, mount/provide the font files
    and set TIMES_NEW_ROMAN_FONT and TIMES_NEW_ROMAN_BOLD_FONT. The
    built-in Times fonts are the portable fallback when TNR is unavailable.
    Returns (regular_font, bold_font)."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    regular_font = "Times-Roman"
    bold_font = "Times-Bold"
    configured_regular = os.environ.get("TIMES_NEW_ROMAN_FONT")
    configured_bold = os.environ.get("TIMES_NEW_ROMAN_BOLD_FONT")
    font_candidates = []
    if configured_regular:
        font_candidates.append((configured_regular, configured_bold))
    font_candidates.extend([
        (r"C:\Windows\Fonts\times.ttf", r"C:\Windows\Fonts\timesbd.ttf"),
        ("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf",
         "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf"),
        ("/Library/Fonts/Times New Roman.ttf",
         "/Library/Fonts/Times New Roman Bold.ttf"),
    ])
    for regular_path, bold_path in font_candidates:
        if regular_path and os.path.isfile(regular_path):
            pdfmetrics.registerFont(TTFont("CompanyAudit", regular_path))
            regular_font = "CompanyAudit"
            if bold_path and os.path.isfile(bold_path):
                pdfmetrics.registerFont(TTFont("CompanyAudit-Bold", bold_path))
                bold_font = "CompanyAudit-Bold"
            else:
                bold_font = regular_font
            break
    return regular_font, bold_font


def _build_report_theme() -> dict[str, Any]:
    """One restrained palette and one set of paragraph styles for the whole
    report. Outcome cards use a muted red for non-qualification, amber for
    review, and teal for a match. Returned as a dict keyed by name."""
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm

    regular_font, bold_font = _register_report_fonts()
    theme: dict[str, Any] = {
        "regular_font": regular_font,
        "bold_font": bold_font,
        "navy": colors.HexColor("#18324B"),
        "teal": colors.HexColor("#167C80"),
        "ink": colors.HexColor("#253746"),
        "muted": colors.HexColor("#657786"),
        "line": colors.HexColor("#D9E2E8"),
        "pale_blue": colors.HexColor("#F2F6F9"),
        "pale_teal": colors.HexColor("#E8F4F3"),
        "pale_red": colors.HexColor("#FBEDEC"),
        "red": colors.HexColor("#A33A35"),
        "pale_amber": colors.HexColor("#FFF5E3"),
        "amber": colors.HexColor("#936218"),
        "white": colors.white,
    }
    navy, ink, muted, line = theme["navy"], theme["ink"], theme["muted"], theme["line"]

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CompanyAuditTitle", parent=styles["Title"], fontName=bold_font,
        fontSize=20, leading=24, alignment=1, textColor=navy,
        spaceAfter=2 * mm,
    )
    subtitle_style = ParagraphStyle(
        "CompanyAuditSubtitle", parent=styles["Normal"], fontName=bold_font,
        fontSize=9, leading=12, alignment=1, textColor=navy,
        spaceAfter=5 * mm,
    )
    section_style = ParagraphStyle(
        "CompanyAuditSection", parent=styles["Heading2"], fontName=bold_font,
        fontSize=11, leading=14, textColor=navy,
        spaceBefore=4 * mm, spaceAfter=2 * mm, keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "CompanyAuditBody", parent=styles["BodyText"], fontName=regular_font,
        fontSize=9, leading=13, textColor=ink, splitLongWords=True,
    )
    label_style = ParagraphStyle(
        "CompanyAuditLabel", parent=body_style, fontName=bold_font,
        textColor=navy,
    )
    small_style = ParagraphStyle(
        "CompanyAuditSmall", parent=body_style, fontSize=8, leading=10,
        textColor=muted,
    )
    disclaimer_style = ParagraphStyle(
        "CompanyAuditDisclaimer", parent=small_style, fontName=bold_font,
        fontSize=9, leading=12,
    )
    theme.update({
        "title": title_style,
        "subtitle": subtitle_style,
        "section": section_style,
        "body": body_style,
        "label": label_style,
        "small": small_style,
        "black_small": ParagraphStyle(
            "CompanyAuditBlackSmall", parent=small_style,
            textColor=colors.black,
        ),
        "black_disclaimer": ParagraphStyle(
            "CompanyAuditBlackDisclaimer", parent=disclaimer_style,
            textColor=colors.black,
        ),
        "ai_note": ParagraphStyle(
            "CompanyAuditAINote", parent=disclaimer_style,
            textColor=colors.black,
        ),
        "outcome": ParagraphStyle(
            "CompanyAuditOutcome", parent=body_style, fontName=bold_font,
            fontSize=13, leading=17, textColor=navy,
        ),
        "narrative": ParagraphStyle(
            "CompanyAuditNarrative", parent=body_style, leftIndent=3 * mm,
            rightIndent=3 * mm, borderColor=line, borderWidth=0.5,
            borderPadding=8, backColor=theme["pale_blue"],
        ),
        "summary": ParagraphStyle(
            "CompanyAuditSummary", parent=body_style, fontSize=9,
            leading=13, textColor=ink,
        ),
    })
    return theme


def _pdf_para(theme: dict[str, Any], value: Any, style: Any = None) -> Any:
    from reportlab.platypus import Paragraph
    from xml.sax.saxutils import escape

    safe = escape(str(value)).replace("\r\n", "\n").replace("\r", "\n")
    return Paragraph(safe.replace("\n", "<br/>"), style or theme["body"])


def _pdf_heading(theme: dict[str, Any], text: str) -> Any:
    from reportlab.platypus import Paragraph
    from xml.sax.saxutils import escape

    return Paragraph(escape(text), theme["section"])


def _add_detail_table(story: list[Any], theme: dict[str, Any], items: list[tuple[str, Any]]) -> None:
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer, Table, TableStyle

    if not items:
        story.append(_pdf_para(theme, "No information was recorded for this section.", theme["small"]))
        return
    rows = [
        [
            _pdf_para(theme, _nice_label(key), theme["label"]),
            _pdf_para(theme, _readable_value(value, key), theme["body"]),
        ]
        for key, value in items
    ]
    table = Table(rows, colWidths=[53 * mm, 117 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), theme["pale_blue"]),
        ("ROWBACKGROUNDS", (1, 0), (1, -1), [theme["white"], colors.HexColor("#FAFBFC")]),
        ("GRID", (0, 0), (-1, -1), 0.35, theme["line"]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table, Spacer(1, 2 * mm)])


def _add_bullets(story: list[Any], theme: dict[str, Any], heading: str, items: Any, color: Any = None) -> None:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm

    if not items:
        return
    story.append(_pdf_heading(theme, heading))
    if not isinstance(items, list):
        items = [items]
    bullet_style = ParagraphStyle(
        "CompanyAuditBullet", parent=theme["body"], leftIndent=5 * mm,
        firstLineIndent=-3 * mm, textColor=color or theme["ink"], spaceAfter=2,
    )
    for item in items:
        story.append(_pdf_para(theme, f"- {_readable_value(item)}", bullet_style))


def _add_outcome_panel(story: list[Any], theme: dict[str, Any], evaluation: dict[str, Any]) -> str:
    """Adds the coloured outcome box and disclaimer. Returns the headline."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    headline, colour_name, explanation = _outcome_for(evaluation)
    outcome_color = theme[colour_name]
    outcome_bg = theme["pale_" + colour_name]
    coloured_style = ParagraphStyle(
        "CompanyAuditOutcomeColored", parent=theme["outcome"],
        textColor=outcome_color,
    )
    panel = Table(
        [[Paragraph(escape(headline), coloured_style)],
         [_pdf_para(theme, explanation, theme["summary"])]],
        colWidths=[170 * mm], hAlign="LEFT",
    )
    panel.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), outcome_bg),
        ("BOX", (0, 0), (-1, -1), 0.8, outcome_color),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([panel, Spacer(1, 2 * mm)])
    story.append(_pdf_para(
        theme,
        "This is a preliminary automated screening report, not an official grant decision or funding offer.",
        theme["black_disclaimer"],
    ))
    return headline


def _add_ai_section(story: list[Any], theme: dict[str, Any], ai_audit: dict[str, Any]) -> None:
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer

    story.append(_pdf_heading(theme, "AI-generated scope and impact analysis"))
    story.append(_pdf_para(
        theme,
        "Supporting analysis generated by AI from the proposal description. "
        "It does not determine grant eligibility; the Logic Manager applies "
        "the programmed rules shown in the eligibility assessment above.",
        theme["ai_note"],
    ))
    story.append(Spacer(1, 3 * mm))
    _add_detail_table(story, theme, [
        (key, value) for key, value in ai_audit.items() if key != "ai_reasoning_summary"
    ])
    if ai_audit.get("ai_reasoning_summary"):
        story.append(_pdf_para(theme, "AI-generated proposal summary", theme["label"]))
        story.append(_pdf_para(theme, ai_audit["ai_reasoning_summary"], theme["body"]))


def _add_record_pages(story: list[Any], theme: dict[str, Any], record: Record, index: int) -> None:
    """Adds the pages for one audit record: summary page, then AI analysis."""
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, Spacer

    profile, proposal, ai_audit, evaluation, record_id, created_at = _report_sections(record, index)

    story.extend([
        Spacer(1, 4 * mm),
        Paragraph("GREEN GRANT ELIGIBILITY ASSESSMENT", theme["title"]),
        Paragraph("Company audit report", theme["subtitle"]),
    ])
    story.append(_pdf_heading(theme, str(profile.get("company_name") or "Company name not recorded")))

    assessment_date, assessment_time = _assessment_date_time(created_at)
    story.append(_pdf_para(theme, f"Assessment ID: {record_id}", theme["black_small"]))
    story.append(_pdf_para(theme, f"Date: {assessment_date} (YYYY-MM-DD)", theme["black_small"]))
    story.append(_pdf_para(theme, f"Time: {assessment_time}", theme["black_small"]))
    story.append(Spacer(1, 3 * mm))

    headline = _add_outcome_panel(story, theme, evaluation)

    story.append(_pdf_heading(theme, "Logic Manager eligibility assessment"))
    _add_detail_table(story, theme, [
        ("Decision status", evaluation.get("decision_status", "Not recorded")),
        ("Meets SME criteria", evaluation.get("is_sme", "Not recorded")),
        ("Potential grant amount", evaluation.get("approved_subsidy_sgd", 0)),
        ("Screening outcome", _screening_result_for(evaluation)),
    ])

    story.append(_pdf_heading(theme, "Company profile"))
    _add_detail_table(story, theme, list(profile.items()))

    story.append(_pdf_heading(theme, "Proposal"))
    story.append(Spacer(1, 3 * mm))
    narrative = proposal.get("raw_narrative", "")
    if narrative:
        story.append(_pdf_para(theme, narrative, theme["narrative"]))
    else:
        story.append(_pdf_para(theme, "No proposal narrative was recorded.", theme["small"]))
    other_proposal = [(key, value) for key, value in proposal.items() if key != "raw_narrative"]
    if other_proposal:
        story.append(Spacer(1, 2 * mm))
        _add_detail_table(story, theme, other_proposal)

    story.append(PageBreak())
    _add_ai_section(story, theme, ai_audit)

    did_not_qualify = headline.startswith("Did not qualify")
    reasons = evaluation.get("reasons", [])
    if not reasons and did_not_qualify:
        reasons = ["No detailed reason was recorded in the saved assessment."]
    _add_bullets(story, theme, "Why this result was reached", reasons,
                 color=theme["red"] if did_not_qualify else theme["ink"])
    _add_bullets(story, theme, "Recommended next steps", evaluation.get("recommendations", []))
    _add_bullets(story, theme, "Potentially matched grants", evaluation.get("matched_schemes", []))

    other_evaluation = [
        (key, value) for key, value in evaluation.items()
        if key not in {
            "decision_status", "approved_subsidy_sgd", "audit_passed", "is_sme",
            "reasons", "recommendations", "matched_schemes",
        }
    ]
    if other_evaluation:
        story.append(_pdf_heading(theme, "Additional assessment details"))
        _add_detail_table(story, theme, other_evaluation)


def _make_page_chrome(theme: dict[str, Any], company_name: str) -> Callable[[Any, Any], None]:
    """Returns the function ReportLab calls to draw each page's header bar and footer."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics

    regular_font = theme["regular_font"]

    def draw_page_chrome(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(theme["navy"])
        canvas.rect(0, A4[1] - 5 * mm, A4[0], 5 * mm, fill=1, stroke=0)
        canvas.setStrokeColor(theme["line"])
        canvas.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
        canvas.setFont(regular_font, 8)
        canvas.setFillColor(colors.black)
        footer_company_name = company_name
        footer_text = f"CONFIDENTIAL | Prepared for {footer_company_name}"
        max_footer_width = A4[0] - 50 * mm
        while footer_text and pdfmetrics.stringWidth(footer_text, regular_font, 8) > max_footer_width:
            footer_company_name = footer_company_name[:-4] + "..." if len(footer_company_name) > 4 else "..."
            footer_text = f"CONFIDENTIAL | Prepared for {footer_company_name}"
        canvas.drawString(20 * mm, 10 * mm, footer_text)
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw_page_chrome


def _build_pdf_report(records: Records, pdf_path: str) -> None:
    """Lays out the whole report and writes it to pdf_path."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    theme = _build_report_theme()
    document = SimpleDocTemplate(
        pdf_path, pagesize=A4,
        rightMargin=20 * mm, leftMargin=20 * mm,
        topMargin=14 * mm, bottomMargin=22 * mm,
        title="Company Green Grant Eligibility Assessment",
        author="SME Green Grant Eligibility Auditor",
    )
    story: list[Any] = []
    if not records:
        story.extend([
            Spacer(1, 5 * mm),
            Paragraph("GREEN GRANT ELIGIBILITY ASSESSMENT", theme["title"]),
            Paragraph("Company audit report", theme["subtitle"]),
            _pdf_para(theme, "No audit records were found in the selected JSON file."),
        ])
    for index, record in enumerate(records):
        if index:
            story.append(PageBreak())
        _add_record_pages(story, theme, record, index)

    chrome = _make_page_chrome(theme, _report_company_name(records))
    document.build(story, onFirstPage=chrome, onLaterPages=chrome)


def export_records_to_pdf(records: Records, source_name: str, pdf_filename: str | None = None) -> tuple[str | None, str]:
    """Builds the PDF report for a list of audit records (nested or flat) and
    saves it next to the user's other record files. `source_name` is only used
    to pick the default PDF name and in log messages.

    Returns (pdf_filename, status): "exported", "missing_dependency",
    "invalid_pdf_name" or "pdf_error".
    """
    try:
        import reportlab  # noqa: F401  (checked up front so the status is clear)
        import reportlab.platypus  # noqa: F401
    except ImportError:
        logger.error("PDF export requires ReportLab. Install it with: python -m pip install reportlab")
        return None, "missing_dependency"

    pdf_name = _resolve_pdf_name(source_name, pdf_filename)
    if pdf_name is None:
        return None, "invalid_pdf_name"

    try:
        os.makedirs(_records_dir(), exist_ok=True)
        _build_pdf_report(records, _record_path(pdf_name))
        return pdf_name, "exported"
    except Exception as err:
        logger.exception("Could not export audit records from %s to PDF: %s", source_name, err)
        return None, "pdf_error"



