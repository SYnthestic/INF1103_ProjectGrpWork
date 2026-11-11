"""I/O Manager: every screen, prompt and keypress of the app. It is the only
module that prints or asks for input, and it decides nothing about grants.

Class overview
    Terminal         raw keyboard/mouse handling for Windows and Unix
    InputValidator   pure checks on typed values (no printing)
    PaperPrinter     the "report on paper" text frames
    IOManager        all prompts and displays; owns a Terminal, a ButtonPanel
                     and a PaperPrinter (composition)
"""

from .constants import (
    Record,
    Records,
    AiAudit,
    IS_WINDOWS,
)
from .terminal import Terminal
from .input_validator import InputValidator
from .paper_printer import PaperPrinter
from .io_manager import IOManager

__all__ = [
    "Records",
    "IS_WINDOWS",
    "AiAudit",
    "Record",
    "Terminal",
    "InputValidator",
    "PaperPrinter",
    "IOManager",
]
