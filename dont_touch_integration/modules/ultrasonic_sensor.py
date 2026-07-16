#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import lgpio
import time

# ----------------------------
# GPIO Pin Configuration
# ----------------------------
TRIG_PIN = 28
ECHO_PIN = 29
OBSTACLE_DISTANCE_THRESHOLD = 12  # cm - obstacle detected if closer than this
DISTANCE_BUFFER_SIZE = 5  # Number of readings to average


class UltrasonicSensor:
    """Handles ultrasonic sensor for distance and obstacle detection"""
    
    def __init__(self, trig_pin=TRIG_PIN, echo_pin=ECHO_PIN, obstacle_threshold=OBSTACLE_DISTANCE_THRESHOLD):
        """Initialize the ultrasonic sensor
        
        Args:
            trig_pin (int): GPIO pin for trigger
            echo_pin (int): GPIO pin for echo
            obstacle_threshold (int): Distance threshold in cm for obstacle detection
        """
        self.trig_pin = trig_pin
        self.echo_pin = echo_pin
        self.obstacle_threshold = obstacle_threshold
        self.last_distance = None
        self.distance_history = []  # Buffer for averaging readings
        self.consecutive_detections = 0  # Counter for consecutive obstacle detections
        
        try:
            self.h = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_output(self.h, self.trig_pin)
            lgpio.gpio_claim_input(self.h, self.echo_pin)
            lgpio.gpio_write(self.h, self.trig_pin, 0)
            time.sleep(0.5)
            print(f"✅ Ultrasonic Sensor initialized (Obstacle threshold: {obstacle_threshold}cm)")
        except Exception as e:
            print(f"⚠️ WARNING: Could not initialize ultrasonic sensor: {e}")
            self.h = None
    
    def get_distance(self):
        """Get distance measurement in cm
        
        Returns:
            float: Distance in centimeters, or None if sensor unavailable
        """
        if self.h is None:
            return None
        
        try:
            # Send trigger pulse
            lgpio.gpio_write(self.h, self.trig_pin, 1)
            time.sleep(0.00001)  # 10 microseconds trigger pulse
            lgpio.gpio_write(self.h, self.trig_pin, 0)
            
            # ⭐ CRITICAL FIX: Wait for sensor to stabilize after trigger
            # The sensor needs time to transmit ultrasonic burst before echo starts
            time.sleep(0.00005)  # 50 microseconds stabilization delay
            
            # Wait for echo start with timeout (max 50ms = ~8.5m range)
            start_time = time.time()
            timeout = 0.05
            while lgpio.gpio_read(self.h, self.echo_pin) == 0:
                if time.time() - start_time > timeout:
                    return None  # Timeout, no echo received
                start_time = time.time()
            
            # Wait for echo end with timeout
            stop_time = time.time()
            while lgpio.gpio_read(self.h, self.echo_pin) == 1:
                if time.time() - stop_time > timeout:
                    return None  # Timeout, echo didn't end properly
                stop_time = time.time()
            
            time_elapsed = stop_time - start_time
            distance = (time_elapsed * 34300) / 2
            self.last_distance = round(distance, 2)
            return self.last_distance
        except Exception as e:
            print(f"⚠️ WARNING: Error reading ultrasonic sensor: {e}")
            return None
    
    def is_obstacle_detected(self):
        """Check if an obstacle is detected within threshold
        Uses noise filtering with consecutive detection requirement.
        
        Returns:
            bool: True if obstacle is near (distance < threshold) consistently, False otherwise
        """
        distance = self.get_distance()
        if distance is None:
            self.consecutive_detections = 0
            return False
        
        # Add to history and keep buffer size limited
        self.distance_history.append(distance)
        if len(self.distance_history) > DISTANCE_BUFFER_SIZE:
            self.distance_history.pop(0)
        
        # Average the readings for noise reduction
        avg_distance = sum(self.distance_history) / len(self.distance_history)
        
        # Only report obstacle if it's consistently detected
        if avg_distance < self.obstacle_threshold:
            self.consecutive_detections += 1
            # Require at least 2 consecutive detections to avoid false positives
            return self.consecutive_detections >= 2
        else:
            self.consecutive_detections = 0
            return False
    
    def cleanup(self):
        """Clean up GPIO resources"""
        try:
            if self.h is not None:
                lgpio.gpiochip_close(self.h)
                print("✅ Ultrasonic sensor cleaned up")
        except Exception as e:
            print(f"⚠️ WARNING: Error cleaning up ultrasonic sensor: {e}")


# ----------------------------
# Main Test Loop (for standalone testing)
# ----------------------------
if __name__ == "__main__":
    sensor = UltrasonicSensor()
    try:
        while True:
            # is_obstacle_detected() internally calls get_distance(), 
            # so we only call it once to avoid redundant measurements
            obstacle = sensor.is_obstacle_detected()
            
            # Use the last measured distance (already obtained in is_obstacle_detected)
            if sensor.last_distance is not None:
                status = "🚨 OBSTACLE DETECTED!" if obstacle else "✅ Clear"
                print(f"Distance: {sensor.last_distance}cm - {status}")
            else:
                print("Sensor unavailable")
            time.sleep(0.2)
    
    except KeyboardInterrupt:
        print("\nProgram stopped by user")
    
    finally:
        sensor.cleanup()
