import json
import logging
import os
import re
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from models import FileCipher, FileDecryptionError, PlainFileCipher, RecordSections
from report_exporter import PdfReportExporter, ReportExporter

Record = dict[str, Any]
Records = list[Record]
AiAudit = dict[str, Any]

# Stay silent unless someone configures logging (otherwise Python's default
# handler would write warnings straight to the terminal).
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class FilenameRules:
    """What counts as a safe save-file or PDF name."""

    INVALID_CHARS = '/\\:*?"<>|'

    @staticmethod
    def normalise(jsonfile_name: str | None) -> str:
        """Strips whitespace and makes sure the name ends with .json
        (any capitalisation of the extension is accepted)."""
        if jsonfile_name is None:
            return ""
        jsonfile_name = str(jsonfile_name).strip()
        if jsonfile_name and not jsonfile_name.lower().endswith(".json"):
            jsonfile_name += ".json"
        return jsonfile_name


    @classmethod
    def is_valid(cls, jsonfile_name: str) -> bool:
        """A bare filename only: no folders, control characters, or empty stem."""
        if any(char in jsonfile_name for char in cls.INVALID_CHARS):
            return False
        if any(ord(char) < 32 for char in jsonfile_name):
            return False
        stem = (
            jsonfile_name[: -len(".json")]
            if jsonfile_name.lower().endswith(".json")
            else jsonfile_name
        )
        # Rejects ".json", "..json", " .json" and similar nameless files.
        return stem.strip(" .") != ""

    @classmethod
    def company_save_filename(cls, company_name: str) -> str:
        """A stable, safe JSON filename for one company. Repeated assessments
        for the same company use the same name; different companies differ."""
        company_name = str(company_name or "Company").strip()
        safe_name = "".join(
            "_" if char in cls.INVALID_CHARS or ord(char) < 32 else char
            for char in company_name
        )
        safe_name = re.sub(r"\s+", " ", safe_name).strip(" .")[:100].rstrip(" .")
        if not safe_name:
            safe_name = "Company"
        return f"audit_{safe_name}.json"

    @classmethod
    def resolve_pdf_name(cls, source_name: str, pdf_filename: str | None) -> str | None:
        """The PDF file name to use, or None when it is not a safe name."""
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
            or any(char in pdf_name for char in cls.INVALID_CHARS)
            or any(ord(char) < 32 for char in pdf_name)
        ):
            return None
        return pdf_name


class JsonStore:
    """Safe JSON file access inside one data folder: atomic writes, corrupt
    files set aside, and a small lock file so two copies of the app sharing a
    folder cannot overwrite each other's change. Files are encrypted/decrypted
    by the cipher passed in (aggregation)."""

    LOCK_TIMEOUT_SECONDS = 5.0
    LOCK_STALE_SECONDS = 30.0

    def __init__(self, data_dir: str, cipher: FileCipher | None = None) -> None:
        self._data_dir = data_dir
        self._cipher = cipher or PlainFileCipher()

    @property
    def cipher(self) -> FileCipher:
        return self._cipher

    @property
    def data_dir(self) -> str:
        return self._data_dir

    @data_dir.setter
    def data_dir(self, value: str) -> None:
        self._data_dir = value

    def full_path(self, filename: str) -> str:
        """Path of a shared file in the data folder (users.json, ...)."""
        return os.path.join(self._data_dir, filename)

    @staticmethod
    def backup_corrupt_file(path: str) -> None:
        """Moves a bad file aside so a later save cannot silently destroy it."""
        try:
            os.replace(path, path + ".corrupt")
        except OSError as err:
            logger.error("Could not back up corrupt file %s: %s", path, err)

    @staticmethod
    def write_bytes(path: str, content: bytes) -> bool:
        """Writes to a temporary file first and then swaps it in, so a crash
        midway can never leave a half-written file behind.
        Returns True on success, False otherwise."""
        tmp_path = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp_path, "wb") as file:
                file.write(content)
            os.replace(tmp_path, path)
            return True
        except OSError as err:
            logger.error("Could not save to %s: %s", path, err)
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            return False

    def write_path(self, path: str, data: Any) -> bool:
        """Saves data as encrypted JSON."""
        try:
            text = json.dumps(data, indent=4, ensure_ascii=False)
        except (TypeError, ValueError, RecursionError) as err:
            logger.error("Could not save to %s: %s", path, err)
            return False
        return self.write_bytes(path, self._cipher.encrypt(text.encode("utf-8")))

    def load_path(self, path: str) -> Any:
        """Reads and decrypts a JSON file. Raises OSError, FileDecryptionError
        or ValueError."""
        with open(path, "rb") as file:
            stored = file.read()
        plaintext = self._cipher.decrypt(stored)
        return json.loads(plaintext.decode("utf-8"))

    def write_json_file(self, filename: str, data: Any) -> bool:
        return self.write_path(self.full_path(filename), data)

    def read_json_file(self, filename: str, default: Any) -> Any:
        """The parsed contents of a data file, or `default` if the file does
        not exist yet. Returns None if the file exists but cannot be read, so
        callers never overwrite data they failed to load. A corrupt file is
        set aside as .corrupt, like the record save files. Files that can't be
        decrypted are left alone, since the key might just be wrong."""
        path = self.full_path(filename)
        if not os.path.isfile(path):
            return default
        try:
            data = self.load_path(path)
        except FileDecryptionError as err:
            logger.error("Could not decrypt %s (%s): %s", path, err.reason, err)
            return None
        except ValueError:  # JSONDecodeError and UnicodeDecodeError
            logger.error("%s contains invalid JSON.", path)
            self.backup_corrupt_file(path)
            return default
        except (OSError, RecursionError) as err:
            logger.error("Could not read %s: %s", path, err)
            return None
        if not isinstance(data, type(default)):
            logger.error("%s does not have the expected format.", path)
            self.backup_corrupt_file(path)
            return default
        return data

    @contextmanager
    def lock(self, filename: str) -> Iterator[bool]:
        """Yields True once this process holds the lock for `filename`, or
        False if it could not be obtained within LOCK_TIMEOUT_SECONDS (the
        caller then reports a failed save instead of risking a lost update).
        A lock older than LOCK_STALE_SECONDS (left by a crashed run) is
        removed."""
        lock_path = self.full_path(filename) + ".lock"
        held = False
        try:
            os.makedirs(self._data_dir, exist_ok=True)
            deadline = time.monotonic() + self.LOCK_TIMEOUT_SECONDS
            while True:
                try:
                    descriptor = os.open(
                        lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                    )
                    os.close(descriptor)
                    held = True
                    break
                except FileExistsError:
                    try:
                        age = time.time() - os.path.getmtime(lock_path)
                        if age > self.LOCK_STALE_SECONDS:
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


class DataManager:
    """Stores and finds records, users and audit history."""

    LOG_FILE = "app.log"
    INVALID_FILENAME_CHARS = FilenameRules.INVALID_CHARS
    # Legacy default filename for callers that still use a shared save file.
    DEFAULT_SAVE_FILE = "audit_records.json"
    USERS_FILE = "users.json"
    AUDIT_HISTORY_FILE = "audit_history.json"
    RULES_CONFIG_FILE = "rules_config.json"
    RECORDS_DIR_NAME = "records"
    ARCHIVE_DIR_NAME = "archive"
    DECRYPTION_STATUSES = {
        "no_key": "encrypted_no_key",
        "not_encrypted": "not_encrypted",
        "damaged": "decrypt_failed",
        "wrong_key": "decrypt_failed",
    }
    RESERVED_FILES = (
        USERS_FILE.lower(),
        AUDIT_HISTORY_FILE.lower(),
        RULES_CONFIG_FILE.lower(),
    )
    # Password fields of a user record. They are replaced on a password reset
    # and never copied into the archive.
    PASSWORD_FIELDS = ("algorithm", "iterations", "salt", "password_hash")
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

    def __init__(
        self,
        data_dir: str | None = None,
        exporter: ReportExporter | None = None,
        cipher: FileCipher | None = None,
    ) -> None:
        # Where save files live. Override with the DATA_DIR environment
        # variable (e.g. a mounted volume when running in Docker).
        if data_dir is None:
            data_dir = os.environ.get("DATA_DIR", ".")
        # cipher comes from LogicManager via main.py (aggregation). None = plain JSON, for tests.
        self._store = JsonStore(data_dir, cipher)  # owned: lives and dies with us
        self._exporter = exporter or PdfReportExporter()
        self._active_user: str | None = None

    @property
    def cipher(self) -> FileCipher:
        return self._store.cipher

    # Folders and the active user
    @property
    def data_dir(self) -> str:
        return self._store.data_dir

    @data_dir.setter
    def data_dir(self, value: str) -> None:
        self._store.data_dir = value

    @staticmethod
    def is_safe_username(username: Any) -> bool:
        return (
            isinstance(username, str)
            and 0 < len(username) <= 64
            and re.fullmatch(r"[a-z0-9_]+", username) is not None
        )

    @property
    def active_user(self) -> str | None:
        return self._active_user

    @active_user.setter
    def active_user(self, username: str | None) -> None:
        """Chooses whose folder the record files are saved to / loaded from.
        None goes back to no active user."""
        if username is not None and not self.is_safe_username(username):
            # Never build a folder name from anything unexpected (e.g. "..").
            raise ValueError("unsafe username")
        self._active_user = username

    def _records_dir(self) -> str:
        if self._active_user is None:
            return self._store.data_dir
        return os.path.join(
            self._store.data_dir, self.RECORDS_DIR_NAME, self._active_user
        )
    
    def _is_reserved(self, name: str) -> bool:
        """Stops a record file from replacing the shared account/history files."""
        return self._active_user is None and name.lower() in self.RESERVED_FILES

    def _record_path(self, jsonfile_name: str) -> str:
        return os.path.join(self._records_dir(), jsonfile_name)

    def get_records_folder(self) -> str:
        """Folder the active user's saved files and PDFs go into (for messages)."""
        return os.path.abspath(self._records_dir())

    # Logging
    def setup_logging(self) -> bool:
        """Sends the app's log messages (AI failures, unreadable files, ...) to
        DATA_DIR/app.log so problems can be looked into afterwards while the app
        carries on. Safe to call more than once. Returns True if logging to the
        file is on; if the file cannot be opened the app simply runs without it."""
        root = logging.getLogger()
        path = os.path.abspath(self._store.full_path(self.LOG_FILE))
        for handler in root.handlers:
            if getattr(handler, "baseFilename", None) == path:
                return True
        try:
            os.makedirs(self._store.data_dir, exist_ok=True)
            handler = logging.FileHandler(path, encoding="utf-8")
        except OSError:
            return False
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(handler)
        root.setLevel(logging.WARNING)
        return True

    # Record helpers
    @staticmethod
    def is_valid_audit_record(record: Any) -> bool:
        """Accept both canonical audit records and the flat IO Manager shape."""
        if not isinstance(record, dict):
            return False

        # Canonical records used by the newer manager architecture.
        if RecordSections.is_nested(record):
            return True

        # Flat, display-oriented records created by the controller.
        return "Company Name" in record and (
            "Proposal Narrative" in record or "Company Total Revenue" in record
        )

    @staticmethod
    def generate_audit_id(records: Any) -> int:
        """The next ID for either nested or flat audit records."""
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

    @staticmethod
    def create_audit_record(
        audit_id: int,
        user_profile: dict[str, Any],
        proposal: dict[str, Any],
        ai_audit: AiAudit,
        evaluation: dict[str, Any],
    ) -> Record:
        """Combine all assessment information into one audit record."""
        return {
            "audit_id": audit_id,
            "created_at": datetime.now().isoformat(),
            "company_profile": user_profile,
            "proposal": {"raw_narrative": proposal},
            "ai_audit": ai_audit,
            "evaluation": evaluation,
        }

    @staticmethod
    def add_audit_record(records: Records, audit_record: Record) -> Records:
        """Add a completed audit record to the current record list."""
        if not isinstance(records, list):
            records = []
        records.append(audit_record)
        return records

    # Loading and saving record files
    def inspect_save_file(self, jsonfile_name: str | None) -> tuple[str, str]:
        """Checks a filename WITHOUT reading the file.

        Returns (clean_name, status) where status is one of:
            "no_name"       nothing was given / user cancelled (clean_name is "")
            "invalid_name"  has illegal characters              (clean_name is "")
            "exists"        a save file is already there
            "not_found"     no such file yet                    (clean_name is still usable)
        """
        if jsonfile_name is None:
            return "", "no_name"
        name = FilenameRules.normalise(jsonfile_name)
        if not name:
            return "", "no_name"
        if not FilenameRules.is_valid(name) or self._is_reserved(name):
            return "", "invalid_name"
        if os.path.isfile(self._record_path(name)):
            return name, "exists"
        return name, "not_found"

    def load_data_from_json(self, jsonfile_name: str) -> tuple[Records, str, str]:
        """Loads records from a JSON save file.

        Returns (data, clean_name, status). data is ALWAYS a list.
        status is one of:
            "loaded"          success
            "no_name"         nothing was given. Thus return to main menu
            "invalid_name"    illegal characters in the name
            "not_found"       file does not exist
            "invalid_json"    file is corrupt/unreadable (set aside as .corrupt)
            "invalid_format"  valid JSON but not a list of audit records (set aside)
            "io_error"        the OS refused to read the file
            "decrypt_failed"  wrong key, or the file was edited/truncated
            "not_encrypted"   plain JSON file while encryption is on
            "encrypted_no_key" encrypted file but no key
        """
        name = FilenameRules.normalise(jsonfile_name)
        if not name:
            return [], "", "no_name"
        if not FilenameRules.is_valid(name) or self._is_reserved(name):
            return [], "", "invalid_name"

        path = self._record_path(name)
        if not os.path.isfile(path):
            return [], name, "not_found"

        try:
            data = self._store.load_path(path)
        except FileDecryptionError as err:
            logger.error("Could not decrypt %s (%s): %s", path, err.reason, err)
            return [], name, self.DECRYPTION_STATUSES.get(err.reason, "decrypt_failed")
        except ValueError:  # JSONDecodeError and UnicodeDecodeError
            logger.error("%s contains invalid JSON.", path)
            self._store.backup_corrupt_file(path)
            return [], name, "invalid_json"
        except (OSError, RecursionError) as err:
            logger.error("Could not read %s: %s", path, err)
            return [], name, "io_error"

        # A single record on its own is treated as a one-item list.
        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list) or not all(
            self.is_valid_audit_record(r) for r in data
        ):
            logger.error("%s is not a list of audit records.", path)
            self._store.backup_corrupt_file(path)
            return [], name, "invalid_format"

        return data, name, "loaded"

    @staticmethod
    def is_data_loaded(data: Records, jsonfile_name: str | None) -> bool:
        """True if there is already data/filename in memory (the controller
        should then ask the user before overwriting it)."""
        return bool(data) or bool(jsonfile_name)

    def save_data_to_json(
        self, data: Records, jsonfile_name: str
    ) -> tuple[str | None, str]:
        """Saves records to a JSON file (written atomically).

        Returns (saved_name_or_None, status) where status is one of:
            "saved", "no_name", "invalid_name", "io_error"
        """
        name = FilenameRules.normalise(jsonfile_name)
        if not name:
            return None, "no_name"
        if not FilenameRules.is_valid(name) or self._is_reserved(name):
            return None, "invalid_name"

        if self._store.write_path(self._record_path(name), data):
            return name, "saved"
        return None, "io_error"


    # User accounts and per-user audit history

    # users.json         -> {username: {password_hash, salt, ...}}
    # audit_history.json -> {username: [audit_record, audit_record, ...]}
    def read_json_file(self, filename: str, default: Any) -> Any:
        return self._store.read_json_file(filename, default)

    def write_json_file(self, filename: str, data: Any) -> bool:
        return self._store.write_json_file(filename, data)

    def load_users(self) -> dict[str, Any] | None:
        """All stored users as {username: record}, or None if unreadable."""
        return self._store.read_json_file(self.USERS_FILE, {})

    def get_user(self, username: str) -> dict[str, Any] | None:
        """The stored user record for `username`, or None."""
        users = self.load_users()
        if users is None:
            return None
        record = users.get(username)
        return record if isinstance(record, dict) else None

    def user_exists(self, username: str) -> bool:
        """True if the username is already in users.json (even if its record
        is damaged, so it can never be silently overwritten)."""
        users = self.load_users()
        return users is not None and username in users

    def save_new_user(self, user_record: dict[str, Any]) -> bool:
        """Adds a new user (built by the Logic Manager). Returns False if the
        username is already taken or the write failed."""
        with self._store.lock(self.USERS_FILE) as locked:
            if not locked:
                return False
            users = self.load_users()
            if users is None:
                return False
            username = user_record["username"]
            if username in users:
                return False

            stored = dict(user_record)
            stored["created_at"] = datetime.now().isoformat(timespec="seconds")
            users[username] = stored
            return self._store.write_json_file(self.USERS_FILE, users)

    def load_audit_history(self) -> dict[str, Any] | None:
        """All saved audits as {username: [audit, ...]}, or None if unreadable."""
        return self._store.read_json_file(self.AUDIT_HISTORY_FILE, {})

    def get_user_audits(self, username: str) -> list[Record]:
        """All audits saved by `username`, oldest first."""
        if not self.is_safe_username(username):
            return []
        history = self.load_audit_history()
        audits = history.get(username, []) if history else []
        if not isinstance(audits, list):
            return []
        # Ignore damaged entries so the screens only ever see audit dicts.
        return [audit for audit in audits if isinstance(audit, dict)]

    def append_user_audit(
        self,
        username: str,
        application: Record,
        ai_audit: AiAudit,
        result: dict[str, Any] | None,
        rules_used: dict[str, Any] | None = None,
    ) -> Record | None:
        """Saves one completed audit (inputs + AI output + decision) under the
        logged-in user. `rules_used` records the thresholds the decision was
        made with, so it can still be explained after they change. Returns the
        saved record, or None on failure."""
        if not self.is_safe_username(username):
            raise ValueError("unsafe username")
        with self._store.lock(self.AUDIT_HISTORY_FILE) as locked:
            if not locked:
                return None
            history = self.load_audit_history()
            if history is None:
                return None
            user_audits = history.get(username)
            if not isinstance(user_audits, list):
                user_audits = []
                history[username] = user_audits

            audit_record = {
                "audit_id": self.generate_audit_id(user_audits),
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "application": application,
                "ai_audit": ai_audit,
                "result": result,
            }
            if rules_used is not None:
                audit_record["rules_used"] = rules_used
            user_audits.append(audit_record)

            if self._store.write_json_file(self.AUDIT_HISTORY_FILE, history):
                return audit_record
            return None

    # Administrator: managing accounts
    def list_users(self) -> list[Record] | None:
        """One summary per account, sorted by name: username, stored role,
        created_at and number of saved audits. Password fields are left out,
        so nothing secret can reach the screen. None if users.json is
        unreadable."""
        users = self.load_users()
        if users is None:
            return None
        history = self.load_audit_history() or {}
        summaries = []
        for username in sorted(users):
            record = users[username] if isinstance(users[username], dict) else {}
            audits = history.get(username)
            summaries.append(
                {
                    "username": username,
                    "role": record.get("role", "user"),
                    "created_at": record.get("created_at", ""),
                    "audit_count": len(audits) if isinstance(audits, list) else 0,
                }
            )
        return summaries

    def _update_user(self, username: str, changes: dict[str, Any]) -> bool:
        """Merges `changes` into one stored user record. False if the user
        does not exist (or has a damaged record) or the write failed."""
        with self._store.lock(self.USERS_FILE) as locked:
            if not locked:
                return False
            users = self.load_users()
            if users is None or not isinstance(users.get(username), dict):
                return False
            users[username] = {**users[username], **changes}
            return self._store.write_json_file(self.USERS_FILE, users)

    def set_user_role(self, username: str, role: str) -> bool:
        return self._update_user(username, {"role": role})

    def set_user_password(self, username: str, password_fields: dict[str, Any]) -> bool:
        """Replaces the stored password hash with one built by the Logic
        Manager. Only the password fields are taken from `password_fields`."""
        changes = {key: password_fields[key] for key in self.PASSWORD_FIELDS}
        changes["password_changed_at"] = datetime.now().isoformat(timespec="seconds")
        return self._update_user(username, changes)

    def _new_archive_dir(self, username: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = os.path.join(
            self._store.data_dir, self.ARCHIVE_DIR_NAME, f"{username}_{stamp}"
        )
        path, counter = base, 1
        while os.path.exists(path):
            counter += 1
            path = f"{base}_{counter}"
        return path

    def archive_user(self, username: str, deleted_by: str) -> tuple[str | None, str]:
        """Deletes an account but keeps its data. Everything belonging to the
        user is moved to DATA_DIR/archive/<username>_<date-time>/:

            account.json         the account details (never the password hash)
            audit_history.json   the user's saved audits
            records/             the user's saved record files and PDFs

        Then the user is removed from users.json and audit_history.json, so
        they can no longer log in. Returns (archive_folder, status), status one
        of "archived", "not_found", "unsafe_name", "busy" or "io_error". On any
        failure the account is left as it was."""
        if not self.is_safe_username(username):
            return None, "unsafe_name"
        with (
            self._store.lock(self.USERS_FILE) as users_locked,
            self._store.lock(self.AUDIT_HISTORY_FILE) as history_locked,
        ):
            if not (users_locked and history_locked):
                return None, "busy"
            users = self.load_users()
            history = self.load_audit_history()
            if users is None or history is None:
                return None, "io_error"
            if username not in users:
                return None, "not_found"

            account = users[username] if isinstance(users[username], dict) else {}
            account = {
                key: value
                for key, value in account.items()
                if key not in self.PASSWORD_FIELDS
            }
            account.update(
                username=username,
                deleted_at=datetime.now().isoformat(timespec="seconds"),
                deleted_by=deleted_by,
            )
            audits = history.get(username, [])

            archive_dir = self._new_archive_dir(username)
            records_dir = os.path.join(
                self._store.data_dir, self.RECORDS_DIR_NAME, username
            )
            archived_records = os.path.join(archive_dir, self.RECORDS_DIR_NAME)
            moved = False
            try:
                if not (
                    self._store.write_path(os.path.join(archive_dir, "account.json"), account)
                    and self._store.write_path(
                        os.path.join(archive_dir, self.AUDIT_HISTORY_FILE), audits
                    )
                ):
                    raise OSError("could not write the archive files")
                if os.path.isdir(records_dir):
                    shutil.move(records_dir, archived_records)
                    moved = True

                history.pop(username, None)
                remaining_users = {k: v for k, v in users.items() if k != username}
                if not self._store.write_json_file(self.AUDIT_HISTORY_FILE, history):
                    raise OSError("could not update audit_history.json")
                if not self._store.write_json_file(self.USERS_FILE, remaining_users):
                    # Put the history back so the account stays complete.
                    history[username] = audits
                    self._store.write_json_file(self.AUDIT_HISTORY_FILE, history)
                    raise OSError("could not update users.json")
            except OSError as err:
                logger.error("Could not archive user %s: %s", username, err)
                if moved:
                    try:
                        shutil.move(archived_records, records_dir)
                    except OSError as undo_err:
                        logger.error("Could not move records back: %s", undo_err)
                return None, "io_error"
            return os.path.abspath(archive_dir), "archived"

    # Administrator: rule thresholds
    def load_rule_config(self) -> tuple[dict[str, Any] | None, str]:
        """The saved rule settings. Returns (values, status), status one of:
            "loaded"      values read from rules_config.json
            "missing"     no settings saved yet (use the defaults)
            "corrupt"     the file was unreadable JSON and was set aside
            "io_error"    the file exists but could not be read
        The values are not checked here; the Logic Manager decides whether
        they make sense."""
        if not os.path.isfile(self._store.full_path(self.RULES_CONFIG_FILE)):
            return None, "missing"
        stored = self._store.read_json_file(self.RULES_CONFIG_FILE, {})
        if stored is None:
            return None, "io_error"
        if not stored:
            return None, "corrupt"
        return stored.get("thresholds"), "loaded"

    def save_rule_config(self, values: dict[str, Any], changed_by: str) -> bool:
        """Saves rule settings already checked by the Logic Manager."""
        stored = {
            "thresholds": dict(values),
            "changed_by": changed_by,
            "changed_at": datetime.now().isoformat(timespec="seconds"),
        }
        with self._store.lock(self.RULES_CONFIG_FILE) as locked:
            if not locked:
                return False
            return self._store.write_json_file(self.RULES_CONFIG_FILE, stored)

    # Encryption
    def _data_files(self) -> list[str]:
        """Shared files + records/ + archive/ (no logs or PDFs)."""
        root = self._store.data_dir
        files = [
            self._store.full_path(name)
            for name in self.RESERVED_FILES
            if os.path.isfile(self._store.full_path(name))
        ]
        for folder in (self.RECORDS_DIR_NAME, self.ARCHIVE_DIR_NAME):
            for dirpath, _dirnames, filenames in os.walk(os.path.join(root, folder)):
                files.extend(
                    os.path.join(dirpath, name)
                    for name in sorted(filenames)
                    if name.lower().endswith(".json")
                )
        return files

    def check_shared_files(self) -> list[tuple[str, str]]:
        """Checked at start-up. Returns (filename, reason) for each shared file
        that can't be decrypted; empty list if all OK."""
        problems = []
        for name in self.RESERVED_FILES:
            path = self._store.full_path(name)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "rb") as file:
                    self._store.cipher.decrypt(file.read())
            except FileDecryptionError as err:
                problems.append((name, err.reason))
            except OSError:
                problems.append((name, "io_error"))
        return problems

    def encrypt_existing_files(self) -> dict[str, list[str]]:
        """Encrypts old plain JSON files once (--encrypt-existing-data).
        Returns file paths grouped by: encrypted, already, unreadable,
        invalid, failed. Only plain valid JSON files are changed."""
        result: dict[str, list[str]] = {
            "encrypted": [], "already": [], "unreadable": [], "invalid": [], "failed": [],
        }
        cipher = self._store.cipher
        if not cipher.encrypts:
            raise ValueError("No encryption key is in use, so nothing can be encrypted.")
        for path in self._data_files():
            shown = os.path.relpath(path, self._store.data_dir)
            try:
                with open(path, "rb") as file:
                    stored = file.read()
            except OSError as err:
                logger.error("Could not read %s: %s", path, err)
                result["failed"].append(shown)
                continue
            if cipher.is_encrypted(stored):
                try:
                    cipher.decrypt(stored)
                    result["already"].append(shown)
                except FileDecryptionError:
                    result["unreadable"].append(shown)
                continue
            try:
                json.loads(stored.decode("utf-8"))
            except (ValueError, RecursionError):
                result["invalid"].append(shown)
                continue
            if self._store.write_bytes(path, cipher.encrypt(stored)):
                result["encrypted"].append(shown)
            else:
                result["failed"].append(shown)
        return result

    # Filtering / querying
    @staticmethod
    def filter_by_decision_status(records: Records, decision_status: str) -> Records:
        """Records whose evaluation decision_status matches exactly."""
        return [
            r
            for r in records
            if RecordSections.get(r, "evaluation").get("decision_status")
            == decision_status
        ]

    @staticmethod
    def filter_approved_records(records: Records) -> Records:
        """Records where the audit passed."""
        return [
            r
            for r in records
            if RecordSections.get(r, "evaluation").get("audit_passed") is True
        ]

    @staticmethod
    def find_records_by_company(records: Records, company_name: str) -> Records:
        """Case-insensitive exact match on company name."""
        wanted = str(company_name).strip().lower()
        return [
            r
            for r in records
            if str(RecordSections.get(r, "company_profile").get("company_name", ""))
            .strip()
            .lower()
            == wanted
        ]

    @staticmethod
    def available_decision_statuses(records: Records) -> list[str]:
        """Sorted distinct decision statuses present in the records (lets the
        I/O Manager offer only filters that can match something)."""
        statuses = {
            RecordSections.get(r, "evaluation").get("decision_status") for r in records
        }
        return sorted(s for s in statuses if isinstance(s, str) and s)

    @staticmethod
    def merge_records(existing: Records, new_records: Records) -> Records:
        """Existing records first, then any new ones not already present."""
        return existing + [r for r in new_records if r not in existing]

    # Editing and deleting records in memory (menu options 5 and 6)
    @staticmethod
    def _valid_index(records: Any, index: Any) -> bool:
        return (
            isinstance(records, list)
            and isinstance(index, int)
            and not isinstance(index, bool)
            and 0 <= index < len(records)
        )

    def update_record_field(
        self, records: Records, index: int, field: str, value: Any
    ) -> tuple[Records, str]:
        """Returns (new_records, status). status is "updated", "bad_index",
        "bad_field" or "not_editable" (the record is not in the display layout)."""
        if not self._valid_index(records, index):
            return records, "bad_index"
        if field not in self.EDITABLE_RECORD_FIELDS:
            return records, "bad_field"
        if not isinstance(records[index], dict) or "Company Name" not in records[index]:
            return records, "not_editable"

        changed = dict(records[index])
        changed[field] = value
        return records[:index] + [changed] + records[index + 1 :], "updated"

    def delete_record(self, records: Records, index: int) -> tuple[Records, str]:
        """Returns (new_records, status). status is "deleted" or "bad_index"."""
        if not self._valid_index(records, index):
            return records, "bad_index"
        return records[:index] + records[index + 1 :], "deleted"

    # Filtering the audit history (For option 9)
    @staticmethod
    def audit_decision_status(audit: Any) -> str:
        """The decision status stored in one history entry, or "" if missing."""
        status = RecordSections.get(audit, "result").get("decision_status")
        return status if isinstance(status, str) else ""

    @classmethod
    def available_audit_statuses(cls, audits: list[Record]) -> list[str]:
        """Sorted distinct decision statuses in the history (so the I/O Manager
        only offers filters that can match something)."""
        return sorted({cls.audit_decision_status(audit) for audit in audits} - {""})

    @classmethod
    def filter_audits_by_status(
        cls, audits: list[Record], decision_status: str
    ) -> list[Record]:
        """History entries whose decision status matches exactly."""
        return [
            audit
            for audit in audits
            if cls.audit_decision_status(audit) == decision_status
        ]

    @staticmethod
    def search_audits_by_company(audits: list[Record], text: str) -> list[Record]:
        """History entries whose company name contains `text` (ignoring case)."""
        wanted = str(text).strip().lower()
        return [
            audit
            for audit in audits
            if wanted
            in str(RecordSections.get(audit, "application").get("Company Name", "")).lower()
        ]
    
    # PDF export function (delegates the drawing to the ReportExporter)
    @staticmethod
    def audit_to_report_record(audit: Record) -> Record:
        """Turns one audit-history entry into the flat record layout the PDF
        report already understands: the application's own keys plus the AI
        result and the grant decision."""
        report = dict(RecordSections.get(audit, "application"))
        report["AI Audit"] = RecordSections.get(audit, "ai_audit")
        report["Grant Decision"] = RecordSections.get(audit, "result")
        report["Audit ID"] = audit.get("audit_id", 1) if isinstance(audit, dict) else 1
        report["Created At"] = (
            audit.get("timestamp", "") if isinstance(audit, dict) else ""
        )
        return report

    @staticmethod
    def audit_pdf_filename(audit: Record) -> str:
        """A safe default PDF name such as 'audit_3_Apex Haulage.pdf'."""
        company = RecordSections.get(audit, "application").get("Company Name", "")
        safe_company = FilenameRules.company_save_filename(company)[
            len("audit_") : -len(".json")
        ]
        audit_id = audit.get("audit_id", "") if isinstance(audit, dict) else ""
        return f"audit_{audit_id}_{safe_company}.pdf"

    def export_audit_to_pdf(self, audit: Record) -> tuple[str | None, str]:
        """Writes the PDF report for one history entry into the user's records
        folder. Returns (pdf_filename, status), as export_records_to_pdf does."""
        if not isinstance(audit, dict) or not audit:
            return None, "pdf_error"
        return self.export_records_to_pdf(
            [self.audit_to_report_record(audit)], "audit", self.audit_pdf_filename(audit)
        )

    def export_json_to_pdf(
        self, jsonfile_name: str, pdf_filename: str | None = None
    ) -> tuple[str | None, str]:
        """Creates a company-facing assessment report from a saved JSON file,
        including every audit record in it."""
        records, clean_json_name, load_status = self.load_data_from_json(jsonfile_name)
        if load_status != "loaded":
            return None, load_status
        return self.export_records_to_pdf(records, clean_json_name, pdf_filename)

    def export_records_to_pdf(
        self, records: Records, source_name: str, pdf_filename: str | None = None
    ) -> tuple[str | None, str]:
        """Builds the PDF report for a list of audit records (nested or flat)
        and saves it next to the user's other record files. `source_name` is
        only used to pick the default PDF name and in log messages.

        Returns (pdf_filename, status): "exported", "missing_dependency",
        "invalid_pdf_name" or "pdf_error"."""
        if not self._exporter.is_available():
            logger.error(
                "PDF export requires ReportLab. Install it with: python -m pip install reportlab"
            )
            return None, "missing_dependency"

        pdf_name = FilenameRules.resolve_pdf_name(source_name, pdf_filename)
        if pdf_name is None:
            return None, "invalid_pdf_name"

        try:
            os.makedirs(self._records_dir(), exist_ok=True)
            self._exporter.export(records, self._record_path(pdf_name))
            return pdf_name, "exported"
        except Exception as err:
            logger.exception(
                "Could not export audit records from %s to PDF: %s", source_name, err
            )
            return None, "pdf_error"