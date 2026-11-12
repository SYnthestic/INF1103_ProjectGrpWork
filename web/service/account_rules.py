"""AccountRules: the terminal app's account rules (InputValidator), so an
account made on the web works in the terminal and the other way round."""

from typing import Any

from managers.io_manager import InputValidator


class AccountRules:
    """The terminal app's account rules (InputValidator), so an account made
    on the web works in the terminal and the other way round."""

    def __init__(self, validator: type[InputValidator] = InputValidator) -> None:
        self._validator = validator

    @staticmethod
    def clean_username(value: Any) -> str:
        """Usernames are not case-sensitive, as in the terminal app."""
        return value.strip().lower() if isinstance(value, str) else ""

    def problem(self, username: Any, password: Any) -> str | None:
        """Why a new account cannot be created with these details, or None."""
        if not isinstance(username, str) or not isinstance(password, str):
            return "Username and password must be text."
        if not username or not password:
            return "Username and password are required."
        if not self._validator.is_valid_username(username):
            return (
                f"Username must be {self._validator.USERNAME_MIN_LEN}-"
                f"{self._validator.USERNAME_MAX_LEN} characters: letters, digits or _."
            )
        problems = self._validator.password_problems(password)
        if problems:
            return "Password must " + ", ".join(problems) + "."
        return None

    @staticmethod
    def is_taken(data: Any, logic: Any, username: str) -> bool:
        """Taken by an account, or reserved for the ADMIN_USERNAME
        administrator (so the web cannot be used to claim the admin name)."""
        return data.user_exists(username) or username == logic.access.bootstrap_admin
