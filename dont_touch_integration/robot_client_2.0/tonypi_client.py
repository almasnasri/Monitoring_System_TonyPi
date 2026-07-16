#!/usr/bin/env python3
"""
TonyPi Robot Client - Real Hardware Integration
Runs on Raspberry Pi with TonyPi robot hardware.
Connects to the monitoring system and sends/receives data via MQTT.

Features:
- Real servo data (position, temperature, voltage) from HiWonder SDK
- IMU sensor data (accelerometer, gyroscope)
- Ultrasonic distance sensor
- Battery voltage monitoring
- Movement actions via pre-recorded action groups
- Automatic fallback to simulation mode if hardware unavailable
"""

import sys
import os

# Add the local hiwonder SDK path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Also add TonyPi default path for when running on actual robot
if os.path.exists('/home/pi/TonyPi'):
    sys.path.append('/home/pi/TonyPi')
    sys.path.append('/home/pi/TonyPi/HiwonderSDK')

import asyncio
import json
import time
import uuid
import psutil
import platform
import random
import socket
from datetime import datetime
from typing import Dict, Any, Optional
import paho.mqtt.client as mqtt
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TonyPi-Client")

# Try to import HiWonder SDK for real hardware access
HARDWARE_AVAILABLE = False
board = None
controller = None
sonar = None

try:
    from hiwonder import ros_robot_controller_sdk as rrc
    from hiwonder.Controller import Controller
    from hiwonder.Sonar import Sonar
    from hiwonder.ActionGroupControl import runActionGroup, stopActionGroup, executeMovement
    
    # Initialize hardware
    board = rrc.Board()
    controller = Controller(board)
    sonar = Sonar()
    board.enable_reception(True)
    
    HARDWARE_AVAILABLE = not board.simulation_mode
    logger.info(f"HiWonder SDK loaded. Hardware mode: {HARDWARE_AVAILABLE}")
except ImportError as e:
    logger.warning(f"HiWonder SDK not available: {e}")
    logger.info("Running in simulation mode")
except Exception as e:
    logger.warning(f"Hardware initialization failed: {e}")
    logger.info("Running in simulation mode")

# Try to import GPIO for light sensor
LIGHT_SENSOR_AVAILABLE = False
light_sensor_gpio = None
try:
    import RPi.GPIO as GPIO
    LIGHT_SENSOR_AVAILABLE = True
    logger.info("RPi.GPIO available for light sensor")
except ImportError:
    logger.warning("RPi.GPIO not available - light sensor will be simulated")


class LightSensor:
    """Light sensor class for reading ambient light via GPIO."""
    
    def __init__(self, pin=24):
        self.pin = pin
        self.initialized = False
        if LIGHT_SENSOR_AVAILABLE:
            try:
                GPIO.setwarnings(False)
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.pin, GPIO.IN)
                self.initialized = True
                logger.info(f"Light sensor initialized on GPIO pin {pin}")
            except Exception as e:
                logger.error(f"Failed to initialize light sensor: {e}")
    
    def is_dark(self) -> bool:
        """Returns True if sensor detects darkness (blocked/low light)."""
        if self.initialized and LIGHT_SENSOR_AVAILABLE:
            try:
                return GPIO.input(self.pin) == 1
            except Exception as e:
                logger.error(f"Error reading light sensor: {e}")
                return False
        # Simulation mode - randomly simulate light conditions
        return random.random() < 0.1  # 10% chance of being dark
    
    def get_light_level(self) -> int:
        """Returns light level: 0 = dark, 100 = bright."""
        if self.is_dark():
            return random.randint(0, 20)  # Low light
        return random.randint(60, 100)  # Normal/bright light
    
    def cleanup(self):
        """Clean up GPIO resources."""
        if self.initialized and LIGHT_SENSOR_AVAILABLE:
            try:
                GPIO.cleanup(self.pin)
            except Exception as e:
                logger.error(f"Error cleaning up light sensor: {e}")


class TonyPiRobotClient:
    """
    TonyPi Robot Client with real hardware integration.
    Automatically falls back to simulation mode if hardware is unavailable.
    """
    
    # Servo configuration for TonyPi humanoid robot
    SERVO_NAMES = [
        "Right Hip Yaw",      # Servo 1
        "Right Hip Roll",     # Servo 2
        "Right Hip Pitch",    # Servo 3
        "Right Knee",         # Servo 4
        "Right Ankle Pitch",  # Servo 5
        "Right Ankle Roll",   # Servo 6
        "Left Hip Yaw",       # Servo 7
        "Left Hip Roll",      # Servo 8
        "Left Hip Pitch",     # Servo 9
        "Left Knee",          # Servo 10
        "Left Ankle Pitch",   # Servo 11
        "Left Ankle Roll",    # Servo 12
    ]
    
    # Number of servos on the robot
    SERVO_COUNT = 6  # TonyPi has 6 main bus servos
    
    def __init__(self, mqtt_broker: str = "localhost", mqtt_port: int = 1883, robot_id: str = None):
        """
        Initialize the TonyPi Robot Client.
        
        Args:
            mqtt_broker: MQTT broker address
            mqtt_port: MQTT broker port
            robot_id: Robot identifier (auto-generated if not provided)
        """
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        
        # Use hostname-based ID for persistence
        if robot_id:
            self.robot_id = robot_id
        else:
            hostname = platform.node().lower().replace(" ", "_")
            self.robot_id = f"tonypi_{hostname}"
        
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.robot_id)
        self.is_connected = False
        self.running = False
        
        # Hardware availability
        self.hardware_available = HARDWARE_AVAILABLE
        
        # Light sensor
        self.light_sensor = LightSensor(pin=24)
        
        # Robot state
        self.battery_level = 100.0
        self._last_battery_voltage = 12.6  # Store last read voltage for reporting
        self.location = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.sensors = {}
        self.status = "online"
        self.servo_data = {}
        
        # MQTT Topics
        self.topics = {
            "sensors": f"tonypi/sensors/{self.robot_id}",
            "status": f"tonypi/status/{self.robot_id}",
            "location": f"tonypi/location",
            "battery": f"tonypi/battery",
            "commands": f"tonypi/commands/{self.robot_id}",
            "response": f"tonypi/commands/response",
            "servos": f"tonypi/servos/{self.robot_id}",
            "vision": f"tonypi/vision/{self.robot_id}",
            "logs": f"tonypi/logs/{self.robot_id}"
        }
        
        # Additional topics
        self.items_topic = f"tonypi/items/{self.robot_id}"
        self.scan_topic = f"tonypi/scan/{self.robot_id}"
        self.job_topic = f"tonypi/job/{self.robot_id}"
        
        # Setup MQTT callbacks
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        
        logger.info(f"TonyPi Robot Client initialized with ID: {self.robot_id}")
        logger.info(f"Hardware available: {self.hardware_available}")

    def on_connect(self, client, userdata, flags, rc, properties=None):
        """Callback for MQTT connection."""
        if rc == 0:
            self.is_connected = True
            logger.info(f"Connected to MQTT broker at {self.mqtt_broker}:{self.mqtt_port}")
            
            # Subscribe to command topics
            client.subscribe(self.topics["commands"])
            client.subscribe("tonypi/commands/broadcast")
            client.subscribe(self.items_topic)
            
            # Send initial status
            self.send_status_update()
        else:
            logger.error(f"Failed to connect to MQTT broker. Return code: {rc}")

    def on_disconnect(self, client, userdata, flags=None, rc=None, properties=None):
        """Callback for MQTT disconnection."""
        self.is_connected = False
        return_code = rc if rc is not None else flags
        logger.warning(f"Disconnected from MQTT broker. Return code: {return_code}")

    def on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages (commands from monitoring system)."""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            logger.info(f"Received command on {topic}: {payload}")
            
            command_type = payload.get("type")
            command_id = payload.get("id", str(uuid.uuid4()))
            
            response = {
                "robot_id": self.robot_id,
                "command_id": command_id,
                "timestamp": datetime.now().isoformat(),
                "success": False,
                "message": "Unknown command"
            }
            
            if command_type == "move":
                response = self.handle_move_command(payload)
            elif command_type == "status_request":
                response = self.handle_status_request(payload)
            elif command_type == "battery_request":
                response = self.handle_battery_request(payload)
            elif command_type == "stop":
                response = self.handle_stop_command(payload)
            elif command_type == "shutdown":
                response = self.handle_shutdown_command(payload)
            elif command_type == "head_nod":
                response = self.handle_head_nod(payload)
            elif command_type == "head_shake":
                response = self.handle_head_shake(payload)
            elif topic.startswith("tonypi/items/"):
                response = self._handle_item_info(payload)
            
            # Send response
            self.client.publish(self.topics["response"], json.dumps(response))
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _handle_item_info(self, payload):
        """Handle item info responses."""
        response = {
            "robot_id": self.robot_id,
            "timestamp": datetime.now().isoformat(),
            "success": payload.get('found', False),
            "item": payload.get('item'),
            "message": payload.get('message', 'Item info')
        }
        
        # Update job progress
        try:
            if not hasattr(self, 'items_done'):
                self.items_done = 0
                self.items_total = 10
            if payload.get('found', False):
                self.items_done += 1
                percent = round((self.items_done / max(1, self.items_total)) * 100, 2)
                job_event = {
                    "robot_id": self.robot_id,
                    "percent": percent,
                    "status": "working" if percent < 100 else "completed",
                    "items_done": self.items_done,
                    "items_total": self.items_total,
                    "timestamp": datetime.now().isoformat()
                }
                self.client.publish(self.job_topic, json.dumps(job_event))
        except Exception as e:
            logger.error(f"Error updating job progress: {e}")
        
        return response

    def handle_move_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle movement commands using TonyPi action groups."""
        try:
            direction = payload.get("direction", "forward")
            distance = payload.get("distance", 1.0)
            speed = payload.get("speed", 0.5)
            
            logger.info(f"Moving {direction} for {distance} units at speed {speed}")
            
            if self.hardware_available:
                # Use real action groups
                result = executeMovement(direction, times=1, with_stand=True)
                if not result.get("success"):
                    logger.warning(f"Movement command failed: {result.get('message')}")
            else:
                # Simulate movement
                if direction == "forward":
                    self.location["x"] += distance
                elif direction == "backward":
                    self.location["x"] -= distance
                elif direction == "left":
                    self.location["y"] -= distance
                elif direction == "right":
                    self.location["y"] += distance
            
            # Simulate battery consumption
            self.battery_level = max(0, self.battery_level - (distance * 0.1))
            
            return {
                "robot_id": self.robot_id,
                "command_id": payload.get("id"),
                "timestamp": datetime.now().isoformat(),
                "success": True,
                "message": f"Moved {direction} for {distance} units",
                "new_location": self.location.copy(),
                "battery_level": self.battery_level
            }
        except Exception as e:
            return {
                "robot_id": self.robot_id,
                "command_id": payload.get("id"),
                "timestamp": datetime.now().isoformat(),
                "success": False,
                "message": f"Movement failed: {str(e)}"
            }

    def handle_stop_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle stop command."""
        logger.info("Stopping all robot activities")
        
        if self.hardware_available:
            try:
                stopActionGroup()
            except Exception as e:
                logger.error(f"Error stopping actions: {e}")
        
        return {
            "robot_id": self.robot_id,
            "command_id": payload.get("id"),
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "message": "Robot stopped successfully"
        }

    def handle_head_nod(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle head nod command."""
        logger.info("Nodding head")
        
        if self.hardware_available and controller:
            try:
                # PWM servo 1 controls head tilt
                controller.set_pwm_servo_pulse(1, 1800, 200)
                time.sleep(0.2)
                controller.set_pwm_servo_pulse(1, 1200, 200)
                time.sleep(0.2)
                controller.set_pwm_servo_pulse(1, 1800, 200)
                time.sleep(0.2)
                controller.set_pwm_servo_pulse(1, 1200, 200)
                time.sleep(0.2)
                controller.set_pwm_servo_pulse(1, 1500, 100)
            except Exception as e:
                logger.error(f"Error nodding head: {e}")
        
        return {
            "robot_id": self.robot_id,
            "command_id": payload.get("id"),
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "message": "Head nod completed"
        }

    def handle_head_shake(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle head shake command."""
        logger.info("Shaking head")
        
        if self.hardware_available and controller:
            try:
                # PWM servo 2 controls head pan
                controller.set_pwm_servo_pulse(2, 1800, 200)
                time.sleep(0.2)
                controller.set_pwm_servo_pulse(2, 1200, 200)
                time.sleep(0.2)
                controller.set_pwm_servo_pulse(2, 1800, 200)
                time.sleep(0.2)
                controller.set_pwm_servo_pulse(2, 1200, 200)
                time.sleep(0.2)
                controller.set_pwm_servo_pulse(2, 1500, 100)
            except Exception as e:
                logger.error(f"Error shaking head: {e}")
        
        return {
            "robot_id": self.robot_id,
            "command_id": payload.get("id"),
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "message": "Head shake completed"
        }

    def handle_status_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle status request commands."""
        return {
            "robot_id": self.robot_id,
            "command_id": payload.get("id"),
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "message": "Status retrieved",
            "data": {
                "status": self.status,
                "battery_level": self.get_battery_percentage(),
                "location": self.location.copy(),
                "sensors": self.sensors.copy(),
                "system_info": self.get_system_info(),
                "hardware_available": self.hardware_available
            }
        }

    def handle_battery_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle battery status request."""
        battery = self.get_battery_percentage()
        return {
            "robot_id": self.robot_id,
            "command_id": payload.get("id"),
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "message": "Battery status retrieved",
            "data": {
                "battery_level": battery,
                "charging": False,
                "estimated_time": battery * 2
            }
        }

    def handle_shutdown_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle shutdown command."""
        logger.info("Shutting down robot client")
        self.running = False
        return {
            "robot_id": self.robot_id,
            "command_id": payload.get("id"),
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "message": "Robot shutting down"
        }

    def get_system_info(self) -> Dict[str, Any]:
        """Get system information from Raspberry Pi (Task Manager metrics)."""
        try:
            cpu_temp = self.get_cpu_temperature()
            # Use interval=None to get instant reading (non-blocking)
            # This returns the CPU usage since last call
            cpu_percent = psutil.cpu_percent(interval=None)
            return {
                "platform": platform.platform(),
                "cpu_percent": cpu_percent,
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage('/').percent,
                "temperature": cpu_temp,           # Legacy field
                "cpu_temperature": cpu_temp,       # New field for frontend
                "uptime": time.time() - psutil.boot_time(),
                "hardware_mode": self.hardware_available,
                "hardware_sdk": self.hardware_available
            }
        except Exception as e:
            logger.error(f"Error getting system info: {e}")
            return {"error": str(e)}

    def get_cpu_temperature(self) -> float:
        """Get CPU temperature (Raspberry Pi specific)."""
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                return float(f.read()) / 1000.0
        except:
            return 45.0 + (time.time() % 10)

    def get_local_ip(self) -> str:
        """Get the local IP address of the robot."""
        try:
            # Create a socket to determine the local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logger.warning(f"Could not determine local IP: {e}")
            # Fallback: try to get from network interfaces
            try:
                hostname = socket.gethostname()
                ip = socket.gethostbyname(hostname)
                if ip != "127.0.0.1":
                    return ip
            except:
                pass
            return "192.168.149.1"  # Default TonyPi IP

    def get_battery_percentage(self) -> float:
        """
        Get battery percentage from hardware or simulation.
        
        TonyPi uses a 3S LiPo battery:
        - Full charge: 12.6V (4.2V per cell)
        - Nominal: 11.1V (3.7V per cell)
        - Empty (safe cutoff): 9.0V (3.0V per cell)
        
        Uses a non-linear voltage curve for more accurate percentage:
        - Above 11.4V: 70-100% (slow discharge region)
        - 10.5V - 11.4V: 30-70% (nominal region)
        - Below 10.5V: 0-30% (fast discharge region)
        """
        if self.hardware_available and board:
            try:
                voltage_mv = board.get_battery()
                logger.debug(f"Raw battery reading: {voltage_mv} mV")
                
                if voltage_mv is not None and voltage_mv > 0:
                    voltage_v = voltage_mv / 1000.0
                    
                    # Sanity check: 3S LiPo should be between 9V and 13V
                    if voltage_v < 5.0:
                        # Might be reading per-cell voltage, multiply by 3
                        logger.warning(f"Battery voltage too low ({voltage_v}V), assuming per-cell reading")
                        voltage_v = voltage_v * 3
                    elif voltage_v > 15.0:
                        # Invalid reading, use last known value
                        logger.warning(f"Battery voltage too high ({voltage_v}V), using fallback")
                        return self.battery_level
                    
                    percentage = self._voltage_to_percentage(voltage_v)
                    self.battery_level = max(0, min(100, percentage))
                    self._last_battery_voltage = voltage_v  # Store for reporting
                    
                    logger.debug(f"Battery: {voltage_v:.2f}V = {percentage:.1f}%")
                    return self.battery_level
                else:
                    logger.warning(f"Invalid battery reading: {voltage_mv}")
            except Exception as e:
                logger.error(f"Error reading battery: {e}")
        else:
            logger.debug(f"Battery hardware not available (hw={self.hardware_available}, board={board is not None})")
        
        # Simulation mode - slowly decrease battery for testing
        if not self.hardware_available:
            self.battery_level = max(0, self.battery_level - 0.01)
            # Estimate voltage from percentage
            self._last_battery_voltage = 9.0 + (self.battery_level / 100.0) * 3.6
        
        return self.battery_level
    
    def _voltage_to_percentage(self, voltage: float) -> float:
        """
        Convert battery voltage to percentage using a realistic LiPo discharge curve.
        
        For 3S LiPo (9.0V - 12.6V range):
        - Uses piecewise linear approximation of actual discharge curve
        - More accurate than simple linear mapping
        
        Args:
            voltage: Battery voltage in Volts
            
        Returns:
            Battery percentage (0-100)
        """
        # Battery configuration for 3S LiPo
        BATTERY_MIN_V = 9.0    # 3.0V per cell - empty
        BATTERY_MAX_V = 12.6   # 4.2V per cell - full
        
        # Clamp voltage to valid range
        voltage = max(BATTERY_MIN_V, min(BATTERY_MAX_V, voltage))
        
        # Piecewise linear approximation of LiPo discharge curve
        # These breakpoints are based on typical 3S LiPo discharge characteristics
        breakpoints = [
            (9.0, 0),      # Empty
            (9.6, 5),      # Critical low
            (10.2, 15),    # Low
            (10.5, 25),    # Start of nominal region
            (10.8, 40),    
            (11.1, 50),    # Nominal voltage
            (11.4, 65),    
            (11.7, 80),    # Good charge
            (12.0, 90),    
            (12.3, 95),    
            (12.6, 100),   # Full
        ]
        
        # Find the segment containing the voltage
        for i in range(len(breakpoints) - 1):
            v1, p1 = breakpoints[i]
            v2, p2 = breakpoints[i + 1]
            
            if v1 <= voltage <= v2:
                # Linear interpolation within segment
                ratio = (voltage - v1) / (v2 - v1)
                return p1 + ratio * (p2 - p1)
        
        # Fallback (shouldn't reach here due to clamping)
        return 0 if voltage < BATTERY_MIN_V else 100

    def read_sensors(self) -> Dict[str, float]:
        """Read sensor data from hardware or simulation."""
        sensors = {}
        
        if self.hardware_available and board:
            try:
                # IMU Data (accelerometer and gyroscope)
                imu = board.get_imu()
                if imu:
                    sensors["accelerometer_x"] = round(imu[0], 3)
                    sensors["accelerometer_y"] = round(imu[1], 3)
                    sensors["accelerometer_z"] = round(imu[2], 3)
                    sensors["gyroscope_x"] = round(imu[3], 2)
                    sensors["gyroscope_y"] = round(imu[4], 2)
                    sensors["gyroscope_z"] = round(imu[5], 2)
            except Exception as e:
                logger.error(f"Error reading IMU: {e}")
            
            try:
                # Ultrasonic distance sensor
                if sonar:
                    distance = sonar.getDistance()
                    if distance != 99999:
                        sensors["ultrasonic_distance"] = distance / 10.0  # Convert to cm
            except Exception as e:
                logger.error(f"Error reading sonar: {e}")
        else:
            # Simulation mode - generate realistic sensor data
            sensors = {
                "accelerometer_x": round(random.uniform(-0.5, 0.5), 3),
                "accelerometer_y": round(random.uniform(-0.5, 0.5), 3),
                "accelerometer_z": round(random.uniform(9.5, 10.0), 3),
                "gyroscope_x": round(random.uniform(-10, 10), 2),
                "gyroscope_y": round(random.uniform(-10, 10), 2),
                "gyroscope_z": round(random.uniform(-10, 10), 2),
                "ultrasonic_distance": round(random.uniform(5.0, 200.0), 1),
            }
        
        # Add CPU temperature (always available)
        sensors["cpu_temperature"] = self.get_cpu_temperature()
        
        # Light sensor data (real hardware or simulated)
        is_dark = self.light_sensor.is_dark()
        sensors["light_sensor_dark"] = 1 if is_dark else 0
        sensors["light_level"] = self.light_sensor.get_light_level()
        
        # Light sensor status for monitoring
        sensors["light_status"] = "dark" if is_dark else "bright"
        
        self.sensors = sensors
        return sensors

    def get_servo_status(self) -> Dict[str, Any]:
        """
        Read real servo data from TonyPi hardware.
        Returns position, temperature, and voltage for each servo.
        """
        servo_data = {}
        servo_names = ["Left Hip", "Left Knee", "Right Hip", "Right Knee", "Head Pan", "Head Tilt"]
        
        if self.hardware_available and controller:
            for idx in range(1, self.SERVO_COUNT + 1):
                try:
                    # Read servo data with timeout handling
                    pos = controller.get_bus_servo_pulse(idx)
                    temp = controller.get_bus_servo_temp(idx)
                    vin = controller.get_bus_servo_vin(idx)
                    
                    # Convert pulse to degrees (500 = -90, 500 = center, 1000 = +90)
                    # Standard formula: ((pulse - 500) / 500) * 90 degrees
                    if pos is not None:
                        angle = ((pos - 500) / 500) * 90
                    else:
                        angle = 0.0
                    
                    # Determine alert level based on temperature
                    alert = "normal"
                    if temp and temp > 70:
                        alert = "critical"
                    elif temp and temp > 60:
                        alert = "warning"
                    
                    servo_data[f"servo_{idx}"] = {
                        "id": idx,
                        "name": servo_names[idx - 1] if idx <= len(servo_names) else f"Servo {idx}",
                        "position": round(angle, 1),
                        "temperature": temp if temp else 45.0,
                        "voltage": (vin / 1000.0) if vin else 5.0,
                        "torque_enabled": True,
                        "alert_level": alert
                    }
                except Exception as e:
                    logger.error(f"Error reading servo {idx}: {e}")
                    # Provide default data on error
                    servo_data[f"servo_{idx}"] = {
                        "id": idx,
                        "name": servo_names[idx - 1] if idx <= len(servo_names) else f"Servo {idx}",
                        "position": 0.0,
                        "temperature": 45.0,
                        "voltage": 5.0,
                        "torque_enabled": True,
                        "alert_level": "normal"
                    }
        else:
            # Simulation mode
            for idx in range(1, self.SERVO_COUNT + 1):
                temp = round(random.uniform(40, 55), 1)
                servo_data[f"servo_{idx}"] = {
                    "id": idx,
                    "name": servo_names[idx - 1] if idx <= len(servo_names) else f"Servo {idx}",
                    "position": round(random.uniform(-45, 45), 1),
                    "temperature": temp,
                    "voltage": round(random.uniform(4.8, 5.2), 2),
                    "torque_enabled": True,
                    "alert_level": "warning" if temp > 50 else "normal"
                }
        
        self.servo_data = servo_data
        return servo_data

    def get_sensor_unit(self, sensor_name: str) -> str:
        """Get the unit for a sensor."""
        unit_map = {
            "accelerometer_x": "m/s^2",
            "accelerometer_y": "m/s^2",
            "accelerometer_z": "m/s^2",
            "gyroscope_x": "deg/s",
            "gyroscope_y": "deg/s",
            "gyroscope_z": "deg/s",
            "ultrasonic_distance": "cm",
            "cpu_temperature": "C",
            "light_sensor_dark": "bool",
            "light_level": "%",
            "light_status": "status"
        }
        return unit_map.get(sensor_name, "")

    def send_sensor_data(self):
        """Send sensor data to monitoring system."""
        if not self.is_connected:
            logger.warning("Not connected - skipping sensor data send")
            return
        
        try:
            sensors = self.read_sensors()
            sent_count = 0
            
            for sensor_name, value in sensors.items():
                # Skip non-numeric values for certain sensors
                if sensor_name == "light_status":
                    continue  # This is a string, skip it
                    
                data = {
                    "robot_id": self.robot_id,
                    "sensor_type": sensor_name,
                    "value": value,
                    "timestamp": datetime.now().isoformat(),
                    "unit": self.get_sensor_unit(sensor_name)
                }
                result = self.client.publish(self.topics["sensors"], json.dumps(data))
                if result.rc == 0:
                    sent_count += 1
            
            logger.info(f"Sent {sent_count}/{len(sensors)} sensor readings to {self.topics['sensors']}")
            
        except Exception as e:
            logger.error(f"Error sending sensor data: {e}")

    def send_servo_data(self):
        """Send servo status data to monitoring system."""
        if not self.is_connected:
            logger.warning("Not connected - skipping servo data send")
            return
        
        try:
            servo_data = self.get_servo_status()
            
            data = {
                "robot_id": self.robot_id,
                "servos": servo_data,
                "servo_count": len(servo_data),
                "timestamp": datetime.now().isoformat()
            }
            
            result = self.client.publish(self.topics["servos"], json.dumps(data))
            if result.rc == 0:
                logger.info(f"Sent servo data: {len(servo_data)} servos to {self.topics['servos']}")
            else:
                logger.error(f"Failed to send servo data: rc={result.rc}")
            
        except Exception as e:
            logger.error(f"Error sending servo data: {e}")

    def send_battery_status(self):
        """Send battery status with actual voltage reading."""
        if not self.is_connected:
            return
        
        try:
            battery = self.get_battery_percentage()
            
            # Use actual voltage if available, otherwise estimate from percentage
            if hasattr(self, '_last_battery_voltage'):
                voltage = self._last_battery_voltage
            else:
                # Fallback: estimate voltage from percentage (for simulation mode)
                # 3S LiPo: 9.0V (0%) to 12.6V (100%)
                voltage = 9.0 + (battery / 100.0) * 3.6
            
            data = {
                "robot_id": self.robot_id,
                "percentage": round(battery, 1),
                "voltage": round(voltage, 2),
                "charging": False,
                "timestamp": datetime.now().isoformat()
            }
            
            self.client.publish(self.topics["battery"], json.dumps(data))
            logger.debug(f"Sent battery status: {battery:.1f}% ({voltage:.2f}V)")
            
        except Exception as e:
            logger.error(f"Error sending battery status: {e}")

    def send_location_update(self):
        """Send location/position update."""
        if not self.is_connected:
            return
        
        try:
            data = {
                "robot_id": self.robot_id,
                "x": self.location["x"],
                "y": self.location["y"],
                "z": self.location["z"],
                "timestamp": datetime.now().isoformat()
            }
            
            self.client.publish(self.topics["location"], json.dumps(data))
            logger.debug(f"Sent location: {self.location}")
            
        except Exception as e:
            logger.error(f"Error sending location: {e}")

    def send_status_update(self):
        """Send robot status update with full Task Manager metrics."""
        if not self.is_connected:
            logger.warning("Not connected - skipping status update send")
            return
        
        try:
            ip_address = self.get_local_ip()
            camera_url = f"http://{ip_address}:8081/?action=stream"
            system_info = self.get_system_info()
            
            data = {
                "robot_id": self.robot_id,
                "status": self.status,
                "timestamp": datetime.now().isoformat(),
                "system_info": system_info,
                "hardware_available": self.hardware_available,
                "ip_address": ip_address,
                "camera_url": camera_url
            }
            
            result = self.client.publish(self.topics["status"], json.dumps(data))
            if result.rc == 0:
                logger.info(f"Sent status to {self.topics['status']}: CPU={system_info.get('cpu_percent')}%, MEM={system_info.get('memory_percent')}%, TEMP={system_info.get('cpu_temperature')}°C")
            else:
                logger.error(f"Failed to send status: rc={result.rc}")
            
        except Exception as e:
            logger.error(f"Error sending status: {e}")

    def send_vision_data(self, detection_result: Dict[str, Any]):
        """
        Send vision detection results to monitoring system.
        
        Args:
            detection_result: Dictionary containing detection data:
                - label: Detected object class name
                - confidence: Detection confidence (0-1)
                - bbox: Bounding box (x1, y1, x2, y2)
                - center_x: Center X coordinate
                - frame_width: Original frame width
                - state: Current robot state (IDLE, SEARCHING, ACTING)
        """
        if not self.is_connected:
            return
        
        try:
            data = {
                "robot_id": self.robot_id,
                "timestamp": datetime.now().isoformat(),
                "detection": detection_result.get("detection"),
                "label": detection_result.get("label"),
                "confidence": detection_result.get("confidence"),
                "bbox": detection_result.get("bbox"),
                "center_x": detection_result.get("center_x"),
                "frame_width": detection_result.get("frame_width", 640),
                "state": detection_result.get("state", "UNKNOWN"),
                "is_locked": detection_result.get("is_locked", False),
                "navigation_command": detection_result.get("nav_cmd"),
                "error": detection_result.get("error")
            }
            
            self.client.publish(self.topics["vision"], json.dumps(data))
            logger.debug(f"Sent vision data: {detection_result.get('label')} ({detection_result.get('confidence', 0):.2f})")
            
        except Exception as e:
            logger.error(f"Error sending vision data: {e}")

    def send_log_message(self, level: str, message: str, source: str = "main"):
        """
        Send terminal/log message to monitoring system.
        
        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Log message content
            source: Source module/file name
        """
        if not self.is_connected:
            return
        
        try:
            data = {
                "robot_id": self.robot_id,
                "timestamp": datetime.now().isoformat(),
                "level": level.upper(),
                "message": message,
                "source": source
            }
            
            self.client.publish(self.topics["logs"], json.dumps(data))
            
        except Exception as e:
            logger.error(f"Error sending log message: {e}")

    async def connect(self):
        """Connect to MQTT broker."""
        try:
            self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.client.loop_start()
            
            # Wait for connection
            timeout = 10
            while not self.is_connected and timeout > 0:
                await asyncio.sleep(0.5)
                timeout -= 0.5
            
            if not self.is_connected:
                raise Exception("Failed to connect to MQTT broker within timeout")
                
            logger.info("Successfully connected to MQTT broker")
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

    async def disconnect(self):
        """Disconnect from MQTT broker."""
        if self.is_connected:
            self.status = "offline"
            self.send_status_update()
            await asyncio.sleep(1)
        
        # Cleanup light sensor GPIO
        if hasattr(self, 'light_sensor'):
            self.light_sensor.cleanup()
            
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("Disconnected from MQTT broker")

    async def run(self):
        """Main loop for the robot client."""
        self.running = True
        print("=" * 60)
        print("   TONYPI ROBOT CLIENT - MONITORING TELEMETRY")
        print("=" * 60)
        print(f"   Robot ID: {self.robot_id}")
        print(f"   MQTT Broker: {self.mqtt_broker}:{self.mqtt_port}")
        print(f"   Hardware Mode: {self.hardware_available}")
        print("=" * 60)
        
        try:
            await self.connect()
            
            # Send initial data immediately
            print("\n📡 Sending initial telemetry...")
            self.send_status_update()
            self.send_battery_status()
            self.send_sensor_data()
            self.send_servo_data()
            self.send_location_update()
            self.send_log_message("INFO", "Robot client started and connected", "main")
            print("✅ Initial telemetry sent!")
            
            print("\n" + "=" * 60)
            print("✅ ROBOT CLIENT RUNNING - Sending telemetry data")
            print("=" * 60)
            print("Data being sent:")
            print("  • Sensors:  every 2 seconds (IMU, temp, light, ultrasonic)")
            print("  • Servos:   every 3 seconds (position, temp, voltage)")
            print("  • Status:   every 10 seconds (CPU, memory, disk, uptime)")
            print("  • Battery:  every 30 seconds")
            print("  • Location: every 5 seconds")
            print("  • Logs:     real-time")
            print("=" * 60)
            print("\nPress Ctrl+C to stop\n")
            
            last_sensor_time = 0
            last_servo_time = 0
            last_battery_time = 0
            last_location_time = 0
            last_status_time = 0
            last_log_time = 0
            cycle_count = 0
            
            while self.running:
                try:
                    current_time = time.time()
                    cycle_count += 1
                    
                    # Check MQTT connection status
                    if not self.is_connected:
                        print("⚠️  MQTT disconnected, attempting reconnect...")
                        sys.stdout.flush()
                        try:
                            self.client.reconnect()
                            await asyncio.sleep(2)
                        except Exception as e:
                            logger.error(f"Reconnect failed: {e}")
                            await asyncio.sleep(5)
                            continue
                    
                    # Send sensor data every 2 seconds
                    if current_time - last_sensor_time >= 2:
                        self.send_sensor_data()
                        sensors = self.sensors
                        cpu_temp = sensors.get('cpu_temperature', 0)
                        print(f"📊 Sensors: CPU={cpu_temp:.1f}°C, Accel=({sensors.get('accelerometer_x', 0):.2f}, {sensors.get('accelerometer_y', 0):.2f}, {sensors.get('accelerometer_z', 0):.2f})")
                        sys.stdout.flush()
                        last_sensor_time = current_time
                    
                    # Send servo data every 3 seconds
                    if current_time - last_servo_time >= 3:
                        self.send_servo_data()
                        print(f"🔧 Servos: {len(self.servo_data)} servos sent")
                        sys.stdout.flush()
                        last_servo_time = current_time
                    
                    # Send battery status every 30 seconds
                    if current_time - last_battery_time >= 30:
                        self.send_battery_status()
                        print(f"🔋 Battery: {self.battery_level:.1f}%")
                        sys.stdout.flush()
                        last_battery_time = current_time
                    
                    # Send location every 5 seconds
                    if current_time - last_location_time >= 5:
                        self.send_location_update()
                        last_location_time = current_time
                    
                    # Send status every 10 seconds (more frequent for Task Manager)
                    if current_time - last_status_time >= 10:
                        self.send_status_update()
                        sys_info = self.get_system_info()
                        print(f"💻 Status: CPU={sys_info.get('cpu_percent', 0):.1f}%, MEM={sys_info.get('memory_percent', 0):.1f}%, DISK={sys_info.get('disk_usage', 0):.1f}%, TEMP={sys_info.get('cpu_temperature', 0):.1f}°C")
                        sys.stdout.flush()
                        last_status_time = current_time
                    
                    # Send periodic log message every 30 seconds
                    if current_time - last_log_time >= 30:
                        self.send_log_message("INFO", f"Robot running normally. Cycle: {cycle_count}", "telemetry")
                        last_log_time = current_time
                    
                    # Simulate battery drain (very slow)
                    if not self.hardware_available and self.battery_level > 0:
                        self.battery_level = max(0, self.battery_level - 0.001)
                    
                except Exception as loop_error:
                    logger.error(f"Error in telemetry loop: {loop_error}")
                    print(f"⚠️  Loop error: {loop_error}")
                    sys.stdout.flush()
                
                await asyncio.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\n🛑 Stopping robot client...")
            self.send_log_message("INFO", "Robot client stopped by user", "main")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            self.send_log_message("ERROR", f"Robot client error: {e}", "main")
        finally:
            await self.disconnect()
            print("✅ Disconnected from monitoring system")


def main():
    """Main entry point."""
    import argparse
    
    # Get default broker from environment or use localhost
    default_broker = os.getenv("MQTT_BROKER", "localhost")
    default_port = int(os.getenv("MQTT_PORT", 1883))
    default_robot_id = os.getenv("ROBOT_ID", None)
    
    parser = argparse.ArgumentParser(
        description="TonyPi Robot Client - Sends telemetry to monitoring system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tonypi_client.py --broker 192.168.1.100
  python tonypi_client.py --broker 192.168.1.100 --robot-id tonypi_test
  
Environment Variables:
  MQTT_BROKER  - MQTT broker address (default: localhost)
  MQTT_PORT    - MQTT broker port (default: 1883)
  ROBOT_ID     - Robot identifier (default: tonypi_<hostname>)
        """
    )
    parser.add_argument("--broker", default=default_broker, 
                        help=f"MQTT broker address (default: {default_broker})")
    parser.add_argument("--port", type=int, default=default_port, 
                        help=f"MQTT broker port (default: {default_port})")
    parser.add_argument("--robot-id", default=default_robot_id, 
                        help="Robot ID (default: tonypi_<hostname>)")
    
    args = parser.parse_args()
    
    print("\n🤖 TonyPi Robot Client - Monitoring Telemetry")
    print(f"   Connecting to MQTT broker: {args.broker}:{args.port}")
    if args.robot_id:
        print(f"   Robot ID: {args.robot_id}")
    print()
    
    robot = TonyPiRobotClient(
        mqtt_broker=args.broker,
        mqtt_port=args.port,
        robot_id=args.robot_id
    )
    
    try:
        asyncio.run(robot.run())
    except KeyboardInterrupt:
        print("\n👋 Robot client stopped by user")
    except Exception as e:
        print(f"\n❌ Robot client error: {e}")
        logger.error(f"Robot client error: {e}")


if __name__ == "__main__":
    main()
