"""Workspaces."""

import threading

from .workspace import Workspace


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
