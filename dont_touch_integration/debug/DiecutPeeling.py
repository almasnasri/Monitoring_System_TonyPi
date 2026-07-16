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
from hiwonder import Controller
from hiwonder import ros_robot_controller_sdk as rrc

rrc_board = rrc.Board()
Board = Controller.Controller(rrc_board)

def main():
    print("=== TonyPi Pro: Diecut Peeling Sequence ===")
    time.sleep(2)

    try:
        # Step 1: Pick up the diecut
        print("Step 1: Picking up diecut...")
        Board.set_bus_servo_deviation(17, 0)
        AGC.runActionGroup("PickUpDiecut1")
        time.sleep(0.5)

        # Step 2: Perform diecut peeling
        print("Step 2a: Performing diecut peeling (left hand)...")
        Board.set_bus_servo_deviation(17, -50)
        AGC.runActionGroup("DoDiecutLeftHand")
        time.sleep(0.5)

        print("Step 2b: Performing diecut peeling (right hand)...")
        Board.set_bus_servo_deviation(17, 0)
        AGC.runActionGroup("DoDiecutRightHand")
        time.sleep(0.5)

        # Step 3: Put down the diecut
        print("Step 3: Placing diecut down...")
        Board.set_bus_servo_deviation(17, 0)
        AGC.runActionGroup("PutDownDiecut1")
        time.sleep(0.5)

        print("=== Task Complete ===")

    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user")


if __name__ == '__main__':
    main()
