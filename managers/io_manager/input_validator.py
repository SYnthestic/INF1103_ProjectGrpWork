"""InputValidator: checks on typed values."""

import math
from typing import Any


class InputValidator:
    """Checks on typed values. Nothing here prints or reads input."""

    USERNAME_MIN_LEN = 3
    USERNAME_MAX_LEN = 20
    PASSWORD_MIN_LEN = 8
    PASSWORD_MAX_LEN = 64

    @classmethod
    def is_valid_username(cls, username: Any) -> bool:
        """3-20 characters: letters, digits and underscores only."""
        return (
            cls.USERNAME_MIN_LEN <= len(username) <= cls.USERNAME_MAX_LEN
            and username.isascii()
            and username.replace("_", "").isalnum()
        )

    @classmethod
    def password_problems(cls, password: str) -> list[str]:
        """The rules the password breaks (empty if it's fine)."""
        problems = []
        if len(password) < cls.PASSWORD_MIN_LEN:
            problems.append(f"be at least {cls.PASSWORD_MIN_LEN} characters long")
        if len(password) > cls.PASSWORD_MAX_LEN:
            problems.append(f"be at most {cls.PASSWORD_MAX_LEN} characters long")
        if not any(ch.isalpha() for ch in password):
            problems.append("contain at least one letter")
        if not any(ch.isdigit() for ch in password):
            problems.append("contain at least one digit")
        if password != password.strip():
            problems.append("not start or end with a space")
        return problems

    @staticmethod
    def finite_float(text: Any) -> float:
        """Like float(), but also rejects "nan" and "inf", which float()
        accepts and which slip past <= / >= range checks. Raises ValueError
        like float()."""
        number = float(text)
        if not math.isfinite(number):
            raise ValueError("number must be finite")
        return number
