"""AccessPolicy: who is an administrator, and which account changes are
allowed."""

from typing import Any


class AccessPolicy:
    """Who is an administrator, and which account changes are allowed.

    A user is an admin if their stored record says role "admin", or if they
    are the bootstrap admin named by the ADMIN_USERNAME setting. The bootstrap
    admin can never be demoted or deleted, so the app always has an admin.
    Admins may not demote or delete their own account either (another admin
    has to), which stops anyone locking themselves out by accident."""

    ADMIN = "admin"
    USER = "user"
    ROLES = (USER, ADMIN)

    def __init__(self, bootstrap_admin: str | None = None) -> None:
        name = (bootstrap_admin or "").strip().lower()
        self._bootstrap_admin = name or None

    @property
    def bootstrap_admin(self) -> str | None:
        return self._bootstrap_admin

    def role_of(self, username: str, user_record: Any) -> str:
        if username and username == self._bootstrap_admin:
            return self.ADMIN
        if isinstance(user_record, dict) and user_record.get("role") == self.ADMIN:
            return self.ADMIN
        return self.USER

    def is_admin(self, username: str, user_record: Any) -> bool:
        return self.role_of(username, user_record) == self.ADMIN

    def role_change_problem(self, actor: str, target: str, new_role: str) -> str | None:
        """Why `actor` may not give `target` the role `new_role`, or None if
        the change is allowed."""
        if new_role not in self.ROLES:
            return f"Unknown role '{new_role}'."
        if new_role == self.USER and target == self._bootstrap_admin:
            return f"'{target}' is the main administrator (ADMIN_USERNAME) and stays an admin."
        if new_role == self.USER and target == actor:
            return "You cannot remove your own admin rights. Ask another admin."
        return None

    def deletion_problem(self, actor: str, target: str) -> str | None:
        """Why `actor` may not delete `target`, or None if it is allowed."""
        if target == actor:
            return "You cannot delete your own account while logged in to it."
        if target == self._bootstrap_admin:
            return f"'{target}' is the main administrator (ADMIN_USERNAME) and cannot be deleted."
        return None
