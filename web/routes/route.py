"""Route."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Route:
    rule: str
    view: Callable[..., Any]
    methods: tuple[str, ...] = ("GET",)
    login: bool = False

    @property
    def endpoint(self) -> str:
        return self.view.__name__
