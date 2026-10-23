"""Visual design for the terminal interface.

Every class here only BUILDS text. Nothing prints or reads input; the
I/O Manager does that."""

import re
import textwrap
from abc import ABC, abstractmethod

from art import art as ascii_art
from art import text2art

ANSI = re.compile(r"\033\[[0-9;]*m")


# ========================================================
# Palette: one place for every colour code
# ========================================================
class Palette:
    RESET = "\033[0m"
    BLUE = "\033[34m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    GOLD = "\033[93m"
    CYAN = "\033[96m"
    GREY = "\033[90m"
    WHITE = "\033[97m"
    LABEL = "\033[30;107m"  # black text on a bright white label


# ========================================================
# Buttons: abstract base + three specialisations
# ========================================================
class Button(ABC):
    """A clickable box. Subclasses only say WHAT it shows and its colour."""

    WIDTH = 26
    BOUNDS = (5, 35)  # clickable columns

    @property
    @abstractmethod
    def label(self) -> str: ...

    @property
    @abstractmethod
    def colour(self) -> str: ...

    @property
    def bounds(self) -> tuple[int, int]:
        return self.BOUNDS

    def render(self) -> str:
        c, s, r = self.colour, Palette.GREY, Palette.RESET
        return f"""
     ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
    █  {c}┌──────────────────────────┐{r}  █
    █  {c}│{self.label:<{self.WIDTH}}│{r}  █▀▄
    █  {c}└──────────────────────────┘{r}  █ █
    ▀████████████████████████████████▀  █
      {s}▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀{r}
    """


class ContinueButton(Button):
    label = "⮞ PRESS ENTER TO CONTINUE"
    colour = Palette.GOLD


class ReturnButton(Button):
    label = " ⮪  CLICK OR ENTER RETURN"
    colour = Palette.CYAN


class AiButton(Button):
    label = "⮞ START AI ANALYSIS"
    colour = Palette.GREEN


class YesNoDialog:
    """Boxed yes/no prompt. render() returns (art, regions), where regions
    maps True/False to the (min_x, max_x) columns of each button."""

    def __init__(self, question: str, btn_w: int = 12, gap: int = 4, indent: int = 4):
        self._question = question
        self._btn_w = btn_w
        self._gap = gap
        self._indent = indent

    def render(self):
        g, rd, grey, r = Palette.GREEN, Palette.RED, Palette.GREY, Palette.RESET
        w, gap, indent = self._btn_w, self._gap, self._indent
        hint = "[Y] Yes    [N] No    or click a button"
        total = 2 * w + gap
        inner = max(len(self._question), len(hint), total) + 6

        def row(plain="", styled=None):
            pad = inner - len(plain)
            left = pad // 2
            return " " * indent + "│" + " " * left + (styled or plain) + " " * (pad - left) + "│"

        def part(label, kind):
            return {
                "top": "┌" + "─" * (w - 2) + "┐",
                "mid": "│" + label.center(w - 2) + "│",
                "bot": "└" + "─" * (w - 2) + "┘",
            }[kind]

        lines = [" " * indent + "┌" + "─" * inner + "┐", row(), row(self._question), row()]
        for kind in ("top", "mid", "bot"):
            yes, no = part("YES", kind), part("NO", kind)
            lines.append(row(yes + " " * gap + no, f"{g}{yes}{r}" + " " * gap + f"{rd}{no}{r}"))
        lines += [row(), row(hint, f"{grey}{hint}{r}"), row(), " " * indent + "└" + "─" * inner + "┘"]

        yes_start = indent + 1 + (inner - total) // 2 + 1
        no_start = yes_start + w + gap
        regions = {True: (yes_start, yes_start + w - 1), False: (no_start, no_start + w - 1)}
        return "\n" + "\n".join(lines) + "\n", regions


# ========================================================
# Floppy-disk prompts: one template, two titles
# ========================================================
class DiskPrompt(ABC):
    """Floppy disk with an input slot sized for max_len characters."""

    def __init__(self, prompt: str = " Name: ", max_len: int = 50):
        self._prompt = prompt
        self._max_len = max_len

    @property
    @abstractmethod
    def title(self) -> str: ...

    def render(self):
        """Returns (art, rows_up, col) so the I/O Manager can place the cursor."""
        b, r, label = Palette.BLUE, Palette.RESET, Palette.LABEL
        w = len(self._prompt) + self._max_len
        inner = w + 4
        body = inner + 4

        def label_row(text=""):
            return f"  {b}██{r}  {label}{text:<{w}}{r}  {b}██ █{r}"

        lines = [
            f"  {b}{'█' * body}▀▄{r}",
            f"  {b}{'█' * body} █{r}",
            f"  {b}██{r}  {'▀' * w}  {b}██ █{r}",
            f"  {b}██{r}  {'█' * w}  {b}██ █{r}",
            f"  {b}██{r}  {'█' * w}  {b}██ █{r}",
            f"  {b}██{' ' * inner}██ █{r}",
            label_row(f"{self.title} (max {self._max_len} chars)".center(w)),
            label_row(self._prompt),  # input row (index 7)
            label_row(),
            f"  {b}{'█' * body}▀{r}",
            f"   {b}{'▀' * (body + 1)}{r}",
        ]
        return "\n".join(lines), len(lines) - 7, 7 + len(self._prompt)


class SaveDiskPrompt(DiskPrompt):
    title = "SAVE TO DISK"


class LoadDiskPrompt(DiskPrompt):
    title = "LOAD FROM DISK"


# ========================================================
# Helper: draws a border of tiles around a block of text
# ========================================================
class TileFramer:
    @staticmethod
    def wrap(content: str, tile: str, gap: str = " ") -> str:
        lines = [l for l in textwrap.dedent(content).strip("\n").splitlines() if l.strip()]
        box_w = len(ANSI.sub("", lines[0]))
        tw, gw = len(tile), len(gap)

        cols = 2
        while cols * tw + (cols - 1) * gw - 2 * (tw + gw) < box_w:
            cols += 1

        total = cols * tw + (cols - 1) * gw
        inner = total - 2 * (tw + gw)
        pad_l = (inner - box_w) // 2
        pad_r = inner - box_w - pad_l

        edge = gap.join([tile] * cols)
        blank = f"{tile}{gap}{' ' * inner}{gap}{tile}"
        out = [edge, blank]
        out += [f"{tile}{gap}{' ' * pad_l}{l}{' ' * pad_r}{gap}{tile}" for l in lines]
        out += [blank, edge]
        return "\n".join(out)


# ========================================================
# Renderer: the interface the I/O Manager talks to
# ========================================================
class Renderer(ABC):
    """Contract for every look the program can have. Each method RETURNS text."""

    @abstractmethod
    def hello(self) -> str: ...

    @abstractmethod
    def goodbye(self) -> str: ...

    @abstractmethod
    def welcome_banner(self) -> str: ...

    @abstractmethod
    def menu(self, username: str | None = None) -> str: ...

    @abstractmethod
    def wrong_option_error(self) -> str: ...

    @abstractmethod
    def saved_icon(self) -> str: ...

    @abstractmethod
    def button_art(self, button: Button) -> str: ...

    @abstractmethod
    def disk_prompt(self, mode: str, max_len: int = 50): ...

    @abstractmethod
    def yes_no(self, question: str): ...


class AnsiRenderer(Renderer):
    """Full colour and art. Plain terminals extend it (see below)."""

    def __init__(self):
        # Composition: the renderer owns its buttons for its whole life.
        self._continue = ContinueButton()
        self._return = ReturnButton()
        self._ai = AiButton()

    # -- hook that subclasses override --------------------------------
    def _finish(self, text: str) -> str:
        return text

    # -- buttons ------------------------------------------------------
    @property
    def continue_button(self) -> Button:
        return self._continue

    @property
    def return_button(self) -> Button:
        return self._return

    @property
    def ai_button(self) -> Button:
        return self._ai

    def button_art(self, button: Button) -> str:
        return self._finish(button.render())

    # -- styles the I/O Manager needs when typing on a disk label -----
    @property
    def label_style(self) -> str:
        return self._finish(Palette.LABEL)

    @property
    def reset_style(self) -> str:
        return self._finish(Palette.RESET)

    # -- screens ------------------------------------------------------
    def hello(self) -> str:
        return text2art("Hello", font="block", chr_ignore=True)

    def goodbye(self) -> str:
        return text2art("Goodbye", font="rnd-xlarge")

    def welcome_banner(self) -> str:
        g, rd, r = Palette.GREEN, Palette.RED, Palette.RESET
        return self._finish(f"""
    ┌──────────────────────────────────────────────────┐
    │                                                  │
    │                   {g}Welcome to:                    {r}│
    │                                                  │
    │{g}🌱 SME Green Sustainability Eligibility Scheme 🌱{r} │
    ├──────────────────────────────────────────────────┤
    │                                                  │
    │   For the purposes of determining eligibility    │
    │  to the SME Green Grant and assessing compliance.│
    │                                                  │
    │   {rd}⚠️ WARNING: This application is experimental.   {r}│
    │                                                  │
    └──────────────────────────────────────────────────┘
    """)

    def framed_welcome_banner(self) -> str:
        tile = ascii_art("woman").strip()
        return TileFramer.wrap(self.welcome_banner(), tile)

    def menu(self, username: str | None = None) -> str:
        border = "▓⚗_⚗▓ " * 10
        blank = "▓" + " " * 57 + "▓"

        def row(text):
            return "▓" + text.ljust(57) + "▓"

        lines = [
            border, blank,
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
            lines += [row(f"    Logged in as: {username}"), blank]
        lines.append(border)
        return "\n".join(lines)

    def wrong_option_error(self) -> str:
        x_art = r"""
      ____    ____
      \   \  /   /
       \   \/   /
        \      /
        /      \
       /   /\   \
      /___/  \___\
    """
        return self._finish(Palette.RED + x_art + Palette.RESET + "Error! Unrecognised number option")

    def saved_icon(self) -> str:
        b, w, r = Palette.BLUE, Palette.WHITE, Palette.RESET
        return self._finish(f"""
  {b}█████████████████████████▀▄{r}
  {b}█████████████████████████ █{r}
  {b}██{r}  ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀ {b}██ █{r}
  {b}██{r}  █████████████████  {b}██ █{r}
  {b}██{r}  █████████████████  {b}██ █{r}
  {b}██                     ██ █{r}
  {b}██       {w}███████{b}       ██ █{r}
  {b}██       {w}██   ██{b}       ██ █{r}
  {b}█████████████████████████▀{r}
   {b}▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀{r}
""")

    # -- prompts ------------------------------------------------------
    def disk_prompt(self, mode: str, max_len: int = 50):
        prompt = LoadDiskPrompt(max_len=max_len) if mode == "load" else SaveDiskPrompt(max_len=max_len)
        art_text, rows_up, col = prompt.render()
        return self._finish(art_text), rows_up, col

    def yes_no(self, question: str):
        art_text, regions = YesNoDialog(question).render()
        return self._finish(art_text), regions


class PlainRenderer(AnsiRenderer):
    """Same screens with the colour codes removed, for Docker logs, CI or
    terminals without ANSI support. Only one method is overridden."""

    def _finish(self, text: str) -> str:
        return ANSI.sub("", text)


def create_renderer(plain: bool = False) -> Renderer:
    """Factory used by main.py / io_manager.py."""
    return PlainRenderer() if plain else AnsiRenderer()
