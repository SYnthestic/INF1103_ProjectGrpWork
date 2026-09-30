from art import *
import random

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
