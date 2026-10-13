import threading
from typing import Any
from collections.abc import Iterator
from sme_interface_stores import sme_interface_gui as gui
import sys
import os
import time
import textwrap
import codecs
import getpass
import math
from contextlib import contextmanager

# Type aliases (plain dicts/lists - the project uses no classes)
Record = dict[str, Any]
Records = list[Record]
AiAudit = dict[str, Any]

# ========================================================
# Platform setup (done once)
# ========================================================
is_windows = os.name == "nt"

if is_windows:
    import msvcrt
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    STD_INPUT_HANDLE = -10
    ENABLE_MOUSE_INPUT = 0x0010
    ENABLE_EXTENDED_FLAGS = 0x0080
    _saved_console_mode = wintypes.DWORD()

    def _getb() -> bytes:
        """Read one raw byte (blocks, no CPU spinning)."""
        return msvcrt.getch()

    def _pending(timeout: float = 0.02) -> bool:
        """Is another byte already waiting?"""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if msvcrt.kbhit():
                return True
            time.sleep(0.002)
        return False

else:
    import select
    import termios
    import tty

    def _getb() -> bytes:
        return os.read(sys.stdin.fileno(), 1)

    def _pending(timeout: float = 0.02) -> bool:
        return bool(select.select([sys.stdin.fileno()], [], [], timeout)[0])


@contextmanager
def _raw_input() -> Iterator[None]:
    """Raw terminal mode on Unix, set once and restored after. No-op on Windows."""
    if is_windows:
        yield
        return
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ========================================================
# Mouse tracking
# ========================================================
def enable_mouse_tracking() -> None:
    sys.stdout.write("\033[?1000h\033[?25l")  # mouse on, hide cursor
    sys.stdout.flush()
    if is_windows:
        hInput = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        kernel32.GetConsoleMode(hInput, ctypes.byref(_saved_console_mode))
        mode = _saved_console_mode.value
        kernel32.SetConsoleMode(hInput, (mode & ~ENABLE_EXTENDED_FLAGS) | ENABLE_MOUSE_INPUT)


def disable_mouse_tracking() -> None:
    sys.stdout.write("\033[?1000l\033[?25h\n")  # mouse off, show cursor
    sys.stdout.flush()
    if is_windows:
        hInput = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        kernel32.SetConsoleMode(hInput, _saved_console_mode.value)


# ========================================================
# One event reader shared by every button/choice prompt
# ========================================================
def _read_event() -> tuple[str, Any] | None:
    """Return ("key", char), ("click", column), or None for anything ignorable."""
    b = _getb()

    if is_windows and b in (b"\x00", b"\xe0"):   # arrow/function key: skip 2nd byte
        _getb()
        return None

    if b != b"\x1b":
        return ("key", b.decode("utf-8", "ignore"))

    # ESC: either a lone Esc press or the start of an escape sequence
    if not _pending() or _getb() != b"[":
        return None
    if not _pending() or _getb() != b"M":        # some other sequence (e.g. arrows)
        return None

    # Mouse report: ESC [ M <button> <x> <y>
    btn, x, _y = _getb(), _getb(), _getb()
    if btn[0] - 32 == 0:                          # left button press
        return ("click", x[0] - 32)
    return None


def wait_for_choice(art: str, regions: dict[Any, tuple[int, int]], keys: dict[str, Any]) -> Any:
    """Show `art`, then wait for a mapped key or a left click inside a region.

    regions: {value: (min_x, max_x)}    keys: {"y": value, "\\r": value, ...}
    Returns the matching value.
    """
    print(art, end="", flush=True)
    enable_mouse_tracking()
    try:
        with _raw_input():
            while True:
                event = _read_event()
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
        disable_mouse_tracking()


# Thin wrappers so existing callers don't change
def execute_button_interaction(button_art: str, min_x: int = 5, max_x: int = 35) -> None:
    wait_for_choice(button_art, {True: (min_x, max_x)}, {"\r": True, "\n": True})


def execute_choice_interaction(art: str, regions: dict[Any, tuple[int, int]], keys: dict[str, Any]) -> Any:
    return wait_for_choice(art, regions, keys)


# ========================================================
# Text input: length-limited line reader
# ========================================================
_decoder = codecs.getincrementaldecoder("utf-8")("ignore")


def _read_key() -> str:
    """Read one character without waiting for Enter."""
    if is_windows:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            msvcrt.getwch()
            return ""
        return ch
    while True:                                   # assemble multi-byte UTF-8 characters
        s = _decoder.decode(_getb())
        if s:
            return s


def read_limited(max_len: int, blocked: str = "") -> str:
    """Read a line, silently ignoring keys once max_len characters are typed."""
    buf = []
    with _raw_input():                            # set once, not per keystroke
        while True:
            ch = _read_key()

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




# Shows welcome sequence with ASCII art and sustainability banner
def show_welcome_sequence() -> None:
    print("Welcome to SME Sustainability Grant Eligibility & Scope Compliance Auditor!")
    print("This tool will help you determine if your company is eligible for the SME Sustainability Grant and assess your compliance with the scope of the grant.")
    print()
    print("Please provide the following information about your company to proceed with the assessment. Thankyou!")
    print()
    print(gui.hello())
    print(gui.framed_sustainability_banner())

# Verifies that the input is a valid integer key for the menu options.
def key_verifier(key: Any, max_digits: int = 2) -> int | None:
    if not isinstance(key, str):
        return None

    key = key.strip()

    if not key:  # Empty response
        print("Empty Response!")
        return None
    if not (key.isascii() and key.isdigit()):  # Letters, symbols, negatives, decimals, floats
        print("Error! Please enter a whole number (no letters, symbols or decimals).")
        return None
    if len(key) > max_digits:  # Also protects int() from huge inputs
        print(f"Error! Please enter at most {max_digits} digits.")
        return None

    return int(key)

# Menu Options
def get_menu_choice(username: str | None = None) -> int:
    key = None
    while key is None: #Prints the menu and then asks you to get the key
        print(gui.boxed_menu(username))
        key = key_verifier(input("➔   ")) #This function calls the key_verifier function which checks if the key is an integer
    return key


# ========================================================
# Login / account screens
# ========================================================
# Menu numbers for the account options shown under the main menu.
# Kept here so main.py and the printed menu always agree.
MENU_AUDIT_HISTORY = 9
MENU_LOGOUT = 10

USERNAME_MIN_LEN = 3
USERNAME_MAX_LEN = 20
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 64


# Login screen shown before the main menu.
def get_auth_choice() -> int:
    key = None
    while key is None:
        lines = [
            "1. Login",
            "2. Create a new account",
            "0. Exit",
        ]
        print_on_paper(lines, title="ACCOUNT LOGIN", footer="Please login to continue")
        key = key_verifier(input("➔   "))
    return key


def is_valid_username(username: Any) -> bool:
    """3-20 characters: letters, digits and underscores only."""
    return (
        USERNAME_MIN_LEN <= len(username) <= USERNAME_MAX_LEN
        and username.isascii()
        and username.replace("_", "").isalnum()
    )


# New account: username format check (whether it is taken is checked
# against stored data in main.py via the Data Manager).
def retrieve_new_username() -> str:
    while True:
        username = input(
            f"Choose a username ({USERNAME_MIN_LEN}-{USERNAME_MAX_LEN} characters, "
            "letters/digits/underscore): "
        ).strip().lower()
        if username == "":
            print("Username cannot be empty. Please try again.")
        elif not is_valid_username(username):
            print("Invalid username. Use only letters, digits and underscores.")
        else:
            return username


# Login: just needs something typed in; the Logic Manager decides if it's right.
def retrieve_username() -> str:
    while True:
        username = input("Username: ").strip().lower()
        if username == "":
            print("Username cannot be empty. Please try again.")
        else:
            return username


def password_problems(password: str) -> list[str]:
    """Returns a list of rules the password breaks (empty if it's fine)."""
    problems = []
    if len(password) < PASSWORD_MIN_LEN:
        problems.append(f"be at least {PASSWORD_MIN_LEN} characters long")
    if len(password) > PASSWORD_MAX_LEN:
        problems.append(f"be at most {PASSWORD_MAX_LEN} characters long")
    if not any(ch.isalpha() for ch in password):
        problems.append("contain at least one letter")
    if not any(ch.isdigit() for ch in password):
        problems.append("contain at least one digit")
    if password != password.strip():
        problems.append("not start or end with a space")
    return problems


# New account: hidden input, strength rules, typed twice to confirm.
def retrieve_new_password() -> str:
    while True:
        password = getpass.getpass(
            f"Choose a password (min {PASSWORD_MIN_LEN} chars, letters and digits, hidden): "
        )
        problems = password_problems(password)
        if problems:
            print("Password must " + ", ".join(problems) + ".")
            continue

        confirm = getpass.getpass("Confirm password: ")
        if confirm != password:
            print("Passwords do not match. Please try again.")
            continue
        return password


# Login: hidden input.
def retrieve_password() -> str:
    while True:
        password = getpass.getpass("Password (hidden): ")
        if password == "":
            print("Password cannot be empty. Please try again.")
        elif len(password) > PASSWORD_MAX_LEN:
            # Accounts can never have a password this long, so don't bother
            # hashing it - and don't allow huge inputs.
            print(f"Passwords are at most {PASSWORD_MAX_LEN} characters long. Please try again.")
        else:
            return password


def show_username_taken(username: str) -> None:
    print(f"The username '{username}' is already taken. Please choose another.")


def show_account_created(username: str) -> None:
    green = "\033[92m"
    reset = "\033[0m"
    print(f"\n{green}Account '{username}' created. You can now login.{reset}\n")


def show_account_save_failed() -> None:
    red = "\033[91m"
    reset = "\033[0m"
    print(f"\n{red}Could not save the new account. Please try again.{reset}\n")


def show_login_success(username: str) -> None:
    green = "\033[92m"
    reset = "\033[0m"
    print(f"\n{green}Welcome back, {username}!{reset}\n")


def show_login_failed() -> None:
    red = "\033[91m"
    reset = "\033[0m"
    # Deliberately vague: don't reveal whether the username exists.
    print(f"\n{red}Invalid username or password.{reset}\n")


def show_logged_out(username: str) -> None:
    print(f"\n{username} has been logged out.\n")


# ========================================================
# Audit history
# ========================================================
def show_audit_saved_to_history(audit_record: Record) -> None:
    if audit_record is None:
        print("Warning: this audit could not be saved to your history.")
    else:
        print(f"Audit #{audit_record['audit_id']} saved to your history.")


def show_unexpected_error(error: BaseException) -> None:
    red = "\033[91m"
    reset = "\033[0m"
    print(f"\n{red}Something went wrong and this step was skipped "
          f"({type(error).__name__}: {error}).")
    print(f"Nothing was saved. Please try again.{reset}\n")


def show_audit_not_saved_ai_failed() -> None:
    yellow = "\033[93m"
    reset = "\033[0m"
    print(f"{yellow}The AI analysis failed, so this audit was NOT added to your history.")
    print(f"Check your internet connection and OPENROUTER_API_KEY, then run option 1 again.{reset}")


# Helpers so one damaged field in audit_history.json (null, wrong type)
# cannot crash the history screens.
def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_text(value: Any, default: str = "") -> str:
    return default if value is None else str(value)


def _as_money(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return 0.0
    return float(value)


def _audit_stamp(audit: Any) -> str:
    return _as_text(audit.get("timestamp")).replace("T", " ")


# Summary table of every audit the user has done.
def display_audit_history(audits: list[Record], username: str, filtered: bool = False) -> bool:
    if len(audits) == 0:
        print(f"\nNo past audits found for '{username}'. Choose option 1 to start one.\n")
        gui.return_button()
        return False

    lines = []
    for audit in audits:
        audit = _as_dict(audit)
        application = _as_dict(audit.get("application"))
        result = _as_dict(audit.get("result"))
        lines.append(
            f"#{_as_text(audit.get('audit_id'), '?')}  {_audit_stamp(audit)}  |  "
            f"{_as_text(application.get('Company Name'), 'N/A')}  |  "
            f"{_as_text(result.get('decision_status'), 'N/A')}  |  "
            f"SGD {_as_money(result.get('approved_subsidy_sgd')):,.2f}"
        )

    count = len(audits)
    print_on_paper(
        lines,
        title=f"PAST AUDITS - {username}",
        footer=f"{count} audit{'s' if count != 1 else ''}" + (" (filtered)" if filtered else "")
    )
    return True


# Asks which audit to open in full. Returns a list index, or None to go back.
def select_audit_record(audits: list[Record]) -> int | None:
    valid_ids = [_as_dict(audit).get("audit_id") for audit in audits]
    while True:
        choice = input("Enter an audit # to view in full (or press Enter to return): ").strip().lstrip("#")
        if choice == "":
            return None
        if choice.isascii() and choice.isdigit() and int(choice) in valid_ids:
            return valid_ids.index(int(choice))
        print("Invalid audit number. Please try again.")


# What to do next on the past-audits screen. Returns ("open", list index),
# ("filter", None) or ("back", None).
def choose_history_action(audits: list[Record]) -> tuple[str, int | None]:
    valid_ids = [_as_dict(audit).get("audit_id") for audit in audits]
    while True:
        choice = input(
            "Enter an audit # to view in full, F to filter the list, "
            "or press Enter to return: "
        ).strip().lstrip("#")
        if choice == "":
            return "back", None
        if choice.lower() == "f":
            return "filter", None
        if choice.isascii() and choice.isdigit() and int(choice) in valid_ids:
            return "open", valid_ids.index(int(choice))
        print("Invalid choice. Enter an audit number from the list, F, or press Enter.")


# Asks how to filter the history. Returns ("status", decision status),
# ("company", text) or None to cancel.
def retrieve_history_filter(statuses: list[str]) -> tuple[str, str] | None:
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
        elif choice.isascii() and choice.isdigit() and 1 <= int(choice) <= len(statuses):
            return "status", statuses[int(choice) - 1]
        else:
            print("Invalid choice. Please try again.")


def show_no_matching_audits() -> None:
    print("\nNo audits match that filter. Showing all of your audits again.\n")


def confirm_export_pdf() -> bool:
    while True:
        choice = input("Export this audit as a PDF report? (y/n): ").strip().lower()
        if choice in ("y", "n"):
            return choice == "y"
        print("Invalid input. Please enter 'y' or 'n'.")


def show_pdf_result(status: str, file_name: str | None, folder: str) -> None:
    messages = {
        "exported": f"PDF report saved as '{file_name}' in {folder}",
        "missing_dependency": "PDF export needs the 'reportlab' package: pip install reportlab",
        "invalid_pdf_name": "The PDF file name is not valid, so nothing was exported.",
        "pdf_error": "The PDF report could not be created. Nothing was exported.",
    }
    print(messages.get(status, f"PDF export failed ({status})."))


def wait_for_return() -> None:
    gui.return_button()


def wait_for_continue() -> None:
    gui.continue_button()


# Shown right after login so the user sees their saved history is loaded.
def show_audit_count(count: int) -> None:
    if count:
        print(f"You have {count} saved audit{'s' if count != 1 else ''} (menu option 9).\n")
    else:
        print("You have no saved audits yet. Choose option 1 to start one.\n")


# Messages for a clean exit (main.py cannot print; only this layer does).
def show_interrupted() -> None:
    print("\n\nInterrupted. Goodbye!")


def show_input_ended() -> None:
    print("\n\nNo more input available. If you run the app in Docker, "
          "start it with 'docker run -it ...' so you can type into it.")


# Full view of one saved audit, reusing the existing report layouts.
def display_audit_detail(audit: Record) -> None:
    audit = _as_dict(audit)
    application = _as_dict(audit.get("application"))
    ai_audit = _as_dict(audit.get("ai_audit"))
    result = _as_dict(audit.get("result"))

    print(f"\nAudit #{_as_text(audit.get('audit_id'), '?')} - {_audit_stamp(audit)}")
    if application:
        print_on_paper(format_pairs(application), title="APPLICATION DETAILS")
    if ai_audit:
        display_ai_audit(ai_audit)
    if result:
        try:
            display_grant_decision(result)
        except (KeyError, TypeError, ValueError):
            # Saved decision is missing fields: show what is there instead.
            print_on_paper(format_pairs(result), title="GRANT ELIGIBILITY DECISION")


# Display Company Profile
def display_company_profile(company_name: str, company_industry: str, total_revenue: float, total_employees: int, local_equity: float, proposal_type: str, sustainability_grant: str, proposal_narrative: str, baseline_energy_expenditure: float, estimated_retrofit_cost: float, reporting_advisory_fee: float) -> None:
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

# input of Company's name
COMPANY_NAME_MAX_LEN = 100
NARRATIVE_MAX_LEN = 3000
OTHER_TEXT_MAX_LEN = 60


def retrieve_company_name() -> str:
    while True:
        company_name = input("Enter your Company's Name: ").strip()
        if company_name == "":
            print("Company Name cannot be empty. Please try again.")
        elif len(company_name) > COMPANY_NAME_MAX_LEN:
            print(f"Company Name must be at most {COMPANY_NAME_MAX_LEN} characters. Please try again.")
        else:
            return company_name

# input of Company's industry
def retrieve_company_industry() -> str:
    valid_industries = ["Logistics", "Manufacturing", "Retail", "Food & Beverage", "Healthcare", "Information Technology", "Construction", "Education", "Finance", "Hospitality", "Aerospace", "Others"]

    while True:
        company_industry = input(f"Enter your Company's Industry Sector (choose from {', '.join(valid_industries)}): ").strip().title()

        if company_industry.strip() == "":
            print("Company Industry Sector cannot be empty. Please try again.")
        elif company_industry not in valid_industries:
            print("Invalid. Please select a valid Industry Sector.")
        elif company_industry == "Others":
            return get_valid_other_industry()
        else:
            return company_industry

def get_valid_other_industry() -> str:
    while True:
        other_industry = input("Please specify your Company's Industry Sector: ").strip().title()
        if other_industry == "":
            print("Industry Sector cannot be empty. Please try again.")
        elif len(other_industry) > OTHER_TEXT_MAX_LEN:
            print(f"Industry Sector must be at most {OTHER_TEXT_MAX_LEN} characters.")
        elif not other_industry.replace(" ", "").isalpha():
            print("Invalid. Please provide a valid Industry Sector containing only alphabetic characters.")
        else:
            return other_industry

# Like float(), but also rejects "nan" and "inf", which float() accepts and
# which slip past <= / >= range checks. Raises ValueError like float().
def finite_float(text: Any) -> float | None:
    number = float(text)
    if not math.isfinite(number):
        raise ValueError("number must be finite")
    return number


# input of Company's Total Revenue
def retrieve_total_revenue() -> float:
    while True:
        try:
            total_revenue = finite_float(input("Enter your Company's Total Revenue (in SGD): "))
            if total_revenue < 0:
                print("Total Revenue cannot be negative. Please try again.")
            elif total_revenue == 0:
                print("Total Revenue cannot be zero. Please try again.")
            else:
                return total_revenue
        except ValueError:
            print("Invalid input. Please enter a numeric value for total revenue.")

# input of Company's Total Number of Employees
def retrieve_total_employees() -> int:
    while True:
        try:
            total_employees = int(input("Enter your Company's Total Number of Employees: "))
            if total_employees < 0:
                print("Total Number of Employees cannot be negative. Please try again.")
            elif total_employees == 0:
                print("Total Number of Employees cannot be zero. Please try again.")
            else:
                return total_employees
        except ValueError:
            print("Invalid input. Please enter a numeric value for total number of employees.")

# input of Company's Local Equity
def retrieve_local_equity() -> float:
    while True:
        raw_value = input("Enter equity % owned by Singapore Citizens/PRs: ").strip()
        if raw_value == "":
            print("Equity % cannot be empty. Please try again.")
            continue
        try:
            local_equity = finite_float(raw_value)
            if local_equity <= 0 or local_equity > 100:
                print("Equity % must be a value between 0 and 100. Please try again.")
                continue
            else:
                return local_equity
        except ValueError:
            print("Invalid input. Please enter a numeric value for your local equity.")

# NEW: applicant self-declares which kind of proposal this is, so we
# only collect the cost fields that are actually relevant, and so
# ai_manager.py gets a strong prior instead of guessing purely from
# free-text narrative.
def retrieve_proposal_type() -> str:
    valid_types = {
        "1": "Equipment / Energy Upgrade",
        "2": "ESG Reporting / Advisory",
    }

    while True:
        choice = input('''What type of proposal is this?\n
                1. Equipment / Energy Upgrade (e.g. fleet electrification, HVAC retrofit, lighting)\n
                2. ESG Reporting / Advisory (e.g. inaugural sustainability report, external assurance)\n
                    Enter 1 or 2: ''').strip()

        if choice in valid_types:
            return valid_types[choice]
        else:
            print("Invalid choice. Please enter 1 or 2.")

# Input of Baseline Annual Energy Expenditure
def retrieve_baseline_energy_expenditure() -> float:
    while True:
        raw_value = input("Enter baseline annual energy expenditure (in SGD): ").strip()
        if raw_value == "":
            print("Baseline annual energy expenditure cannot be empty. Please try again.")
            continue
        try:
            baseline_energy_expenditure = finite_float(raw_value)
            if baseline_energy_expenditure <= 0:
                print("Baseline annual energy expenditure cannot be zero or negative. Please try again.")
                continue
            else:
                return baseline_energy_expenditure
        except ValueError:
            print("Invalid input. Please enter a numeric value for baseline annual energy expenditure.")

# Input of Estimated Retrofit Cost
def retrieve_estimated_retrofit_cost() -> float:
    while True:
        raw_value = input("Enter estimated retrofit cost (in SGD): ").strip()
        if raw_value == "":
            print("Estimated retrofit cost cannot be empty. Please try again.")
            continue
        try:
            estimated_retrofit_cost = finite_float(raw_value)
            if estimated_retrofit_cost <= 0:
                print("Estimated retrofit cost cannot be zero or negative. Please try again.")
                continue
            else:
                return estimated_retrofit_cost
        except ValueError:
            print("Invalid input. Please enter a numeric value for estimated retrofit cost.")

# NEW: free-text description of the proposed upgrade. This is the raw
# narrative ai_manager.py needs in order to classify GHG scope, detect
# exclusion keywords, and estimate abatement — currently nothing in
# main.py or io_manager.py collects this at all.
def retrieve_proposal_narrative() -> str:
    print("Describe your proposed sustainability/energy upgrade in your own words.")
    print("(e.g. what equipment is being replaced, the fuel/energy source involved,")
    print(" and whether any components are second-hand, refurbished, or modified.)")
    while True:
        narrative = input("Proposal Description: ").strip()
        if narrative == "":
            print("Proposal description cannot be empty. Please try again.")
        elif len(narrative) > NARRATIVE_MAX_LEN:
            print(f"Please keep the description under {NARRATIVE_MAX_LEN} characters "
                  f"(yours has {len(narrative)}).")
        else:
            return narrative

# Input of Reporting/Advisory Fee (only collected for ESG Reporting / Advisory proposals)
def retrieve_reporting_advisory_fee() -> float:
    while True:
        raw_value = input("Enter estimated external ESG reporting/advisory fee (in SGD): ").strip()
        if raw_value == "":
            print("Reporting/advisory fee cannot be empty. Please try again.")
            continue
        try:
            reporting_advisory_fee = finite_float(raw_value)
            if reporting_advisory_fee < 0:
                print("Reporting/advisory fee cannot be negative. Please try again.")
                continue
            else:
                return reporting_advisory_fee
        except ValueError:
            print("Invalid input. Please enter a numeric value for the reporting/advisory fee.")

# Sustainability Grant that Company's want to apply
def retrieve_sustainability_grant() -> str:
    valid_grants = ['1. Energy Efficiency Grant (EEG) -Base Tier', '2. Energy Efficiency Grant (EEG) -Advanced Tier', '3. Enterprise Development Grant (EDG)', '4. Sustainability Reporting Programme (SRP)', '5. Others']
    while True:
        print('\nWhich Sustainability Grant would your company like to apply for?')
        for grant in valid_grants:
            print(grant)

        grant_choice = input("Enter the number corresponding to your choice (1-5): ").strip()

        if grant_choice == "":
            print("Sustainability Grant choice cannot be empty. Please select a valid option from 1 to 5.")
            continue
        
        if grant_choice not in ['1', '2', '3', '4', '5']:
            print("Invalid choice. Please select a valid option (1-5).")
            continue


        if grant_choice == '5':
            while True:
                other_grant = input("Please specify the Sustainability Grant that is not stated in the options: ").strip()
                if other_grant == "":
                    print("Sustainability Grant cannot be empty. Please provide a valid grant name.")
                elif len(other_grant) > OTHER_TEXT_MAX_LEN:
                    print(f"Grant name must be at most {OTHER_TEXT_MAX_LEN} characters.")
                elif not other_grant.replace(" ", "").isalpha():
                    print("Invalid input. Please enter a valid grant name.")
                else:
                    other_grant = other_grant
                    return other_grant
        
        else:
                selected_grant = valid_grants[int(grant_choice) - 1]
                return selected_grant

# For displaying list of grants already applied for by the company
# Records loaded from a file can be in the newer nested layout
# (company_profile / proposal / ...) or be missing fields. This turns any
# record into the flat, capitalised layout the screens and main.py use, so
# a file that doesn't match exactly shows "N/A" instead of crashing.
def flat_record(record: Any) -> Record:
    if not isinstance(record, dict):
        return {}
    if isinstance(record.get("company_profile"), dict):
        return audit_record_to_display_format(record)
    return record


def _section(record: Any, name: str) -> dict[str, Any]:
    section = record.get(name)
    return section if isinstance(section, dict) else {}


def audit_record_to_display_format(audit_record: Record) -> Record:
    """Turns a saved (nested) audit record into the capitalised keys the
    screens use, so records loaded from JSON are listed exactly like the
    ones entered in this session."""
    profile = _section(audit_record, "company_profile")
    return {
        "Company Name": profile.get("company_name", ""),
        "Company Industry": profile.get("company_industry", ""),
        "Company Total Revenue": profile.get("annual_revenue_sgd", 0.0),
        "Total Employees": profile.get("group_employment_size", 0),
        "Local Equity": profile.get("local_shareholding_pct", 0.0),
        "Proposal Type": profile.get("proposal_type", ""),
        "Sustainability Grant": profile.get("sustainability_grant", ""),
        "Proposal Narrative": _section(audit_record, "proposal").get("raw_narrative", ""),
        "Baseline Energy Expenditure": profile.get("baseline_annual_energy_expenditure_sgd", 0.0),
        "Estimated Retrofit Cost": profile.get("estimated_retrofit_cost_sgd", 0.0),
        "Reporting Advisory Fee": profile.get("reporting_advisory_fee_sgd", 0.0),
    }


def display_applied_grants(scheme_grant_records: Records, key: int) -> Records | None:
    red = "\033[91m"
    reset = "\033[0m"

    if len(scheme_grant_records) == 0:
        print(f"\n {red}⚠️  SYSTEM NOTICE: You do not have any grants applied.{reset}\n")
        gui.return_button()
        return

    # Build the paper contents: one block per grant
    lines = []
    for i, grant in enumerate(scheme_grant_records, start=1):
        grant = flat_record(grant)
        if i > 1:
            lines.append("")
        lines.append(f"{i}. {grant.get('Company Name', 'N/A')} - {grant.get('Company Industry', 'N/A')}")
        details = {
            "Total Revenue": grant.get("Company Total Revenue", "N/A"),
            "Total Employees": grant.get("Total Employees", "N/A"),
            "Local Equity": grant.get("Local Equity", "N/A"),
            "Proposal Type": grant.get("Proposal Type", "N/A"),
            "Proposal Narrative": grant.get("Proposal Narrative", "N/A"),
            "Sustainability Grant": grant.get("Sustainability Grant", "N/A"),
            "Baseline Energy Expenditure": grant.get("Baseline Energy Expenditure", "N/A"),
            "Estimated Retrofit Cost": grant.get("Estimated Retrofit Cost", "N/A"),
            "Reporting Advisory Fee": grant.get("Reporting Advisory Fee", 0.0),
        }
        lines.extend(format_pairs(details, indent="   "))

    count = len(scheme_grant_records)
    footer = f"{count} record{'s' if count != 1 else ''}"

    if key == 1:
        print_on_paper(lines, title="SCHEME GRANT RECORDS", footer=footer)
        gui.ai_button()
    elif key in (4, 5, 6):
        print_on_paper(lines, title="GRANTS ALREADY APPLIED FOR", footer=footer)
        if key == 4:
            gui.return_button()

    return scheme_grant_records

# Bridges main.py's case-1 record format (capitalised, display-oriented
# keys, built one company at a time into scheme_grant_records) onto the
# snake_case keys logic_manager.py's evaluate_grant_application()
# actually reads. main.py's case 1 now stores Proposal Type and
# Reporting Advisory Fee directly on the record, so no extra
# parameters are needed here.
def convert_record_to_profile(record: Record) -> dict[str, Any]:
    record = flat_record(record)
    return {
        "company_name": record.get("Company Name", ""),
        "company_industry": record.get("Company Industry", ""),
        "annual_revenue_sgd": record.get("Company Total Revenue", 0.0),
        "group_employment_size": record.get("Total Employees", 0),
        "local_shareholding_pct": record.get("Local Equity", 0.0),
        "proposal_type": record.get("Proposal Type", "Equipment / Energy Upgrade"),
        "sustainability_grant":  record.get("Sustainability Grant", "Not Specified"),
        "baseline_annual_energy_expenditure_sgd": record.get("Baseline Energy Expenditure", 0.0),
        "estimated_retrofit_cost_sgd": record.get("Estimated Retrofit Cost", 0.0),
        "reporting_advisory_fee_sgd": record.get("Reporting Advisory Fee", 0.0),
    }


# Y/N confirmation for whether to save the just-processed record to
# JSON, used right after the automated AI + Logic audit in main.py.
# io_manager.py

# Asks for a save/load file name using the floppy-disk label prompt.
# Re-prompts until a non-empty name is entered.
def retrieve_json_filename(blocked_chars: str = "", *args: Any) -> str:
    """blocked_chars: characters the typed name may not contain (supplied
    by main.py from the Data Manager, which owns the file-name rules).
    Extra args are passed on to the disk prompt; a first value of 3 shows
    the 'load' disk instead of the 'save' disk."""
    while True:
        if sys.stdin.isatty():
            name = prompt_filename_on_disk(
                *args,
                max_len=50,
                blocked=blocked_chars,
            )
        else:
            name = input("Enter JSON file name (e.g. grants): ").strip()
        if name:
            return name
        print("File name cannot be empty. Please try again.")


def confirm_overwrite_records() -> bool:
    while True:
        choice = input("This will replace the records currently in memory. Continue? (y/n): ").strip().lower()
        if choice == "y":
            return True
        if choice == "n":
            return False
        print("Invalid input. Please enter 'y' or 'n'.")


def ask_existing_file_action(file_name: str) -> str:
    """The file already exists: returns "add", "replace" or "cancel"."""
    while True:
        choice = input(
            f"'{file_name}' already exists. "
            "(a = add to it, r = replace it, c = cancel): "
        ).strip().lower()
        if choice in ("a", "r", "c"):
            return {"a": "add", "r": "replace", "c": "cancel"}[choice]
        print("Invalid input. Please enter 'a', 'r' or 'c'.")


def display_save_result(status: str | None, file_name: str) -> None:
    messages = {
        "saved": f"Data successfully saved to {file_name}.",
        "no_name": "No file name was given.",
        "invalid_name": "That file name contains illegal characters.",
        "io_error": "The file could not be written.",
    }
    print(messages.get(status, f"Unknown save status: {status}"))
    if status == "saved":
        print(gui.save_disk_block_deep_blue())


def display_load_result(status: str, file_name: str) -> None:
    messages = {
        "loaded": f"Records loaded successfully from {file_name}.",
        "no_name": "No file name was given.",
        "invalid_name": "That file name contains illegal characters.",
        "not_found": f"File '{file_name}' was not found.",
        "invalid_json": "The file is corrupt or unreadable. It was set aside as a .corrupt backup.",
        "invalid_format": "The file is valid JSON but not a list of audit records. It was set aside.",
        "io_error": "The operating system refused to read the file.",
    }
    print(messages.get(status, f"Unknown load status: {status}"))


def confirm_save_to_json() -> bool:
    art, regions = gui.yes_no_buttons("Save this record to JSON now?")
    return execute_choice_interaction(art, regions, {"y": True, "n": False})

# Shows the floppy disk and lets the user type the file name on its label.
def prompt_filename_on_disk(*args: Any, max_len: int = 50, blocked: str = "") -> str:
    key = args[0] if args else None   # first extra value, or None if nothing was passed

    if key == 3: #When loading the file
        art, rows_up, col = gui.load_disk_prompt_art(max_len=max_len)
    else: #When saving the file
        art, rows_up, col = gui.save_disk_prompt_art(max_len=max_len)
    print(art)

    # Jump back up into the label and start typing there
    sys.stdout.write(f"\033[{rows_up}A\033[{col}G{gui.LABEL}")
    sys.stdout.flush()
    try:
        return read_limited(max_len, blocked).strip()
    finally:
        # Reset colours and move back below the disk
        # (no newline is echoed now, so move down the full rows_up)
        sys.stdout.write(f"{gui.RESET}\033[{rows_up}B\r")
        sys.stdout.flush()
        
# Enables paper format
#So it looks abit like you are reading your work on paper while also looking at a command console
PAPER_WIDTH = 110


def print_on_paper(lines: list[str], title: str = "REPORT", footer: str = "End of report", width: int = PAPER_WIDTH) -> None:
    """Print a list of text lines inside a paper-style frame."""
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


def format_pairs(data: Any, width: int = PAPER_WIDTH, indent: str = "") -> list[str]:
    """Turn a dict into aligned 'key : value' lines with a hanging indent."""
    inner = width - 4 - len(indent)
    key_w = max(len(str(k)) for k in data)
    lines = []
    for key, value in data.items():
        label = f"{str(key):<{key_w}} : "
        hang = " " * len(label)
        wrapped = textwrap.wrap(str(value), width=inner - len(label)) or [""]
        lines.append(indent + label + wrapped[0])
        lines.extend(indent + hang + extra for extra in wrapped[1:])
    return lines

# Renders the AI Manager's structured output for the CLI. All console
# print statements in the codebase belong in io_manager.py per the
# architecture, so ai_manager.py and logic_manager.py never print
# directly — they just return data for this layer to display.
def display_ai_audit(ai_audit: AiAudit) -> None:
    print_on_paper(format_pairs(ai_audit), title="AI AUDIT REPORT")

# Runs whenever AI Manager is using the get_ai_response() function. It gives one bar for every second passed
def run_ai_analysis_bar(stop_event: threading.Event, timeout_seconds: int = 60) -> None:
    """
    Animates the progress bar. Stops instantly if stop_event is flagged 
    or when it hits the maximum timeout.
    """
    cyan = "\033[96m"
    reset = "\033[0m"
    
    print("\nAnalysing your proposal with the AI Manager, please wait...\n")
    sys.stdout.write("\033[?25l")  # Hide text cursor
    sys.stdout.flush()
    
    try:
        # Loop for the maximum allowed duration
        for i in range(1, timeout_seconds + 1):
            # Check if the API background thread has finished and flagged us to stop
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


# Renders the Logic Manager's decision for the CLI.
def display_grant_decision(result: dict[str, Any]) -> None:
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
    print_on_paper(lines, title="GRANT ELIGIBILITY DECISION")

# When there is no records
# ---------- Menu options 5 and 6: pick, edit and delete records ----------

# Field name -> the prompt that asks for it (same checks as when the record
# was first entered).
FIELD_PROMPTS = {
    "Company Name": retrieve_company_name,
    "Company Industry": retrieve_company_industry,
    "Company Total Revenue": retrieve_total_revenue,
    "Total Employees": retrieve_total_employees,
    "Local Equity": retrieve_local_equity,
    "Sustainability Grant": retrieve_sustainability_grant,
    "Proposal Narrative": retrieve_proposal_narrative,
    "Baseline Energy Expenditure": retrieve_baseline_energy_expenditure,
    "Estimated Retrofit Cost": retrieve_estimated_retrofit_cost,
    "Reporting Advisory Fee": retrieve_reporting_advisory_fee,
}

COMMON_FIELDS = (
    "Company Name", "Company Industry", "Company Total Revenue",
    "Total Employees", "Local Equity", "Sustainability Grant", "Proposal Narrative",
)


def fields_for(record: Record) -> tuple[str, ...]:
    """The fields that make sense for this record: equipment proposals have
    a baseline spend and retrofit cost, reporting proposals have a fee."""
    if flat_record(record).get("Proposal Type") == "ESG Reporting / Advisory":
        return COMMON_FIELDS + ("Reporting Advisory Fee",)
    return COMMON_FIELDS + ("Baseline Energy Expenditure", "Estimated Retrofit Cost")


def _choose_number(prompt: str, highest: int) -> int | None:
    """Asks for a whole number from 0 to highest. Returns None if invalid."""
    answer = key_verifier(input(prompt), max_digits=len(str(highest)))
    if answer is None or answer > highest:
        return None
    return answer


def select_record_index(records: Records, action: str) -> int | None:
    """Lists the records and asks which to `action` ("update"/"delete").
    Returns the 0-based index, or None if the user cancels."""
    print(f"\nWhich record do you want to {action}?")
    for number, record in enumerate(records, start=1):
        record = flat_record(record)
        print(f"  {number}. {record.get('Company Name') or 'N/A'}"
              f"  ({record.get('Proposal Type') or 'N/A'})")
    print("  0. Cancel")

    while True:
        number = _choose_number(f"Enter 0-{len(records)}: ", len(records))
        if number is None:
            print(f"Please enter a number from 0 to {len(records)}.")
        elif number == 0:
            return None
        else:
            return number - 1


def select_field_to_edit(record: Record) -> str | None:
    """Asks which field of `record` to change. Returns the field name or None."""
    fields = fields_for(record)
    flat = flat_record(record)
    print("\nWhich detail do you want to change?")
    for number, field in enumerate(fields, start=1):
        value = str(flat.get(field, "N/A"))
        shortened = value if len(value) <= 40 else value[:37] + "..."
        print(f"  {number}. {field}: {shortened}")
    print("  0. Cancel")

    while True:
        number = _choose_number(f"Enter 0-{len(fields)}: ", len(fields))
        if number is None:
            print(f"Please enter a number from 0 to {len(fields)}.")
        elif number == 0:
            return None
        else:
            return fields[number - 1]


def retrieve_field_value(field: str) -> Any:
    """Prompts for a new value of `field` with the original validation."""
    return FIELD_PROMPTS[field]()


def confirm_delete_record(company_name: str) -> bool:
    while True:
        choice = input(f"Delete the record for '{company_name}'? (y/n): ").strip().lower()
        if choice in ("y", "n"):
            return choice == "y"
        print("Invalid input. Please enter 'y' or 'n'.")


def show_record_updated(company_name: str, field: str) -> None:
    print(f"Updated '{field}' for '{company_name}'. Use option 2 to save the change.")
    gui.return_button()


def show_record_deleted(company_name: str) -> None:
    print(f"Deleted the record for '{company_name}'. "
          "Use option 2 (choose replace) to remove it from a saved file too.")
    gui.return_button()


def show_record_not_changed() -> None:
    print("Nothing was changed.")
    gui.return_button()


def display_no_records_message() -> None:
    print("No records yet. Please select option 1 first.")
    gui.return_button()

# When AI hasn't yet audited the machine. The AI will audit right after finishing the input for the company grant so it only activates in practice when no data exists
def display_no_ai_audit() -> None:
    print("No AI audit yet. Please run option 7 first.")
    gui.return_button()

# ASCII related
# io_manager.py
def show_wrong_option_error() -> None:
    print(gui.wrong_sign_red())
    gui.return_button()

# 
def show_goodbye() -> None:
    print(gui.goodbye_art())
