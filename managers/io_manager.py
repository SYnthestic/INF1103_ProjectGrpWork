"""I/O Manager: every screen, prompt and keypress of the app. It is the only
module that prints or asks for input, and it decides nothing about grants.

Class overview
    Terminal         raw keyboard/mouse handling for Windows and Unix
    InputValidator   pure checks on typed values (no printing)
    PaperPrinter     the "report on paper" text frames
    IOManager        all prompts and displays; owns a Terminal, a ButtonPanel
                     and a PaperPrinter (composition)
"""

import codecs
import getpass
import math
import os
import sys
import textwrap
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from models import ApplicationRecord
from sme_interface_stores.sme_interface_gui import InterfaceArt
from sme_interface_stores.buttons import ButtonPanel

Record = dict[str, Any]
Records = list[Record]
AiAudit = dict[str, Any]

IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    import ctypes
    import msvcrt
    from ctypes import wintypes
else:
    import select
    import termios
    import tty


# ========================================================
# Terminal: keyboard and mouse
# ========================================================
class Terminal:
    """Low-level terminal access: raw keys, mouse clicks and length-limited
    line reading. One instance per program."""

    STD_INPUT_HANDLE = -10
    ENABLE_MOUSE_INPUT = 0x0010
    ENABLE_EXTENDED_FLAGS = 0x0080

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")("ignore")
        if IS_WINDOWS:
            self._kernel32 = ctypes.windll.kernel32
            self._saved_console_mode = wintypes.DWORD()

    # ----- raw bytes -----
    def _getb(self) -> bytes:
        """Read one raw byte (blocks, no CPU spinning)."""
        if IS_WINDOWS:
            return msvcrt.getch()
        return os.read(sys.stdin.fileno(), 1)

    def _pending(self, timeout: float = 0.02) -> bool:
        """Is another byte already waiting?"""
        if IS_WINDOWS:
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                if msvcrt.kbhit():
                    return True
                time.sleep(0.002)
            return False
        return bool(select.select([sys.stdin.fileno()], [], [], timeout)[0])

    @contextmanager
    def raw_input(self) -> Iterator[None]:
        """Raw terminal mode on Unix, set once and restored after. No-op on Windows."""
        if IS_WINDOWS:
            yield
            return
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            yield
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    # ----- mouse tracking -----
    def enable_mouse_tracking(self) -> None:
        sys.stdout.write("\033[?1000h\033[?25l")  # mouse on, hide cursor
        sys.stdout.flush()
        if IS_WINDOWS:
            handle = self._kernel32.GetStdHandle(self.STD_INPUT_HANDLE)
            self._kernel32.GetConsoleMode(handle, ctypes.byref(self._saved_console_mode))
            mode = self._saved_console_mode.value
            self._kernel32.SetConsoleMode(
                handle, (mode & ~self.ENABLE_EXTENDED_FLAGS) | self.ENABLE_MOUSE_INPUT
            )

    def disable_mouse_tracking(self) -> None:
        sys.stdout.write("\033[?1000l\033[?25h\n")  # mouse off, show cursor
        sys.stdout.flush()
        if IS_WINDOWS:
            handle = self._kernel32.GetStdHandle(self.STD_INPUT_HANDLE)
            self._kernel32.SetConsoleMode(handle, self._saved_console_mode.value)

    # ----- one event reader shared by every button/choice prompt -----
    def _read_event(self) -> tuple[str, Any] | None:
        """Return ("key", char), ("click", column), or None for anything ignorable."""
        b = self._getb()

        if IS_WINDOWS and b in (b"\x00", b"\xe0"):  # arrow/function key: skip 2nd byte
            self._getb()
            return None

        if b != b"\x1b":
            return ("key", b.decode("utf-8", "ignore"))

        # ESC: either a lone Esc press or the start of an escape sequence
        if not self._pending() or self._getb() != b"[":
            return None
        if not self._pending() or self._getb() != b"M":  # some other sequence
            return None

        # Mouse report: ESC [ M <button> <x> <y>
        btn, x, _y = self._getb(), self._getb(), self._getb()
        if btn[0] - 32 == 0:  # left button press
            return ("click", x[0] - 32)
        return None

    def wait_for_choice(
        self, art: str, regions: dict[Any, tuple[int, int]], keys: dict[str, Any]
    ) -> Any:
        """Show `art`, then wait for a mapped key or a left click inside a region.

        regions: {value: (min_x, max_x)}    keys: {"y": value, "\\r": value, ...}
        Returns the matching value.
        """
        print(art, end="", flush=True)
        self.enable_mouse_tracking()
        try:
            with self.raw_input():
                while True:
                    event = self._read_event()
                    if event is None:
                        continue
                    kind, val = event
                    if kind == "key":
                        if val == "\x03":
                            raise KeyboardInterrupt
                        if val.lower() in keys:
                            return keys[val.lower()]
                    else:
                        for value, (lo, hi) in regions.items():
                            if lo <= val <= hi:
                                return value
        finally:
            self.disable_mouse_tracking()

    def execute_button_interaction(
        self, button_art: str, min_x: int = 5, max_x: int = 35
    ) -> None:
        self.wait_for_choice(
            button_art, {True: (min_x, max_x)}, {"\r": True, "\n": True}
        )

    def execute_choice_interaction(
        self, art: str, regions: dict[Any, tuple[int, int]], keys: dict[str, Any]
    ) -> Any:
        return self.wait_for_choice(art, regions, keys)

    # ----- text input: length-limited line reader -----
    def _read_key(self) -> str:
        """Read one character without waiting for Enter."""
        if IS_WINDOWS:
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                msvcrt.getwch()
                return ""
            return ch
        while True:  # assemble multi-byte UTF-8 characters
            s = self._decoder.decode(self._getb())
            if s:
                return s

    def read_limited(self, max_len: int, blocked: str = "") -> str:
        """Read a line, silently ignoring keys once max_len characters are typed."""
        buf: list[str] = []
        with self.raw_input():  # set once, not per keystroke
            while True:
                ch = self._read_key()

                if ch in ("\r", "\n"):
                    break
                if ch == "\x03":
                    raise KeyboardInterrupt
                if ch in ("\x08", "\x7f"):
                    if buf:
                        buf.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                    continue
                if not ch or not ch.isprintable() or ch in blocked:
                    continue
                if len(buf) >= max_len:
                    continue

                buf.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()

        return "".join(buf)


# ========================================================
# Pure input checks
# ========================================================
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


# ========================================================
# Paper-style text frames
# ========================================================
class PaperPrinter:
    """Prints text inside a frame so it looks a bit like reading your work on
    paper while also looking at a command console."""

    WIDTH = 110

    def __init__(self, width: int = WIDTH) -> None:
        self._width = width

    def print_on_paper(
        self,
        lines: list[str],
        title: str = "REPORT",
        footer: str = "End of report",
        width: int | None = None,
    ) -> None:
        """Print a list of text lines inside a paper-style frame."""
        width = width or self._width
        inner = width - 4  # usable space between "| " and " |"

        def row(text: str = "") -> None:
            print(f"| {text:<{inner}} |")

        print()
        print("+" + "-" * (width - 2) + "+")
        row(title.center(inner))
        row("=" * inner)
        row()

        for text in lines:
            stripped = text.lstrip()
            indent = " " * (len(text) - len(stripped))
            # Bullets get a hanging indent so wrapped lines align under the text
            if stripped.startswith("- "):
                indent += "  "
            wrapped = textwrap.wrap(text, width=inner, subsequent_indent=indent) or [""]
            for piece in wrapped:
                row(piece)

        row()
        row("-" * inner)
        row(footer.center(inner))
        row()
        print(("\\/" * width)[:width])  # torn paper edge

    def format_pairs(
        self, data: Any, width: int | None = None, indent: str = ""
    ) -> list[str]:
        """Turn a dict into aligned 'key : value' lines with a hanging indent."""
        width = width or self._width
        inner = width - 4 - len(indent)
        if not data:
            return ["(no data)"]
        key_w = max((len(str(k)) for k in data), default=0)
        lines = []
        for key, value in data.items():
            label = f"{str(key):<{key_w}} : "
            hang = " " * len(label)
            wrapped = textwrap.wrap(str(value), width=inner - len(label)) or [""]
            lines.append(indent + label + wrapped[0])
            lines.extend(indent + hang + extra for extra in wrapped[1:])
        return lines


# ========================================================
# The I/O Manager
# ========================================================
class IOManager:
    """Everything the user sees and types."""

    # Menu numbers for the account options shown under the main menu.
    # Kept here so the controller and the printed menu always agree.
    MENU_AUDIT_HISTORY = 9
    MENU_LOGOUT = 10
    MENU_ADMIN = 11  # shown to administrators only

    USERNAME_MIN_LEN = InputValidator.USERNAME_MIN_LEN
    USERNAME_MAX_LEN = InputValidator.USERNAME_MAX_LEN
    PASSWORD_MIN_LEN = InputValidator.PASSWORD_MIN_LEN
    PASSWORD_MAX_LEN = InputValidator.PASSWORD_MAX_LEN

    COMPANY_NAME_MAX_LEN = 100
    NARRATIVE_MAX_LEN = 3000
    OTHER_TEXT_MAX_LEN = 60

    INDUSTRIES = (
        "Logistics",
        "Manufacturing",
        "Retail",
        "Food & Beverage",
        "Healthcare",
        "Information Technology",
        "Construction",
        "Education",
        "Finance",
        "Hospitality",
        "Aerospace",
        "Others",
    )

    GRANT_OPTIONS = (
        "1. Energy Efficiency Grant (EEG) -Base Tier",
        "2. Energy Efficiency Grant (EEG) -Advanced Tier",
        "3. Enterprise Development Grant (EDG)",
        "4. Sustainability Reporting Programme (SRP)",
        "5. Others",
    )

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"

    def __init__(self) -> None:
        # Owned parts (composition): created here, used only through us.
        self._terminal = Terminal()
        self._buttons = ButtonPanel(self._terminal)
        self._paper = PaperPrinter()
        self._art = InterfaceArt
        self._validator = InputValidator
        # Field name -> the prompt that asks for it (same checks as when the
        # record was first entered).
        self._field_prompts = {
            "Company Name": self.retrieve_company_name,
            "Company Industry": self.retrieve_company_industry,
            "Company Total Revenue": self.retrieve_total_revenue,
            "Total Employees": self.retrieve_total_employees,
            "Local Equity": self.retrieve_local_equity,
            "Sustainability Grant": self.retrieve_sustainability_grant,
            "Proposal Narrative": self.retrieve_proposal_narrative,
            "Baseline Energy Expenditure": self.retrieve_baseline_energy_expenditure,
            "Estimated Retrofit Cost": self.retrieve_estimated_retrofit_cost,
            "Reporting Advisory Fee": self.retrieve_reporting_advisory_fee,
        }

    @property
    def field_prompts(self) -> dict[str, Any]:
        return dict(self._field_prompts)

    @property
    def buttons(self) -> ButtonPanel:
        return self._buttons

    # ----- validation passthroughs used by the controller -----
    def is_valid_username(self, username: Any) -> bool:
        return self._validator.is_valid_username(username)

    def password_problems(self, password: str) -> list[str]:
        return self._validator.password_problems(password)

    def finite_float(self, text: Any) -> float:
        return self._validator.finite_float(text)

    # ========================================================
    # Welcome, menus
    # ========================================================
    def show_welcome_sequence(self) -> None:
        print(
            "Welcome to SME Sustainability Grant Eligibility & Scope Compliance Auditor!"
        )
        print(
            "This tool will help you determine if your company is eligible for the SME Sustainability Grant and assess your compliance with the scope of the grant."
        )
        print()
        print(
            "Please provide the following information about your company to proceed with the assessment. Thankyou!"
        )
        print()
        print(self._art.hello())
        print(self._art.framed_sustainability_banner())

    def key_verifier(self, key: Any, max_digits: int = 2) -> int | None:
        """Verifies that the input is a valid whole number for a menu option."""
        if not isinstance(key, str):
            return None

        key = key.strip()

        if not key:  # Empty response
            print("Empty Response!")
            return None
        if not (key.isascii() and key.isdigit()):  # letters, symbols, negatives...
            print(
                "Error! Please enter a whole number (no letters, symbols or decimals)."
            )
            return None
        if len(key) > max_digits:  # Also protects int() from huge inputs
            print(f"Error! Please enter at most {max_digits} digits.")
            return None

        return int(key)

    def get_menu_choice(self, username: str | None = None, is_admin: bool = False) -> int:
        key = None
        while key is None:  # Prints the menu and then asks for the key
            print(self._art.boxed_menu(username, is_admin))
            key = self.key_verifier(input("➔   "))
        return key

    def get_auth_choice(self) -> int:
        """Login screen shown before the main menu."""
        key = None
        while key is None:
            lines = [
                "1. Login",
                "2. Create a new account",
                "0. Exit",
            ]
            self.print_on_paper(
                lines, title="ACCOUNT LOGIN", footer="Please login to continue"
            )
            key = self.key_verifier(input("➔   "))
        return key

    # ========================================================
    # Login / account screens
    # ========================================================
    def retrieve_new_username(self) -> str:
        """New account: username format check (whether it is taken is checked
        against stored data by the controller via the Data Manager)."""
        while True:
            username = (
                input(
                    f"Choose a username ({self.USERNAME_MIN_LEN}-{self.USERNAME_MAX_LEN} characters, "
                    "letters/digits/underscore): "
                )
                .strip()
                .lower()
            )
            if username == "":
                print("Username cannot be empty. Please try again.")
            elif not self.is_valid_username(username):
                print("Invalid username. Use only letters, digits and underscores.")
            else:
                return username

    def retrieve_username(self) -> str:
        """Login: just needs something typed in; the Logic Manager decides if
        it's right."""
        while True:
            username = input("Username: ").strip().lower()
            if username == "":
                print("Username cannot be empty. Please try again.")
            else:
                return username

    def retrieve_new_password(self) -> str:
        """New account: hidden input, strength rules, typed twice to confirm."""
        while True:
            password = getpass.getpass(
                f"Choose a password (min {self.PASSWORD_MIN_LEN} chars, letters and digits, hidden): "
            )
            problems = self.password_problems(password)
            if problems:
                print("Password must " + ", ".join(problems) + ".")
                continue

            confirm = getpass.getpass("Confirm password: ")
            if confirm != password:
                print("Passwords do not match. Please try again.")
                continue
            return password

    def retrieve_password(self) -> str:
        """Login: hidden input."""
        while True:
            password = getpass.getpass("Password (hidden): ")
            if password == "":
                print("Password cannot be empty. Please try again.")
            elif len(password) > self.PASSWORD_MAX_LEN:
                # Accounts can never have a password this long, so don't bother
                # hashing it - and don't allow huge inputs.
                print(
                    f"Passwords are at most {self.PASSWORD_MAX_LEN} characters long. Please try again."
                )
            else:
                return password

    def show_username_taken(self, username: str) -> None:
        print(f"The username '{username}' is already taken. Please choose another.")

    def show_account_created(self, username: str) -> None:
        print(
            f"\n{self.GREEN}Account '{username}' created. You can now login.{self.RESET}\n"
        )

    def show_account_save_failed(self) -> None:
        print(
            f"\n{self.RED}Could not save the new account. Please try again.{self.RESET}\n"
        )

    def show_login_success(self, username: str) -> None:
        print(f"\n{self.GREEN}Welcome back, {username}!{self.RESET}\n")

    def show_login_failed(self) -> None:
        # Deliberately vague: don't reveal whether the username exists.
        print(f"\n{self.RED}Invalid username or password.{self.RESET}\n")

    def show_logged_out(self, username: str) -> None:
        print(f"\n{username} has been logged out.\n")

    # ========================================================
    # Administrator console
    # ========================================================
    ADMIN_MENU = (
        "1. List users",
        "2. Create a user",
        "3. Reset a user's password",
        "4. Change a user's role",
        "5. Delete a user (their data is archived)",
        "6. View grant rule thresholds",
        "7. Change a grant rule threshold",
        "8. Reset grant rule thresholds to the defaults",
        "0. Back to the main menu",
    )

    def get_admin_choice(self) -> int:
        key = None
        while key is None:
            self.print_on_paper(
                list(self.ADMIN_MENU),
                title="ADMIN CONSOLE",
                footer="Changes here affect every user",
            )
            key = self.key_verifier(input("➔   "))
        return key

    def show_admin_message(self, text: str, success: bool = True) -> None:
        colour = self.GREEN if success else self.RED
        print(f"\n{colour}{text}{self.RESET}\n")

    def show_admin_only(self) -> None:
        self.show_admin_message("Only administrators can open the admin console.", False)

    def show_admin_setup(self, username: str) -> None:
        print(
            f"\nFirst run: the administrator account '{username}' (ADMIN_USERNAME) "
            "does not exist yet. Choose its password now."
        )

    def show_admin_name_invalid(self, username: str) -> None:
        self.show_admin_message(
            f"ADMIN_USERNAME '{username}' is not a valid username "
            f"({self.USERNAME_MIN_LEN}-{self.USERNAME_MAX_LEN} letters, digits or "
            "underscores), so no administrator account was set up.",
            False,
        )

    def display_user_list(self, users: list[Record]) -> None:
        """users: dicts with username, role, created_at and audit_count."""
        if not users:
            self.print_on_paper(["No accounts yet."], title="USERS", footer="")
            return
        lines = [f"{'Username':<20} {'Role':<6} {'Audits':>6}  Created"]
        lines.append("-" * 52)
        for user in users:
            created = str(user.get("created_at") or "-")[:10]
            lines.append(
                f"{str(user.get('username')):<20} {str(user.get('role')):<6} "
                f"{user.get('audit_count', 0):>6}  {created}"
            )
        self.print_on_paper(lines, title="USERS", footer=f"{len(users)} account(s)")

    def select_user(self, users: list[Record], action: str) -> str | None:
        """Lists the users and asks which one to `action`. Returns the username
        or None if cancelled."""
        if not users:
            print("\nThere are no accounts.")
            return None
        print(f"\nWhich user do you want to {action}?")
        for number, user in enumerate(users, start=1):
            print(f"  {number}. {user.get('username')}  ({user.get('role')})")
        print("  0. Cancel")
        while True:
            number = self._choose_number(f"Enter 0-{len(users)}: ", len(users))
            if number is None:
                print(f"Please enter a number from 0 to {len(users)}.")
            elif number == 0:
                return None
            else:
                return str(users[number - 1].get("username"))

    def retrieve_role(self) -> str | None:
        """Returns "user", "admin", or None if cancelled."""
        print("\nRole:\n  1. user   (can run and view their own audits)")
        print("  2. admin  (can also open the admin console)\n  0. Cancel")
        while True:
            number = self._choose_number("Enter 0-2: ", 2)
            if number is None:
                print("Please enter 0, 1 or 2.")
            else:
                return {0: None, 1: "user", 2: "admin"}[number]

    def confirm_delete_user(self, username: str) -> bool:
        """Deleting an account is serious, so the name must be typed out."""
        print(
            f"\nDeleting '{username}' removes the login. Their audits and saved "
            "files are moved to the archive folder, not destroyed."
        )
        typed = input(f"Type the username '{username}' to confirm, or press Enter to cancel: ")
        return typed.strip().lower() == username

    def display_rule_config(self, rows: list[tuple[str, str, float, str]]) -> None:
        """rows: (setting name, label, value, unit)."""
        lines = [
            f"{number}. {label}: {value:g}{'' if unit == '%' else ' '}{unit}"
            for number, (_, label, value, unit) in enumerate(rows, start=1)
        ]
        self.print_on_paper(
            lines,
            title="GRANT RULE THRESHOLDS",
            footer="Used for every new decision",
        )

    def select_rule_setting(self, rows: list[tuple[str, str, float, str]]) -> int | None:
        """Returns the 0-based index of the threshold to change, or None."""
        self.display_rule_config(rows)
        print("  0. Cancel")
        while True:
            number = self._choose_number(f"Which threshold? (0-{len(rows)}): ", len(rows))
            if number is None:
                print(f"Please enter a number from 0 to {len(rows)}.")
            elif number == 0:
                return None
            else:
                return number - 1

    def retrieve_threshold_value(self, label: str, unit: str, current: float) -> float | None:
        """A new number for one threshold, or None if the user pressed Enter.
        Whether the value makes sense is decided by the Logic Manager."""
        while True:
            text = input(
                f"New value for '{label}' in {unit} (now {current:g}, Enter to cancel): "
            ).strip()
            if not text:
                return None
            try:
                return self.finite_float(text)
            except ValueError:
                print("Please enter a number, e.g. 12.5")

    def show_rule_problems(self, problems: list[str]) -> None:
        print(f"\n{self.RED}Not changed:{self.RESET}")
        for problem in problems:
            print(f"  - {problem}")
        print()

    def confirm_reset_rules(self) -> bool:
        while True:
            choice = (
                input("Reset every grant rule threshold to the default? (y/n): ")
                .strip()
                .lower()
            )
            if choice in ("y", "n"):
                return choice == "y"
            print("Invalid input. Please enter 'y' or 'n'.")

    def show_rule_settings_problem(self, status: str, problems: list[str]) -> None:
        """Start-up warning when the saved thresholds cannot be used."""
        reasons = {
            "corrupt": "the settings file was damaged and has been set aside",
            "io_error": "the settings file could not be read",
            "invalid": "the saved values are not valid",
        }
        print(
            f"\n{self.YELLOW}Saved grant rule thresholds were not used "
            f"({reasons.get(status, status)}); the defaults apply.{self.RESET}"
        )
        for problem in problems:
            print(f"  - {problem}")
        print()

    # ========================================================
    # Audit history
    # ========================================================
    def show_audit_saved_to_history(self, audit_record: Record | None) -> None:
        if audit_record is None:
            print("Warning: this audit could not be saved to your history.")
        else:
            print(f"Audit #{audit_record['audit_id']} saved to your history.")

    def show_unexpected_error(self, error: BaseException) -> None:
        print(
            f"\n{self.RED}Something went wrong and this step was skipped "
            f"({type(error).__name__}: {error})."
        )
        print(f"Nothing was saved. Please try again.{self.RESET}\n")

    def show_audit_not_saved_ai_failed(self) -> None:
        print(
            f"{self.YELLOW}The AI analysis failed, so this audit was NOT added to your history."
        )
        print(
            f"Check your internet connection and OPENROUTER_API_KEY, then run option 1 again.{self.RESET}"
        )

    # Helpers so one damaged field in audit_history.json (null, wrong type)
    # cannot crash the history screens.
    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _as_text(value: Any, default: str = "") -> str:
        return default if value is None else str(value)

    @staticmethod
    def _as_money(value: Any) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            return 0.0
        return float(value)

    def _audit_stamp(self, audit: Any) -> str:
        return self._as_text(audit.get("timestamp")).replace("T", " ")

    def display_audit_history(
        self, audits: list[Record], username: str, filtered: bool = False
    ) -> bool:
        """Summary table of every audit the user has done."""
        if len(audits) == 0:
            print(
                f"\nNo past audits found for '{username}'. Choose option 1 to start one.\n"
            )
            self._buttons.return_button()
            return False

        lines = []
        for audit in audits:
            audit = self._as_dict(audit)
            application = self._as_dict(audit.get("application"))
            result = self._as_dict(audit.get("result"))
            lines.append(
                f"#{self._as_text(audit.get('audit_id'), '?')}  {self._audit_stamp(audit)}  |  "
                f"{self._as_text(application.get('Company Name'), 'N/A')}  |  "
                f"{self._as_text(result.get('decision_status'), 'N/A')}  |  "
                f"SGD {self._as_money(result.get('approved_subsidy_sgd')):,.2f}"
            )

        count = len(audits)
        self.print_on_paper(
            lines,
            title=f"PAST AUDITS - {username}",
            footer=f"{count} audit{'s' if count != 1 else ''}"
            + (" (filtered)" if filtered else ""),
        )
        return True

    def select_audit_record(self, audits: list[Record]) -> int | None:
        """Asks which audit to open in full. Returns a list index, or None."""
        valid_ids = [self._as_dict(audit).get("audit_id") for audit in audits]
        while True:
            choice = (
                input("Enter an audit # to view in full (or press Enter to return): ")
                .strip()
                .lstrip("#")
            )
            if choice == "":
                return None
            if choice.isascii() and choice.isdigit() and int(choice) in valid_ids:
                return valid_ids.index(int(choice))
            print("Invalid audit number. Please try again.")

    def choose_history_action(self, audits: list[Record]) -> tuple[str, int | None]:
        """What to do next on the past-audits screen. Returns ("open", list
        index), ("filter", None) or ("back", None)."""
        valid_ids = [self._as_dict(audit).get("audit_id") for audit in audits]
        while True:
            choice = (
                input(
                    "Enter an audit # to view in full, F to filter the list, "
                    "or press Enter to return: "
                )
                .strip()
                .lstrip("#")
            )
            if choice == "":
                return "back", None
            if choice.lower() == "f":
                return "filter", None
            if choice.isascii() and choice.isdigit() and int(choice) in valid_ids:
                return "open", valid_ids.index(int(choice))
            print(
                "Invalid choice. Enter an audit number from the list, F, or press Enter."
            )

    def retrieve_history_filter(self, statuses: list[str]) -> tuple[str, str] | None:
        """Asks how to filter the history. Returns ("status", decision status),
        ("company", text) or None to cancel."""
        print("\nFilter your past audits by:")
        for number, status in enumerate(statuses, start=1):
            print(f"  {number}. Decision: {status}")
        print("  C. Company name (search)")
        while True:
            choice = input("Your choice (or press Enter to cancel): ").strip()
            if choice == "":
                return None
            if choice.lower() == "c":
                text = input("Company name contains: ").strip()
                if text:
                    return "company", text
                print("Nothing to search for.")
            elif (
                choice.isascii()
                and choice.isdigit()
                and 1 <= int(choice) <= len(statuses)
            ):
                return "status", statuses[int(choice) - 1]
            else:
                print("Invalid choice. Please try again.")

    def show_no_matching_audits(self) -> None:
        print("\nNo audits match that filter. Showing all of your audits again.\n")

    def confirm_export_pdf(self) -> bool:
        while True:
            choice = input("Export this audit as a PDF report? (y/n): ").strip().lower()
            if choice in ("y", "n"):
                return choice == "y"
            print("Invalid input. Please enter 'y' or 'n'.")

    def show_pdf_result(self, status: str, file_name: str | None, folder: str) -> None:
        messages = {
            "exported": f"PDF report saved as '{file_name}' in {folder}",
            "missing_dependency": "PDF export needs the 'reportlab' package: pip install reportlab",
            "invalid_pdf_name": "The PDF file name is not valid, so nothing was exported.",
            "pdf_error": "The PDF report could not be created. Nothing was exported.",
        }
        print(messages.get(status, f"PDF export failed ({status})."))

    def wait_for_return(self) -> None:
        self._buttons.return_button()

    def wait_for_continue(self) -> None:
        self._buttons.continue_button()

    def show_audit_count(self, count: int) -> None:
        """Shown right after login so the user sees their saved history is loaded."""
        if count:
            print(
                f"You have {count} saved audit{'s' if count != 1 else ''} (menu option 9).\n"
            )
        else:
            print("You have no saved audits yet. Choose option 1 to start one.\n")

    # Messages for a clean exit (the controller cannot print; only this layer does).
    def show_interrupted(self) -> None:
        print("\n\nInterrupted. Goodbye!")

    def show_input_ended(self) -> None:
        print(
            "\n\nNo more input available. If you run the app in Docker, "
            "start it with 'docker run -it ...' so you can type into it."
        )

    def display_audit_detail(self, audit: Record) -> None:
        """Full view of one saved audit, reusing the existing report layouts."""
        audit = self._as_dict(audit)
        application = self._as_dict(audit.get("application"))
        ai_audit = self._as_dict(audit.get("ai_audit"))
        result = self._as_dict(audit.get("result"))

        print(
            f"\nAudit #{self._as_text(audit.get('audit_id'), '?')} - {self._audit_stamp(audit)}"
        )
        if application:
            self.print_on_paper(
                self.format_pairs(application), title="APPLICATION DETAILS"
            )
        if ai_audit:
            self.display_ai_audit(ai_audit)
        if result:
            try:
                self.display_grant_decision(result)
            except (KeyError, TypeError, ValueError):
                # Saved decision is missing fields: show what is there instead.
                self.print_on_paper(
                    self.format_pairs(result), title="GRANT ELIGIBILITY DECISION"
                )

    # ========================================================
    # Collecting an application
    # ========================================================
    def display_company_profile(
        self,
        company_name: str,
        company_industry: str,
        total_revenue: float,
        total_employees: int,
        local_equity: float,
        proposal_type: str,
        sustainability_grant: str,
        proposal_narrative: str,
        baseline_energy_expenditure: float,
        estimated_retrofit_cost: float,
        reporting_advisory_fee: float,
    ) -> None:
        print(f"Company Name: {company_name}")
        print(f"Company Industry: {company_industry}")
        print(f"Company Total Revenue: {total_revenue}")
        print(f"Total Employees: {total_employees}")
        print(f"Local Equity: {local_equity}")
        print(f"Proposal Type: {proposal_type}")
        print(f"Sustainability Grant: {sustainability_grant}")
        print(f"Proposal Narrative:  {proposal_narrative}")
        print(f"Baseline Energy Expenditure: {baseline_energy_expenditure}")
        print(f"Estimated Retrofit Cost: {estimated_retrofit_cost}")
        print(f"Reporting Advisory Fee: {reporting_advisory_fee}")

    def retrieve_company_name(self) -> str:
        while True:
            company_name = input("Enter your Company's Name: ").strip()
            if company_name == "":
                print("Company Name cannot be empty. Please try again.")
            elif len(company_name) > self.COMPANY_NAME_MAX_LEN:
                print(
                    f"Company Name must be at most {self.COMPANY_NAME_MAX_LEN} characters. Please try again."
                )
            else:
                return company_name

    def retrieve_company_industry(self) -> str:
        valid_industries = list(self.INDUSTRIES)

        while True:
            company_industry = (
                input(
                    f"Enter your Company's Industry Sector (choose from {', '.join(valid_industries)}): "
                )
                .strip()
                .title()
            )

            if company_industry.strip() == "":
                print("Company Industry Sector cannot be empty. Please try again.")
            elif company_industry not in valid_industries:
                print("Invalid. Please select a valid Industry Sector.")
            elif company_industry == "Others":
                return self.get_valid_other_industry()
            else:
                return company_industry

    def get_valid_other_industry(self) -> str:
        while True:
            other_industry = (
                input("Please specify your Company's Industry Sector: ")
                .strip()
                .title()
            )
            if other_industry == "":
                print("Industry Sector cannot be empty. Please try again.")
            elif len(other_industry) > self.OTHER_TEXT_MAX_LEN:
                print(
                    f"Industry Sector must be at most {self.OTHER_TEXT_MAX_LEN} characters."
                )
            elif not other_industry.replace(" ", "").isalpha():
                print(
                    "Invalid. Please provide a valid Industry Sector containing only alphabetic characters."
                )
            else:
                return other_industry

    def retrieve_total_revenue(self) -> float:
        while True:
            try:
                total_revenue = self.finite_float(
                    input("Enter your Company's Total Revenue (in SGD): ")
                )
                if total_revenue < 0:
                    print("Total Revenue cannot be negative. Please try again.")
                elif total_revenue == 0:
                    print("Total Revenue cannot be zero. Please try again.")
                else:
                    return total_revenue
            except ValueError:
                print("Invalid input. Please enter a numeric value for total revenue.")

    def retrieve_total_employees(self) -> int:
        while True:
            try:
                total_employees = int(
                    input("Enter your Company's Total Number of Employees: ")
                )
                if total_employees < 0:
                    print(
                        "Total Number of Employees cannot be negative. Please try again."
                    )
                elif total_employees == 0:
                    print("Total Number of Employees cannot be zero. Please try again.")
                else:
                    return total_employees
            except ValueError:
                print(
                    "Invalid input. Please enter a numeric value for total number of employees."
                )

    def retrieve_local_equity(self) -> float:
        while True:
            raw_value = input(
                "Enter equity % owned by Singapore Citizens/PRs: "
            ).strip()
            if raw_value == "":
                print("Equity % cannot be empty. Please try again.")
                continue
            try:
                local_equity = self.finite_float(raw_value)
                if local_equity <= 0 or local_equity > 100:
                    print(
                        "Equity % must be a value between 0 and 100. Please try again."
                    )
                    continue
                else:
                    return local_equity
            except ValueError:
                print(
                    "Invalid input. Please enter a numeric value for your local equity."
                )

    def retrieve_proposal_type(self) -> str:
        """The applicant self-declares which kind of proposal this is, so only
        the relevant cost fields are collected, and so the AI gets a strong
        prior instead of guessing purely from the free-text narrative."""
        valid_types = {
            "1": "Equipment / Energy Upgrade",
            "2": "ESG Reporting / Advisory",
        }

        while True:
            choice = input("""What type of proposal is this?\n
                1. Equipment / Energy Upgrade (e.g. fleet electrification, HVAC retrofit, lighting)\n
                2. ESG Reporting / Advisory (e.g. inaugural sustainability report, external assurance)\n
                    Enter 1 or 2: """).strip()

            if choice in valid_types:
                return valid_types[choice]
            else:
                print("Invalid choice. Please enter 1 or 2.")

    def retrieve_baseline_energy_expenditure(self) -> float:
        while True:
            raw_value = input(
                "Enter baseline annual energy expenditure (in SGD): "
            ).strip()
            if raw_value == "":
                print(
                    "Baseline annual energy expenditure cannot be empty. Please try again."
                )
                continue
            try:
                baseline_energy_expenditure = self.finite_float(raw_value)
                if baseline_energy_expenditure <= 0:
                    print(
                        "Baseline annual energy expenditure cannot be zero or negative. Please try again."
                    )
                    continue
                else:
                    return baseline_energy_expenditure
            except ValueError:
                print(
                    "Invalid input. Please enter a numeric value for baseline annual energy expenditure."
                )

    def retrieve_estimated_retrofit_cost(self) -> float:
        while True:
            raw_value = input("Enter estimated retrofit cost (in SGD): ").strip()
            if raw_value == "":
                print("Estimated retrofit cost cannot be empty. Please try again.")
                continue
            try:
                estimated_retrofit_cost = self.finite_float(raw_value)
                if estimated_retrofit_cost <= 0:
                    print(
                        "Estimated retrofit cost cannot be zero or negative. Please try again."
                    )
                    continue
                else:
                    return estimated_retrofit_cost
            except ValueError:
                print(
                    "Invalid input. Please enter a numeric value for estimated retrofit cost."
                )

    def retrieve_proposal_narrative(self) -> str:
        """The free-text description of the upgrade: the raw narrative the AI
        needs to classify GHG scope, detect exclusion keywords and estimate
        abatement."""
        print("Describe your proposed sustainability/energy upgrade in your own words.")
        print("(e.g. what equipment is being replaced, the fuel/energy source involved,")
        print(" and whether any components are second-hand, refurbished, or modified.)")
        while True:
            narrative = input("Proposal Description: ").strip()
            if narrative == "":
                print("Proposal description cannot be empty. Please try again.")
            elif len(narrative) > self.NARRATIVE_MAX_LEN:
                print(
                    f"Please keep the description under {self.NARRATIVE_MAX_LEN} characters "
                    f"(yours has {len(narrative)})."
                )
            else:
                return narrative

    def retrieve_reporting_advisory_fee(self) -> float:
        """Only collected for ESG Reporting / Advisory proposals."""
        while True:
            raw_value = input(
                "Enter estimated external ESG reporting/advisory fee (in SGD): "
            ).strip()
            if raw_value == "":
                print("Reporting/advisory fee cannot be empty. Please try again.")
                continue
            try:
                reporting_advisory_fee = self.finite_float(raw_value)
                if reporting_advisory_fee < 0:
                    print("Reporting/advisory fee cannot be negative. Please try again.")
                    continue
                else:
                    return reporting_advisory_fee
            except ValueError:
                print(
                    "Invalid input. Please enter a numeric value for the reporting/advisory fee."
                )

    def retrieve_sustainability_grant(self) -> str:
        """The Sustainability Grant the company wants to apply for."""
        valid_grants = self.GRANT_OPTIONS
        while True:
            print("\nWhich Sustainability Grant would your company like to apply for?")
            for grant in valid_grants:
                print(grant)

            grant_choice = input(
                "Enter the number corresponding to your choice (1-5): "
            ).strip()

            if grant_choice == "":
                print(
                    "Sustainability Grant choice cannot be empty. Please select a valid option from 1 to 5."
                )
                continue

            if grant_choice not in ["1", "2", "3", "4", "5"]:
                print("Invalid choice. Please select a valid option (1-5).")
                continue

            if grant_choice == "5":
                while True:
                    other_grant = input(
                        "Please specify the Sustainability Grant that is not stated in the options: "
                    ).strip()
                    if other_grant == "":
                        print(
                            "Sustainability Grant cannot be empty. Please provide a valid grant name."
                        )
                    elif len(other_grant) > self.OTHER_TEXT_MAX_LEN:
                        print(
                            f"Grant name must be at most {self.OTHER_TEXT_MAX_LEN} characters."
                        )
                    elif not other_grant.replace(" ", "").isalpha():
                        print("Invalid input. Please enter a valid grant name.")
                    else:
                        return other_grant

            else:
                return valid_grants[int(grant_choice) - 1]

    # ========================================================
    # Showing records
    # ========================================================
    def display_applied_grants(
        self, scheme_grant_records: Records, key: int
    ) -> Records | None:
        if len(scheme_grant_records) == 0:
            print(
                f"\n {self.RED}⚠️  SYSTEM NOTICE: You do not have any grants applied.{self.RESET}\n"
            )
            self._buttons.return_button()
            return None

        # Build the paper contents: one block per grant
        lines = []
        for i, grant in enumerate(scheme_grant_records, start=1):
            grant = ApplicationRecord(grant).flat
            if i > 1:
                lines.append("")
            lines.append(
                f"{i}. {grant.get('Company Name', 'N/A')} - {grant.get('Company Industry', 'N/A')}"
            )
            details = {
                "Total Revenue": grant.get("Company Total Revenue", "N/A"),
                "Total Employees": grant.get("Total Employees", "N/A"),
                "Local Equity": grant.get("Local Equity", "N/A"),
                "Proposal Type": grant.get("Proposal Type", "N/A"),
                "Proposal Narrative": grant.get("Proposal Narrative", "N/A"),
                "Sustainability Grant": grant.get("Sustainability Grant", "N/A"),
                "Baseline Energy Expenditure": grant.get(
                    "Baseline Energy Expenditure", "N/A"
                ),
                "Estimated Retrofit Cost": grant.get("Estimated Retrofit Cost", "N/A"),
                "Reporting Advisory Fee": grant.get("Reporting Advisory Fee", 0.0),
            }
            lines.extend(self.format_pairs(details, indent="   "))

        count = len(scheme_grant_records)
        footer = f"{count} record{'s' if count != 1 else ''}"

        if key == 1:
            self.print_on_paper(lines, title="SCHEME GRANT RECORDS", footer=footer)
            self._buttons.ai_button()
        elif key in (4, 5, 6):
            self.print_on_paper(lines, title="GRANTS ALREADY APPLIED FOR", footer=footer)
            if key == 4:
                self._buttons.return_button()

        return scheme_grant_records

    # ========================================================
    # Saving and loading files
    # ========================================================
    def retrieve_json_filename(
    self, blocked_chars: str = "", for_loading: bool = False
    ) -> str | None:
        """Asks for a save/load file name using the floppy-disk label prompt.
        blocked_chars: characters the typed name may not contain (supplied by
        the controller from the Data Manager, which owns the file-name rules).
        for_loading shows the 'load' disk instead of the 'save' disk.
        Returns the name, or None if the user entered nothing (cancel)."""
        if sys.stdin.isatty():
            name = self.prompt_filename_on_disk(
                for_loading=for_loading, max_len=50, blocked=blocked_chars
            )
        else:
            name = input("Enter JSON file name (e.g. grants, blank to cancel): ")
        name = (name or "").strip()
        return name or None

    def confirm_overwrite_records(self) -> bool:
        while True:
            choice = (
                input(
                    "This will replace the records currently in memory. Continue? (y/n): "
                )
                .strip()
                .lower()
            )
            if choice == "y":
                return True
            if choice == "n":
                return False
            print("Invalid input. Please enter 'y' or 'n'.")

    def ask_existing_file_action(self, file_name: str) -> str:
        """The file already exists: returns "add", "replace" or "cancel"."""
        while True:
            choice = (
                input(
                    f"'{file_name}' already exists. "
                    "(a = add to it, r = replace it, c = cancel): "
                )
                .strip()
                .lower()
            )
            if choice in ("a", "r", "c"):
                return {"a": "add", "r": "replace", "c": "cancel"}[choice]
            print("Invalid input. Please enter 'a', 'r' or 'c'.")

    def display_save_result(self, status: str | None, file_name: str) -> None:
        messages = {
            "saved": f"Data successfully saved to {file_name}.",
            "no_name": "Cancelled. Returning to main menu.",
            "invalid_name": "That file name contains illegal characters.",
            "io_error": "The file could not be written.",
        }
        print(messages.get(status, f"Unknown save status: {status}"))
        if status == "saved":
            print(self._art.save_disk_block_deep_blue())

    def display_load_result(self, status: str, file_name: str) -> None:
        messages = {
            "loaded": f"Records loaded successfully from {file_name}.",
            "no_name": "Cancelled. Returning to main menu.",
            "invalid_name": "That file name contains illegal characters.",
            "not_found": f"File '{file_name}' was not found.",
            "invalid_json": "The file is corrupt or unreadable. It was set aside as a .corrupt backup.",
            "invalid_format": "The file is valid JSON but not a list of audit records. It was set aside.",
            "io_error": "The operating system refused to read the file.",
        }
        print(messages.get(status, f"Unknown load status: {status}"))

    def confirm_save_to_json(self) -> bool:
        art, regions = self._art.yes_no_buttons("Save this record to JSON now?")
        return self._terminal.execute_choice_interaction(
            art, regions, {"y": True, "n": False}
        )

    def confirm_unsaved_exit(self) -> bool:
        """Asks until the answer is y or n, so a typo never discards
        unsaved records."""
        while True:
            choice = (
                input("You have unsaved records. Save before leaving? (y/n): ")
                .strip()
                .lower()
            )
            if choice in ("y", "n"):
                return choice == "y"
            print("Invalid input. Please enter 'y' or 'n'.")

    def show_leave_cancelled(self) -> None:
        print("Save cancelled. You still have unsaved records, so you were returned to the menu.")

    def prompt_filename_on_disk(
        self, for_loading: bool = False, max_len: int = 50, blocked: str = ""
    ) -> str:
        """Shows the floppy disk and lets the user type the file name on its label."""
        if for_loading:
            art, rows_up, col = self._art.load_disk_prompt_art(max_len=max_len)
        else:
            art, rows_up, col = self._art.save_disk_prompt_art(max_len=max_len)
        print(art)

        # Jump back up into the label and start typing there
        sys.stdout.write(f"\033[{rows_up}A\033[{col}G{self._art.LABEL}")
        sys.stdout.flush()
        try:
            return self._terminal.read_limited(max_len, blocked).strip()
        finally:
            # Reset colours and move back below the disk
            # (no newline is echoed now, so move down the full rows_up)
            sys.stdout.write(f"{self._art.RESET}\033[{rows_up}B\r")
            sys.stdout.flush()

    # ========================================================
    # Paper-style output
    # ========================================================
    def print_on_paper(
        self,
        lines: list[str],
        title: str = "REPORT",
        footer: str = "End of report",
        width: int | None = None,
    ) -> None:
        self._paper.print_on_paper(lines, title, footer, width)

    def format_pairs(
        self, data: Any, width: int | None = None, indent: str = ""
    ) -> list[str]:
        return self._paper.format_pairs(data, width, indent)

    def display_ai_audit(self, ai_audit: AiAudit) -> None:
        """Renders the AI Manager's structured output. All console printing
        belongs in this class, so the AI and Logic Managers just return data."""
        self.print_on_paper(self.format_pairs(ai_audit), title="AI AUDIT REPORT")

    def run_ai_analysis_bar(
        self, stop_event: threading.Event, timeout_seconds: int = 60
    ) -> None:
        """Animates the progress bar, one bar per second. Stops instantly if
        stop_event is flagged or when it hits the maximum timeout."""
        cyan = "\033[96m"
        reset = "\033[0m"

        print("\nAnalysing your proposal with the AI Manager, please wait...\n")
        sys.stdout.write("\033[?25l")  # Hide text cursor
        sys.stdout.flush()

        try:
            for i in range(1, timeout_seconds + 1):
                # Has the API background thread finished and flagged us to stop?
                if stop_event.is_set():
                    break

                percent = int((i / timeout_seconds) * 100)
                progress_bar = f"\r   Time Taken: [{cyan}{'█' * i}{' ' * (timeout_seconds - i)}{reset}] {percent}% ({i}/{timeout_seconds}s)"

                sys.stdout.write(progress_bar)
                sys.stdout.flush()
                time.sleep(1)
        finally:
            # Restore terminal text cursor
            sys.stdout.write("\033[?25h\n\n")
            sys.stdout.flush()

    def display_grant_decision(self, result: dict[str, Any]) -> None:
        """Renders the Logic Manager's decision."""
        lines = [
            f"SME Eligible     : {'YES' if result['is_sme'] else 'NO'}",
            f"Decision Status  : {result['decision_status']}",
            f"Audit Passed     : {result['audit_passed']}",
            f"Approved Subsidy : SGD {result['approved_subsidy_sgd']:,.2f}",
        ]

        sections = [
            ("Matched Schemes:", result["matched_schemes"]),
            ("Reasons:", result["reasons"]),
            ("Recommendations:", result["recommendations"]),
        ]
        for heading, items in sections:
            if items:
                lines.append("")
                lines.append(heading)
                lines.extend(f"  - {item}" for item in items)
        self.print_on_paper(lines, title="GRANT ELIGIBILITY DECISION")

    # ========================================================
    # Menu options 5 and 6: pick, edit and delete records
    # ========================================================
    def _choose_number(self, prompt: str, highest: int) -> int | None:
        """Asks for a whole number from 0 to highest. Returns None if invalid."""
        answer = self.key_verifier(input(prompt), max_digits=len(str(highest)))
        if answer is None or answer > highest:
            return None
        return answer

    def select_record_index(self, records: Records, action: str) -> int | None:
        """Lists the records and asks which to `action` ("update"/"delete").
        Returns the 0-based index, or None if the user cancels."""
        print(f"\nWhich record do you want to {action}?")
        for number, record in enumerate(records, start=1):
            record = ApplicationRecord(record).flat
            print(
                f"  {number}. {record.get('Company Name') or 'N/A'}"
                f"  ({record.get('Proposal Type') or 'N/A'})"
            )
        print("  0. Cancel")

        while True:
            number = self._choose_number(f"Enter 0-{len(records)}: ", len(records))
            if number is None:
                print(f"Please enter a number from 0 to {len(records)}.")
            elif number == 0:
                return None
            else:
                return number - 1

    def select_field_to_edit(self, record: Record) -> str | None:
        """Asks which field of `record` to change. Returns the field name or None."""
        wrapped = ApplicationRecord(record)
        fields = wrapped.proposal.editable_fields
        flat = wrapped.flat
        print("\nWhich detail do you want to change?")
        for number, field in enumerate(fields, start=1):
            value = str(flat.get(field, "N/A"))
            shortened = value if len(value) <= 40 else value[:37] + "..."
            print(f"  {number}. {field}: {shortened}")
        print("  0. Cancel")

        while True:
            number = self._choose_number(f"Enter 0-{len(fields)}: ", len(fields))
            if number is None:
                print(f"Please enter a number from 0 to {len(fields)}.")
            elif number == 0:
                return None
            else:
                return fields[number - 1]

    def retrieve_field_value(self, field: str) -> Any:
        """Prompts for a new value of `field` with the original validation."""
        return self._field_prompts[field]()

    def confirm_delete_record(self, company_name: str) -> bool:
        while True:
            choice = (
                input(f"Delete the record for '{company_name}'? (y/n): ")
                .strip()
                .lower()
            )
            if choice in ("y", "n"):
                return choice == "y"
            print("Invalid input. Please enter 'y' or 'n'.")

    def show_record_updated(self, company_name: str, field: str) -> None:
        print(
            f"Updated '{field}' for '{company_name}'. Use option 2 to save the change."
        )
        self._buttons.return_button()

    def show_record_deleted(self, company_name: str) -> None:
        print(
            f"Deleted the record for '{company_name}'. "
            "Use option 2 (choose replace) to remove it from a saved file too."
        )
        self._buttons.return_button()

    def show_record_not_changed(self) -> None:
        print("Nothing was changed.")
        self._buttons.return_button()

    def display_no_records_message(self) -> None:
        print("No records yet. Please select option 1 first.")
        self._buttons.return_button()

    def display_no_ai_audit(self) -> None:
        """When the AI hasn't yet audited. The AI audits right after the input
        for the company grant, so this only shows when no data exists."""
        print("No AI audit yet. Please run option 7 first.")
        self._buttons.return_button()

    def show_wrong_option_error(self) -> None:
        print(self._art.wrong_sign_red())
        self._buttons.return_button()

    def show_goodbye(self) -> None:
        print(self._art.goodbye_art())
