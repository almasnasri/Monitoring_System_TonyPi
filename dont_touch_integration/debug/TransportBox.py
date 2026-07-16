#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import time
import os
import cv2
from threading import Thread

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

# Import custom modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules'))
try:
    from qr_navigate import start_qr_navigation_async, get_navigation_result
    QR_AVAILABLE = True
except ImportError:
    print("[WARNING] QR navigation module not available")
    QR_AVAILABLE = False


def get_camera_frame(camera_index=0):
    """Get frame from camera"""
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return None
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def main():
    # Optional: use QR scanning if available
    use_qr = False
    steps_to_take = 5
    
    if len(sys.argv) >= 2 and sys.argv[1].lower() == 'qr' and QR_AVAILABLE:
        use_qr = True
        print("Using QR code navigation mode")

    mode_str = "QR Navigation" if use_qr else f"Fixed Steps (5)"
    print(f"=== TonyPi Pro: Transport Box Sequence - {mode_str} ===")
    time.sleep(2)

    try:
        # Step 1: Pick up the object
        print("Step 1: Picking up object...")
        AGC.runActionGroup("PickUp")
        time.sleep(0.5)

        if use_qr and QR_AVAILABLE:
            # Step 2: Scan for QR code and navigate
            print("Step 2: Scanning for QR code...")
            start_qr_navigation_async(timeout=60)
            
            # Wait for navigation to complete
            print("Step 3: Navigating to QR code...")
            result = get_navigation_result()
            timeout = time.time() + 60
            while result is None and time.time() < timeout:
                time.sleep(0.5)
                result = get_navigation_result()
            
            if result:
                print(f"Reached destination: {result}")
            else:
                print("[WARNING] QR navigation timeout, falling back to walking")
                for i in range(steps_to_take):
                    print(f"  Walking step {i+1}/{steps_to_take}...")
                    AGC.runActionGroup("WalkOneStep")
                    time.sleep(0.5)
        else:
            # Step 2: Walk forward (fixed steps)
            print("Step 2: Walking forward...")
            for i in range(steps_to_take):
                print(f"  Walking step {i+1}/{steps_to_take}...")
                AGC.runActionGroup("WalkOneStep")
                time.sleep(0.5)

        # Final Step: Put down the object
        print("Step 3: Placing object down...")
        AGC.runActionGroup("PutDown")

        print("=== Task Complete ===")

    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user")


if __name__ == '__main__':
    main()
