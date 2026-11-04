"""Screen art for the terminal: buttons.

    ButtonPanel    shows the clickable buttons by handing their art to a
                   terminal object it is given (association; the old circular
                   import of io_manager is gone)

The I/O Manager is the only caller; it owns the printing.
"""

import re
import textwrap

from art import art as art_lookup
from art import text2art

ANSI = re.compile(r"\033\[[0-9;]*m")

BLUE = "\033[34m"
LABEL = "\033[30;107m"  # black text on a bright white label
RESET = "\033[0m"
BUTTON_BOUNDS = (5, 35)
class ButtonPanel:
    """The clickable buttons. Each one builds its art and hands it to the
    terminal, which shows it and waits for Enter or a click."""

    def __init__(self, terminal) -> None:
        self._terminal = terminal

    def _show(self, art: str) -> None:
        self._terminal.execute_button_interaction(
            art, min_x=BUTTON_BOUNDS[0], max_x=BUTTON_BOUNDS[1]
        )

    def continue_button(self) -> None:
        gold = "\033[93m"
        shadow = "\033[90m"
        reset = "\033[0m"

        art = f"""
     ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
    █  {gold}┌──────────────────────────┐{reset}  █
    █  {gold}│⮞ PRESS ENTER TO CONTINUE │{reset}  █▀▄
    █  {gold}└──────────────────────────┘{reset}  █ █
    ▀████████████████████████████████▀  █
      {shadow}▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀{reset}
    """
        self._show(art)

    def return_button(self) -> None:
        cyan = "\033[96m"
        shadow = "\033[90m"
        reset = "\033[0m"

        art = f"""
     ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
    █  {cyan}┌──────────────────────────┐{reset}  █
    █  {cyan}│ ⮪  CLICK OR ENTER RETURN │{reset}  █▀▄
    █  {cyan}└──────────────────────────┘{reset}  █ █
    ▀████████████████████████████████▀  █
      {shadow}▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀{reset}
    """
        self._show(art)

    def ai_button(self) -> None:
        """The button that starts the AI analysis (menu option 1), so users
        know the AI Manager is about to run."""
        green = "\033[92m"
        shadow = "\033[90m"
        reset = "\033[0m"

        label = "⮞ START AI ANALYSIS"

        art = f"""
     ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
    █  {green}┌──────────────────────────┐{reset}  █
    █  {green}│{label:<26}│{reset}  █▀▄
    █  {green}└──────────────────────────┘{reset}  █ █
    ▀████████████████████████████████▀  █
      {shadow}▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀{reset}
    """
        self._show(art)
