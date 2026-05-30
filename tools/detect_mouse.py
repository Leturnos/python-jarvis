"""
Mouse Position Detector Utility
This script prints the X and Y screen coordinates of the mouse in real-time.
"""

import time
import sys
import pyautogui

def main():
    print("=========================================")
    print("       Mouse Position Detector          ")
    print("=========================================")
    print("Move your mouse to the desired position.")
    print("Press Ctrl+C in this terminal to exit.")
    print("-----------------------------------------")
    
    try:
        while True:
            x, y = pyautogui.position()
            position_str = f"Current Position -> X: {x:4d} | Y: {y:4d}"
            sys.stdout.write("\r" + position_str)
            sys.stdout.flush()
            time.sleep(0.1)
    except KeyboardInterrupt:
        x, y = pyautogui.position()
        print("\n\nPosition detection stopped.")
        print(f"Final logged position: X: {x} | Y: {y}")
        print("Use these coordinates in your automation configuration.")

if __name__ == "__main__":
    main()
