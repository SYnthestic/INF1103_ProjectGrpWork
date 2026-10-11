from art import *
import io_manager as in_and_out
import random
import sys
import os
import time
import re
import textwrap
from art import art

ANSI = re.compile(r"\033\[[0-9;]*m")


def tile_frame(content, tile, gap=" "):
    """Surround `content` (multi-line string) with a border made of `tile`."""
    lines = textwrap.dedent(content).strip("\n").splitlines()
    lines = [l for l in lines if l.strip()]

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

    edge = gap.join([tile] * cols)                       # top / bottom row
    blank = f"{tile}{gap}{' ' * inner}{gap}{tile}"       # breathing room

    out = [edge, blank]
    for line in lines:
        out.append(f"{tile}{gap}{' ' * pad_l}{line}{' ' * pad_r}{gap}{tile}")
    out += [blank, edge]
    return "\n".join(out)




BLUE = "\033[34m"
LABEL = "\033[30;107m"  # black text on a bright white label
RESET = "\033[0m"
BUTTON_BOUNDS = (5, 35)


# ========================================================
# 🎨 INDIVIDUAL BUTTON ART ASSETS (Calls the engine)
# ========================================================

def continue_button():
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
    # Send art and custom boundaries to the core engine
    in_and_out.execute_button_interaction(art, min_x=5, max_x=35)


def return_button():
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
    # Uses the exact same engine loop!
    in_and_out.execute_button_interaction(art, min_x=5, max_x=35)

#The button that will start the AI analysis. This is for the Option 1, so as to let users know the AI Manager will start running
def ai_button():
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
# Uses the exact same engine loop!
    in_and_out.execute_button_interaction(art, min_x=5, max_x=35)

#Defines the yes and no buttons
def yes_no_buttons(question, btn_w=12, gap=4, indent=4):
    """Boxed yes/no prompt. Returns (art, regions).
    regions maps True/False to the (min_x, max_x) columns of each button."""
    green, red, grey, reset = "\033[92m", "\033[91m", "\033[90m", "\033[0m"
    hint = "[Y] Yes    [N] No    or click a button"
    total = 2 * btn_w + gap
    inner = max(len(question), len(hint), total) + 6

    def row(plain="", styled=None):
        pad = inner - len(plain)
        left = pad // 2
        return " " * indent + "│" + " " * left + (styled or plain) + " " * (pad - left) + "│"

    def button(label, colour, part):
        parts = {
            "top": "┌" + "─" * (btn_w - 2) + "┐",
            "mid": "│" + label.center(btn_w - 2) + "│",
            "bot": "└" + "─" * (btn_w - 2) + "┘",
        }
        return parts[part]

    lines = [" " * indent + "┌" + "─" * inner + "┐", row(), row(question), row()]
    for part in ("top", "mid", "bot"):
        yes, no = button("YES", green, part), button("NO", red, part)
        plain = yes + " " * gap + no
        styled = f"{green}{yes}{reset}" + " " * gap + f"{red}{no}{reset}"
        lines.append(row(plain, styled))
    lines += [row(), row(hint, f"{grey}{hint}{reset}"), row(),
              " " * indent + "└" + "─" * inner + "┘"]

    # Button columns (1-based, matching the terminal's mouse reports)
    pad_l = (inner - total) // 2
    yes_start = indent + 1 + pad_l + 1
    no_start = yes_start + btn_w + gap
    regions = {
        True: (yes_start, yes_start + btn_w - 1),
        False: (no_start, no_start + btn_w - 1),
    }
    return "\n" + "\n".join(lines) + "\n", regions
    

def wrong_sign_red():
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

def face_paintscheme():
    return art("woman")  # a single tile, e.g. ▓⚗_⚗▓




def hello():
    return text2art("Hello", font='block', chr_ignore=True)

def goodbye_art():
    return text2art("Goodbye", font="rnd-xlarge")

def save_disk_prompt_art(prompt=" Name: ", max_len=50):
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
        label_row(f"SAVE TO DISK (max {max_len} chars)".center(w)),
        label_row(prompt),  # <- input row (index 7)
        label_row(),
        f"  {BLUE}{'█' * body}▀{RESET}",
        f"   {BLUE}{'▀' * (body + 1)}{RESET}",
    ]

    input_row = 7
    rows_up = len(lines) - input_row
    col = 7 + len(prompt)
    return "\n".join(lines), rows_up, col

def save_disk_block_deep_blue():
    # Terminal Color Codes
    blue = "\033[34m"   # Deep classic blue
    white = "\033[97m"  # Crisp white for contrast
    reset = "\033[0m"   # Reset formatting

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

# sme_interface_gui.py
def boxed_menu():
    border = "▓⚗_⚗▓ " * 10
    blank = "▓" + " " * 57 + "▓"

    def row(text):
        return "▓" + text.ljust(57) + "▓"

    lines = [
        border,
        blank,
        row("    Please select your choice (0,1,2,3,4,5,6)"),
        blank,
        row("    0. Exit"),
        row("    1. Start"),
        row("    2. Save to JSON"),
        row("    3. Pull from JSON"),
        row("    4. Display Current Records"),
        row("    5. Update Records"),
        row("    6. Delete Records"),
        row("    7. AI Processor"),
        row("    8. Logic Manager"),
        blank,
        border,
    ]
    return "\n".join(lines)

def sustainability_banner():
    # Terminal Colors: \033[92m = Eco Green, \033[91m = Warning Red, \033[90m = Grey, \033[0m = Reset
    green = "\033[92m"
    red = "\033[91m"
    grey = "\033[90m"
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

def framed_sustainability_banner():
    tile = face_paintscheme().strip()
    return tile_frame(sustainability_banner(), tile)
