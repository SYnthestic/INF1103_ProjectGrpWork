from art import *
import random
import sys
import os
import time

BUTTON_BOUNDS = (5, 35)
# Set up clean cross-platform input capturing
is_windows = os.name == 'nt'

if is_windows:
    import msvcrt
    import ctypes
    # Need access to low-level Windows console input mode handles
    from ctypes import wintypes
    kernel32 = ctypes.windll.kernel32
    STD_INPUT_HANDLE = -10
    ENABLE_MOUSE_INPUT = 0x0010
    ENABLE_EXTENDED_FLAGS = 0x0080
else:
    import select
    import tty
    import termios

def enable_mouse_tracking():
    sys.stdout.write("\033[?1000h\033[?25l")
    sys.stdout.flush()
    if is_windows:
        # Extra Windows system hook to ensure the console terminal application unblocks mouse tracking
        hInput = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        mode = wintypes.DWORD()
        kernel32.GetConsoleMode(hInput, ctypes.byref(mode))
        kernel32.SetConsoleMode(hInput, (mode.value & ~ENABLE_EXTENDED_FLAGS) | ENABLE_MOUSE_INPUT)

def disable_mouse_tracking():
    sys.stdout.write("\033[?1000l\033[?25h\n")
    sys.stdout.flush()

# ========================================================
# ⚙️ THE UNIFIED HYBRID INPUT ENGINE (Reused by all buttons)
# ========================================================
def execute_button_interaction(button_art, min_x=5, max_x=35):
    """
    Prints any button art and waits for an Enter key or a mouse click 
    within the specific horizontal columns (min_x to max_x).
    """
    print(button_art, end="", flush=True)
    enable_mouse_tracking()

    try:
        if is_windows:
            buffer = ""
            while True:
                if msvcrt.kbhit():
                    char = msvcrt.getch()
                    if char in (b'\r', b'\n'):
                        break
                    try:
                        decoded = char.decode('utf-8', errors='ignore')
                    except:
                        continue
                    buffer += decoded
                    if "\033[M" in buffer:
                        idx = buffer.find("\033[M")
                        if len(buffer) >= idx + 6:
                            payload = buffer[idx+3:idx+6]
                            if len(payload) == 3:
                                click_type = ord(payload[0]) - 32
                                click_x = ord(payload[1]) - 32
                                if click_type == 0 and min_x <= click_x <= max_x:
                                    break
                            buffer = ""
        else:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                while True:
                    r, _, _ = select.select([sys.stdin], [], [])
                    if r:
                        user_input = sys.stdin.read(1)
                        if user_input in ('\n', '\r'):
                            break
                        if user_input == '\033':
                            next_chars = sys.stdin.read(5)
                            if next_chars.startswith('[M'):
                                click_type = ord(next_chars[2]) - 32
                                click_x = ord(next_chars[3]) - 32
                                if click_type == 0 and min_x <= click_x <= max_x:
                                    break
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    finally:
        disable_mouse_tracking()

# ========================================================
# 🎨 INDIVIDUAL BUTTON ART ASSETS (Calls the engine)
# ========================================================

def press_enter_to_continue():
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
    execute_button_interaction(art, min_x=5, max_x=35)


def print_return_keycap():
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
    execute_button_interaction(art, min_x=5, max_x=35)
    
def ai_button_art():
    green = "\033[92m"
    shadow = "\033[90m"
    reset = "\033[0m"

    label = "⮞ START AI ANALYSIS"

    return f"""
     ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
    █  {green}┌──────────────────────────┐{reset}  █
    █  {green}│{label:<26}│{reset}  █▀▄
    █  {green}└──────────────────────────┘{reset}  █ █
    ▀████████████████████████████████▀  █
      {shadow}▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀{reset}
    """
    

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

