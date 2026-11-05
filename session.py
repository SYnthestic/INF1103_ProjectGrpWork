"""session.py: the state of one logged-in user, until logout."""

from typing import Any

Record = dict[str, Any]
Records = list[Record]
AiAudit = dict[str, Any]


class Session:
    """What one logged-in user is working on. The Session owns its record
    list and lives only until logout (composition)."""

    def __init__(self, username: str) -> None:
        self.username = username
        self.records: Records = []
        self.ai_audit: AiAudit = {}
        self.jsonfile_name = ""
        self.dirty = False