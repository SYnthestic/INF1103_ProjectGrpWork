"""AdminService: the administrator's account and threshold changes for the
web pages, with the same rules as the terminal admin console."""

from typing import Any

from .account_rules import AccountRules
from .application_validator import ApplicationValidator


class AdminService:
    """Every admin action returns (ok, message). The Logic Manager decides
    what is allowed (AccessPolicy, RuleConfig) and the Data Manager stores
    it; this class only connects them, like the terminal's admin flows."""

    def __init__(self, logic: Any, data: Any, actor: str) -> None:
        self._logic = logic
        self._data = data
        self._actor = actor
        self._accounts = AccountRules()

    # ----- who is an admin -----
    def is_admin(self, username: str | None) -> bool:
        if not username:
            return False
        return self._logic.is_admin(username, self._data.get_user(username))

    def users(self) -> list[dict[str, Any]] | None:
        """Account summaries (never the password hash) with each user's
        effective role, or None if users.json cannot be read."""
        users = self._data.list_users()
        if users is None:
            return None
        for user in users:
            user["role"] = self._logic.access.role_of(user["username"], user)
            user["is_you"] = user["username"] == self._actor
        return users

    # ----- accounts -----
    def create_user(self, username: Any, password: Any, role: Any) -> tuple[bool, str]:
        username = self._accounts.clean_username(username)
        problem = self._accounts.problem(username, password)
        if problem:
            return False, problem
        if role not in self._logic.access.ROLES:
            return False, "Choose a role: user or admin."
        if self._accounts.is_taken(self._data, self._logic, username):
            return False, f"The username '{username}' is already taken."
        record = self._logic.build_new_user_record(username, password, role=role)
        if not self._data.save_new_user(record):
            return False, "Could not save the new account. Please try again."
        return True, f"Account '{username}' created as {role}."

    def reset_password(self, username: str, password: Any) -> tuple[bool, str]:
        if self._data.get_user(username) is None:
            return False, f"There is no account called '{username}'."
        problem = self._accounts.problem(username, password)
        if problem:
            return False, problem
        if not self._data.set_user_password(username, self._logic.hash_password(password)):
            return False, f"The password for '{username}' was not changed."
        return True, f"Password for '{username}' changed."

    def change_role(self, username: str, role: Any) -> tuple[bool, str]:
        if self._data.get_user(username) is None:
            return False, f"There is no account called '{username}'."
        problem = self._logic.access.role_change_problem(self._actor, username, role)
        if problem:
            return False, problem
        if not self._data.set_user_role(username, role):
            return False, f"The role of '{username}' was not changed."
        return True, f"'{username}' is now {role}."

    def delete_user(self, username: str, typed_confirmation: Any) -> tuple[bool, str]:
        problem = self._logic.access.deletion_problem(self._actor, username)
        if problem:
            return False, problem
        if str(typed_confirmation or "").strip().lower() != username:
            return False, f"Type '{username}' exactly to confirm. Nothing was deleted."
        folder, status = self._data.archive_user(username, deleted_by=self._actor)
        if status == "archived":
            return True, f"'{username}' was deleted. Their data was archived in {folder}"
        reasons = {
            "not_found": "that account no longer exists",
            "busy": "the files are in use, please try again",
            "unsafe_name": "the stored username cannot be used as a folder name",
        }
        reason = reasons.get(status, "the files could not be written")
        return False, f"'{username}' was not deleted ({reason})."

    # ----- grant rule thresholds -----
    def threshold_rows(self) -> list[tuple[str, str, float, str]]:
        """(setting name, label, current value, unit) for each threshold."""
        config = self._logic.rule_config
        return [
            (name, label, getattr(config, name), unit)
            for name, (label, unit) in config.LABELS.items()
        ]

    def save_thresholds(self, form: Any) -> tuple[bool, str | list[str]]:
        """Checks every value with the Logic Manager before anything is
        saved; returns (False, problems) if any are invalid."""
        values: dict[str, Any] = {}
        for name, label, _, _ in self.threshold_rows():
            number = ApplicationValidator.form_number(form.get(name, ""))
            if number is None:
                return False, [f"{label}: must be a number."]
            values[name] = number
        problems = self._logic.rule_config_problems(values)
        if problems:
            return False, problems
        return self._apply(self._logic.rule_config_from_dict(values))

    def reset_thresholds(self) -> tuple[bool, str]:
        return self._apply(self._logic.default_rule_config())

    def _apply(self, config: Any) -> tuple[bool, str]:
        if not self._data.save_rule_config(config.to_dict(), changed_by=self._actor):
            return False, "The thresholds could not be saved, so nothing changed."
        self._logic.use_rule_config(config)
        return True, "Saved. New decisions use these thresholds."
