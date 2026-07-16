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
from gpiozero import Button  # <-- Import for touch sensor

# ---------------------------
# TonyPi setup
# ---------------------------
rrc_board = rrc.Board()
Board = Controller.Controller(rrc_board)

# ---------------------------
# Touch Sensor setup
# ---------------------------
TOUCH_PIN = 18  # GPIO pin where touch sensor signal is connected
touch = Button(TOUCH_PIN, pull_up=True)  # Pull-up resistor enabled
emergency_stop = False  # Flag for emergency stop

def on_touch_detected():
    global emergency_stop
    print("\n⚠ TOUCH DETECTED! EMERGENCY STOP ACTIVATED ⚠")
    emergency_stop = True
    AGC.stopAll()  # Stop all running actions immediately

touch.when_pressed = on_touch_detected  # Assign callback

# ---------------------------
# Main Task
# ---------------------------
def main():
    global emergency_stop
    print("=== TonyPi Pro: Sheet Flip Sequence ===")
    time.sleep(2)

    try:
        # Step 1: Grab sheet
        if emergency_stop: return
        print("Step 1: Grabbing sheet...")
        Board.set_bus_servo_deviation(16, 57)
        Board.set_bus_servo_deviation(18, 0)
        AGC.runActionGroup("GrabSheet")
        time.sleep(1)

        # Step 2: Pass sheet
        if emergency_stop: return
        print("Step 2: Passing sheet...")
        Board.set_bus_servo_deviation(16, 57)
        Board.set_bus_servo_deviation(18, 0)
        AGC.runActionGroup("PassSheet")
        time.sleep(1)

        # Step 3: Change hand (flip sheet)
        if emergency_stop: return
        print("Step 3: Changing hand (flip sheet)...")
        Board.set_bus_servo_deviation(16, -34)
        Board.set_bus_servo_deviation(18, -125)
        AGC.runActionGroup("ChangeHandSheet")
        time.sleep(1)

        # Step 4: Put down sheet
        if emergency_stop: return
        print("Step 4: Putting down sheet...")
        Board.set_bus_servo_deviation(18, 0)
        AGC.runActionGroup("PutDownSheet")
        Board.set_bus_servo_deviation(16, 0)
        time.sleep(1)

        print("=== Task Complete ===")

    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user")

if __name__ == '__main__':
    main()
