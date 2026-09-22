# Importations
import sys
import os
import json

# Code
print(
'''
****************************************************
*                                                  *
*                   Welcome to:                    *
*                                                  *
* ~  SME Green Sutainability Eligibility Scheme  ~ *
-------------------------------------------------- *
*                                                  *
*  WARNING! THIS APP IS PRIMITIVE AND MAY NOT WORK *
*                                                  *
****************************************************
''')
input("Press enter to continue ")
key = 1

while key!=0:
    keyverify = False
    while keyverify == False:
        key = input("Please select your choice (0,1,2,3,4)\n 0. Exit\n 1. Start\n 2. B\n 3. C\n 4. D\n")
        if len(key) == 0:
            print("Empty Response!")
        elif key.isnumeric() == False:
            print("Error! Letters detected!!")
        elif key.isspace():
            print("Error! Space only answer not allowed")
        elif int(key) < 0 or int(key) > 4:
            print("Error! Unrecognised number option")
        else:
            keyverify = True
            key = int(key)

    match key:
        case 0:
            print("Exiting the program.")
        case 1: # Start checks
            print("Function U/C")
            from io_manager import get_user_input
            user_age = get_user_input("Please enter your age: ")
        case 2:
            print("Function U/C")
        case 3:
            print("Function U/C")
        case 4:
            print("Function U/C")