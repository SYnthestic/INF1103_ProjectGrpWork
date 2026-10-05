from art import *
import random
import sys
import os
import time

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
    

def print_wrong_sign_red():
    # # \033[91m sets color to bright red, \033[0m resets it to normal
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
                        
    print(red_start + x_art + color_reset)
    print("Error! Unrecognised number option")
    # print(x_art)

def woman_says_hi():
    a = art("woman",number=10)
    print(a)

def print_hello():
    print(text2art("Hello", font='block', chr_ignore=True))

def print_goodbye():
    tprint("Goodbye","rnd-xlarge")


def print_save_disk_block_deep_blue():
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
    print(disk_art)

def print_boxed_menu():
    border = "▓⚗_⚗▓ " * 10
    
    # Each row is padded to match the exact length of the border line (59 characters wide)
    print(border)
    print("▓                                                         ▓")
    print("▓    Please select your choice (0,1,2,3,4,5,6)            ▓")
    print("▓                                                         ▓")
    print("▓    0. Exit                                              ▓")
    print("▓    1. Start                                             ▓")
    print("▓    2. Save to JSON                                      ▓")
    print("▓    3. Pull from JSON                                    ▓")
    print("▓    4. Display Current Records                           ▓")
    print("▓    5. AI Processor                                      ▓")
    print("▓    6. Logic Manager                                     ▓")
    print("▓                                                         ▓")
    print(border)

def print_sustainability_banner():
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
    print(banner)

# Runs whenever AI Manager is using the get_ai_response() function. It gives one bar for every second passed
def run_ai_analysis_bar(stop_event, timeout_seconds=60):
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