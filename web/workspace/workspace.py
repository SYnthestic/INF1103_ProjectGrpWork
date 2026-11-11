"""Workspace: one user's records in memory (the web version of the CLI
Session)."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Workspace:
    """One user's records in memory (the web version of the CLI Session)."""

    records: list[dict[str, Any]] = field(default_factory=list)
    jsonfile_name: str = ""
    ai_audit: dict[str, Any] = field(default_factory=dict)
    dirty: bool = False
