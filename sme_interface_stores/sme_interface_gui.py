"""Screen art for the terminal: menus, banners and floppy-disk prompts.

    InterfaceArt   builds art as plain strings (it never prints or reads keys)


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


class InterfaceArt:
    """Every picture and layout the app can show, as strings."""

    BLUE = BLUE
    LABEL = LABEL
    RESET = RESET

    @staticmethod
    def tile_frame(content: str, tile: str, gap: str = " ") -> str:
        """Surround `content` (multi-line string) with a border made of `tile`."""
        lines = textwrap.dedent(content).strip("\n").splitlines()
        lines = [line for line in lines if line.strip()]

        # Width of the box, measured from its plain top border (no colours/emoji)
        box_w = len(ANSI.sub("", lines[0]))
        tw, gw = len(tile), len(gap)

        # Smallest tile count whose inner area fits the box
        cols = 2
        while cols * tw + (cols - 1) * gw - 2 * (tw + gw) < box_w:
            cols += 1

        total = cols * tw + (cols - 1) * gw
        inner = total - 2 * (tw + gw)
        pad_l = (inner - box_w) // 2
        pad_r = inner - box_w - pad_l

        edge = gap.join([tile] * cols)  # top / bottom row
        blank = f"{tile}{gap}{' ' * inner}{gap}{tile}"  # breathing room

        out = [edge, blank]
        for line in lines:
            out.append(f"{tile}{gap}{' ' * pad_l}{line}{' ' * pad_r}{gap}{tile}")
        out += [blank, edge]
        return "\n".join(out)

    @staticmethod
    def yes_no_buttons(question: str, btn_w: int = 12, gap: int = 4, indent: int = 4):
        """Boxed yes/no prompt. Returns (art, regions).
        regions maps True/False to the (min_x, max_x) columns of each button."""
        green, red, grey, reset = "\033[92m", "\033[91m", "\033[90m", "\033[0m"
        hint = "[Y] Yes    [N] No    or click a button"
        total = 2 * btn_w + gap
        inner = max(len(question), len(hint), total) + 6

        def row(plain="", styled=None):
            pad = inner - len(plain)
            left = pad // 2
            return (
                " " * indent
                + "│"
                + " " * left
                + (styled or plain)
                + " " * (pad - left)
                + "│"
            )

        def button(label, part):
            parts = {
                "top": "┌" + "─" * (btn_w - 2) + "┐",
                "mid": "│" + label.center(btn_w - 2) + "│",
                "bot": "└" + "─" * (btn_w - 2) + "┘",
            }
            return parts[part]

        lines = [" " * indent + "┌" + "─" * inner + "┐", row(), row(question), row()]
        for part in ("top", "mid", "bot"):
            yes, no = button("YES", part), button("NO", part)
            plain = yes + " " * gap + no
            styled = f"{green}{yes}{reset}" + " " * gap + f"{red}{no}{reset}"
            lines.append(row(plain, styled))
        lines += [
            row(),
            row(hint, f"{grey}{hint}{reset}"),
            row(),
            " " * indent + "└" + "─" * inner + "┘",
        ]

        # Button columns (1-based, matching the terminal's mouse reports)
        pad_l = (inner - total) // 2
        yes_start = indent + 1 + pad_l + 1
        no_start = yes_start + btn_w + gap
        regions = {
            True: (yes_start, yes_start + btn_w - 1),
            False: (no_start, no_start + btn_w - 1),
        }
        return "\n" + "\n".join(lines) + "\n", regions

    @staticmethod
    def wrong_sign_red() -> str:
        red_start = "\033[91m"
        color_reset = "\033[0m"

        x_art = r"""
      ____    ____
      \   \  /   /
       \   \/   /
        \      /
        /      \
       /   /\   \
      /___/  \___\
    """

        return red_start + x_art + color_reset + "Error! Unrecognised number option"

    @staticmethod
    def face_paintscheme() -> str:
        return art_lookup("woman")  # a single tile, e.g. ▓⚗_⚗▓

    @staticmethod
    def hello() -> str:
        return text2art("Hello", font="block", chr_ignore=True)

    @staticmethod
    def goodbye_art() -> str:
        return text2art("Goodbye", font="rnd-xlarge")

    @staticmethod
    def _disk_prompt_art(title: str, prompt: str, max_len: int):
        """Floppy disk with an input slot sized to fit max_len characters."""
        w = len(prompt) + max_len  # label/shutter width
        inner = w + 4
        body = inner + 4

        def label_row(text=""):
            return f"  {BLUE}██{RESET}  {LABEL}{text:<{w}}{RESET}  {BLUE}██ █{RESET}"

        lines = [
            f"  {BLUE}{'█' * body}▀▄{RESET}",
            f"  {BLUE}{'█' * body} █{RESET}",
            f"  {BLUE}██{RESET}  {'▀' * w}  {BLUE}██ █{RESET}",
            f"  {BLUE}██{RESET}  {'█' * w}  {BLUE}██ █{RESET}",
            f"  {BLUE}██{RESET}  {'█' * w}  {BLUE}██ █{RESET}",
            f"  {BLUE}██{' ' * inner}██ █{RESET}",
            label_row(title.center(w)),
            label_row(prompt),  # <- input row (index 7)
            label_row(),
            f"  {BLUE}{'█' * body}▀{RESET}",
            f"   {BLUE}{'▀' * (body + 1)}{RESET}",
        ]

        input_row = 7
        rows_up = len(lines) - input_row
        col = 7 + len(prompt)
        return "\n".join(lines), rows_up, col

    @classmethod
    def save_disk_prompt_art(cls, prompt: str = " Name: ", max_len: int = 50):
        return cls._disk_prompt_art(f"SAVE TO DISK or click enter to return (max {max_len} chars)", prompt, max_len)

    @classmethod
    def load_disk_prompt_art(cls, prompt: str = " Name: ", max_len: int = 50):
        return cls._disk_prompt_art(
            f"LOAD FROM DISC or click enter to return (max {max_len} chars)", prompt, max_len
        )

    @staticmethod
    def save_disk_block_deep_blue() -> str:
        blue = "\033[34m"  # Deep classic blue
        white = "\033[97m"  # Crisp white for contrast
        reset = "\033[0m"  # Reset formatting

        disk_art = f"""
  {blue}█████████████████████████▀▄{reset}
  {blue}█████████████████████████ █{reset}
  {blue}██{reset}  ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀ {blue}██ █{reset}
  {blue}██{reset}  █████████████████  {blue}██ █{reset}
  {blue}██{reset}  █████████████████  {blue}██ █{reset}
  {blue}██                     ██ █{reset}
  {blue}██       {white}███████{blue}       ██ █{reset}
  {blue}██       {white}██   ██{blue}       ██ █{reset}
  {blue}█████████████████████████▀{reset} 
   {blue}▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀{reset}  
"""
        return disk_art

    @staticmethod
    def boxed_menu(username: str | None = None) -> str:
        border = "▓⚗_⚗▓ " * 10
        blank = "▓" + " " * 57 + "▓"

        def row(text):
            return "▓" + text.ljust(57) + "▓"

        lines = [
            border,
            blank,
            row("    Please select your choice (0-10)"),
            blank,
            row("    0. Exit"),
            row("    1. Start"),
            row("    2. Save to JSON"),
            row("    3. Pull from JSON"),
            row("    4. Display Current Records"),
            row("    5. Update Records"),
            row("    6. Delete Records"),
            row("    7. Run AI Manager (only)"),
            row("    8. Run Logic Manager (only)"),
            row("    9. View My Past Audits"),
            row("   10. Logout"),
            blank,
        ]
        if username:
            lines.append(row(f"    Logged in as: {username}"))
            lines.append(blank)
        lines.append(border)
        return "\n".join(lines)

    @staticmethod
    def sustainability_banner() -> str:
        # Terminal Colors: \033[92m = Eco Green, \033[91m = Warning Red, \033[0m = Reset
        green = "\033[92m"
        red = "\033[91m"
        reset = "\033[0m"

        banner = f"""
    ┌──────────────────────────────────────────────────┐
    │                                                  │
    │                   {green}Welcome to:                    {reset}│
    │                                                  │
    │{green}🌱 SME Green Sustainability Eligibility Scheme 🌱{reset} │
    ├──────────────────────────────────────────────────┤
    │                                                  │
    │   For the purposes of determining eligibility    │
    │  to the SME Green Grant and assessing compliance.│
    │                                                  │
    │   {red}⚠️ WARNING: This application is experimental.   {reset}│
    │                                                  │
    └──────────────────────────────────────────────────┘
    """
        return banner

    @classmethod
    def framed_sustainability_banner(cls) -> str:
        tile = cls.face_paintscheme().strip()
        return cls.tile_frame(cls.sustainability_banner(), tile)


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
