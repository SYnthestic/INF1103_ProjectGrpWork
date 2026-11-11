"""PasswordHasher: passwords are never stored."""

import hashlib
import hmac
import secrets
from typing import Any


class PasswordHasher:
    """Passwords are never stored. Instead we store a random 16-byte salt per
    user plus the PBKDF2-HMAC-SHA256 hash of salt + password, repeated
    `iterations` times so brute-forcing is slow. Comparison is constant time
    (hmac.compare_digest) so timing does not leak the hash."""

    ALGORITHM = "pbkdf2_sha256"
    DEFAULT_ITERATIONS = 200_000
    SALT_BYTES = 16
    # Upper limits used when checking a login, so a hand-edited or damaged
    # users.json (or an absurdly long password) cannot hang or crash the app.
    MAX_PASSWORD_CHARS_CHECKED = 256
    MAX_STORED_ITERATIONS = 5_000_000

    def __init__(self, iterations: int = DEFAULT_ITERATIONS) -> None:
        self._iterations = iterations

    def hash_password(
        self,
        password: str,
        salt_hex: str | None = None,
        iterations: int | None = None,
    ) -> dict[str, Any]:
        """Hashes a password. A fresh random salt is made for a new account;
        a stored salt is reused when checking a login.

        Returns: algorithm, iterations, salt (hex), password_hash (hex)."""
        if salt_hex is None:
            salt_hex = secrets.token_hex(self.SALT_BYTES)
        if iterations is None:
            iterations = self._iterations

        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations
        )
        return {
            "algorithm": self.ALGORITHM,
            "iterations": iterations,
            "salt": salt_hex,
            "password_hash": digest.hex(),
        }
    def build_new_user_record(self, username: str, password: str) -> dict[str, Any]:
        """The record the Data Manager stores for a new account."""
        record: dict[str, Any] = {"username": username}
        record.update(self.hash_password(password))
        return record

    def verify_password(self, password: Any, user_record: Any) -> bool:
        """Checks a login attempt against a stored user record.

        user_record may be None (unknown username). A hash is still computed
        in that case so a wrong username takes as long as a wrong password.
        A damaged record simply fails the login instead of crashing."""
        if (
            not isinstance(password, str)
            or len(password) > self.MAX_PASSWORD_CHARS_CHECKED
        ):
            return False

        if not isinstance(user_record, dict):
            self.hash_password(password)  # dummy work to equalise timing
            return False

        salt = user_record.get("salt")
        stored_hash = user_record.get("password_hash")
        iterations = user_record.get("iterations", self.DEFAULT_ITERATIONS)

        if (
            not isinstance(salt, str)
            or not isinstance(stored_hash, str)
            or isinstance(iterations, bool)
            or not isinstance(iterations, int)
            or not 0 < iterations <= self.MAX_STORED_ITERATIONS
        ):
            return False

        try:
            attempt = self.hash_password(password, salt_hex=salt, iterations=iterations)
            return hmac.compare_digest(
                attempt["password_hash"].encode("ascii"), stored_hash.encode("ascii")
            )
        except (ValueError, TypeError, UnicodeError):
            return False
