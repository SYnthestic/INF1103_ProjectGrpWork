"""JsonStore: safe JSON file access inside one data folder: atomic writes,
corrupt files set aside, and a small lock file so two copies of the app sharing a folder cannot overwrite each other's change."""

import json
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from models import FileCipher, FileDecryptionError, PlainFileCipher

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


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
