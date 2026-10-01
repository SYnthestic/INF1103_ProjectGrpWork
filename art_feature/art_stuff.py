from art import *
import random
import sys

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
    # print(x_art)

def woman_says_hi():
    a = art("woman",number=10)
    print(a)

def print_hello():
    print(text2art("Hello", font='block', chr_ignore=True))

def print_goodbye():
    tprint("Goodbye","rnd-xlarge")

def press_enter_key():
    # Terminal colors: \033[93m = Bright Yellow/Gold, \033[90m = Grey Shadow, \033[0m = Reset
    gold = "\033[93m"
    shadow = "\033[90m"
    reset = "\033[0m"
    
    # Hide the blinking terminal cursor so the key looks static and clean
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

    # The 3D Keycap Art Matrix
    key_art = f"""
     ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
    █  {gold}┌──────────────────────────┐{reset}  █
    █  {gold}│⮞ PRESS ENTER TO CONTINUE │{reset}  █▀▄
    █  {gold}└──────────────────────────┘{reset}  █ █
    ▀████████████████████████████████▀  █
      {shadow}▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀{reset}
    """
    
    print(key_art, end="", flush=True)

    # Standard built-in input mechanism waiting for the Enter keypress
    input()

    # Restore the terminal cursor to normal behavior
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()
    print("\n") # Clean line break after click

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
