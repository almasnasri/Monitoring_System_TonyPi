import time
from gpiozero import Button
import hiwonder.ActionGroupControl as agc

# ---------------------------
# Configuration
# ---------------------------
TOUCH_PIN = 22  # GPIO pin for touch sensor signal

# Touch sensor: using pull_up=True means:
# Not touched = HIGH, Touched = LOW
touch = Button(TOUCH_PIN, pull_up=True)

# Action group controller
# agc = ActionGroupControl()

# Emergency stop flag
emergency_stop = False

def on_touch_detected():
    global emergency_stop
    print("\n⚠ TOUCH DETECTED! EMERGENCY STOP ACTIVATED ⚠")
    emergency_stop = True
    agc.stopAll()  # Immediately stop all robot actions

# Register callback for touch detection
touch.when_pressed = on_touch_detected

# ---------------------------
# Example task
# ---------------------------
def perform_task():
    global emergency_stop
    print("Task started. Touch the sensor to stop.")

    for i in range(10):  # Loop of actions
        if emergency_stop:
            print("Emergency stop triggered. Task terminated.")
            return  # FULL STOP — do not continue the task

        print("Step:", i)
        agc.runActionGroup("TurnSheetOver")  # example action
        time.sleep(0.1)

    print("Task completed normally.")

if __name__ == '__main__':
    perform_task()
