import RPi.GPIO as GPIO

class LightSensor:
    def __init__(self, pin=24):
        self.pin = pin
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN)

    def is_dark(self):
        # Returns True if Sensor is blocked (High signal)
        return GPIO.input(self.pin) == 1

    def cleanup(self):
        # This safely releases the pin when you exit
        GPIO.cleanup(self.pin)
