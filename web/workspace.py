import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Workspace:
    """One user's records in memory (the web version of the CLI Session)."""

    records: list[dict[str, Any]] = field(default_factory=list)
    jsonfile_name: str = ""
    ai_audit: dict[str, Any] = field(default_factory=dict)
    dirty: bool = False


class Workspaces:
    def __init__(self) -> None:
        self._items: dict[str, Workspace] = {}
        self._lock = threading.Lock()

    def get(self, username: str) -> Workspace:
        with self._lock:
            return self._items.setdefault(username, Workspace())

    def discard(self, username: str) -> None:
        with self._lock:
            self._items.pop(username, None)