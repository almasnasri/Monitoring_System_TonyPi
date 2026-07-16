#!/usr/bin/python3
import time
import sys

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("❌ Critical Error: RPi.GPIO library not found.")
    print("   (This script must be run on the Raspberry Pi)")
    sys.exit(1)

# --- CONFIGURATION ---
# Change this if your sensor is on a different pin!
# Common Hiwonder pins: 11, 7, or check the labels on the expansion board.
SENSOR_PIN = 24

def main():
    print("------------------------------------------")
    print(f"      LIGHT SENSOR DEBUGGER (Pin {SENSOR_PIN})")
    print("------------------------------------------")
    print("1. Cover the sensor with your hand.")
    print("2. Shine a light on it.")
    print("3. Watch the values below change.")
    print("------------------------------------------")
    print("Press CTRL+C to quit.\n")

    # Setup GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SENSOR_PIN, GPIO.IN)

    try:
        while True:
            # Read the pin state (0 or 1)
            state = GPIO.input(SENSOR_PIN)
            
            # Interpret the state
            # NOTE: Most sensors output 1 (High) when DARK, and 0 (Low) when LIGHT.
            # If yours is opposite, just swap these text labels.
            status_text = "🌑 DARK" if state == 1 else "☀️ LIGHT"
            
            # Print to console (overwriting the line for a clean look)
            sys.stdout.write(f"\rSensor Raw Value: [{state}]  >>>  Status: {status_text}   ")
            sys.stdout.flush()
            
            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\n\nTest Finished.")
        GPIO.cleanup()

if __name__ == "__main__":
    main()