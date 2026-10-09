from art import *
import io_manager as in_and_out
import random
import sys
import os
import time

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

def woman_says_hi():
    a = art("woman",number=10)
    return a

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
        row("    5. AI Processor"),
        row("    6. Logic Manager"),
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

