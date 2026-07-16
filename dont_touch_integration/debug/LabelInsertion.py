#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import time
import os

# Ensure Python 3 is being used
if sys.version_info.major < 3:
    print('Please run this program with Python 3!')
    sys.exit(0)

# Import TonyPi Action Group Control module
if __name__ == '__main__':
    sys.path.append('/home/pi/tonypi/functions')  # Path when running directly
else:
    sys.path.append(os.path.join(os.path.dirname(__file__), 'functions'))  # Path when imported

import hiwonder.ActionGroupControl as AGC

STEP_DELAY = 2  # seconds to wait after each step


def confirm_step(message):
    """
    Ask user to confirm before continuing.
    c = continue, x = abort
    """
    while True:
        choice = input(f"{message} [c = continue / x = abort]: ").strip().lower()
        if choice == 'c':
            return True
        elif choice == 'x':
            print("⚠️ Task aborted by user.")
            sys.exit(0)
        else:
            print("Invalid choice, please enter 'c' to continue or 'x' to abort.")


def main():
    print("=== TonyPi Pro: Label Insertion Sequence ===")
    time.sleep(2)

    try:
        # Step 1: Grab the label
        print("Step 1: Grabbing label...")
        AGC.runActionGroup("GrabLabel")
        time.sleep(STEP_DELAY)

        # Confirm before proceeding
        confirm_step("✅ Confirm to proceed with lifting the label")

        # Step 2: Lift label for insertion
        print("Step 2: Lifting label for insertion...")
        AGC.runActionGroup("LiftLabelInsertion")
        time.sleep(STEP_DELAY)

        # Step 3: Put label
        print("Step 3: Placing label...")
        AGC.runActionGroup("PutLabel")
        time.sleep(STEP_DELAY)

        # Confirm before final step
        confirm_step("✅ Confirm to proceed with putting down label and standing up")

        # Step 4: Put down label and stand up
        print("Step 4: Putting down label and standing up...")
        AGC.runActionGroup("PutDownLabelAndStandUp")
        time.sleep(STEP_DELAY)

        print("=== Task Complete ===")

    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user")


if __name__ == '__main__':
    main()
