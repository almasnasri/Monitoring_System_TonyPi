#!/usr/bin/env python3
"""
TonyPi Robot Simulator - Aligned with Current System
=====================================================
Comprehensive simulator that matches the exact data formats and features
of tonypi_client.py for testing all frontend features.

Features:
- All sensor data matching tonypi_client.py format
- System performance metrics (CPU, Memory, Disk, Temperature, Uptime)
- Servo data (6 servos with matching names and format)
- Job simulation with progress tracking
- Multiple test modes for different scenarios
- Terminal log streaming via MQTT
- Interactive command mode
- Head nod/shake simulation

Usage:
    python simulator.py                          # Normal mode
    python simulator.py --mode high-load         # Simulate high CPU/memory
    python simulator.py --mode servo-warning     # Simulate servo issues
    python simulator.py --mode low-battery       # Simulate low battery
    python simulator.py --mode job-demo          # Run job simulation
    python simulator.py --interactive            # Interactive command mode
"""

import asyncio
import sys
import os
import argparse
import random
import math
import time
import json
import threading
import uuid
import platform
import socket
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum

# Add the robot_client directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import paho.mqtt.client as mqtt
import logging

# Try to import psutil for real system metrics (optional)
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TonyPi-Simulator")


class SimulatorMode(Enum):
    """Available simulation modes"""
    NORMAL = "normal"
    HIGH_LOAD = "high-load"
    SERVO_WARNING = "servo-warning"
    LOW_BATTERY = "low-battery"
    JOB_DEMO = "job-demo"
    MOVEMENT_DEMO = "movement-demo"
    ALL_FEATURES = "all-features"


class TonyPiSimulator:
    """
    TonyPi Simulator aligned with tonypi_client.py data formats.
    
    Tested Frontend Pages:
    - Dashboard: Robot status, battery, location
    - Monitoring: CPU, Memory, Disk, Temperature, Uptime
    - Robots: Status, battery, location, sensors, terminal logs
    - Servos: 6 servos with position, temperature, voltage, torque
    - Sensors: Accelerometer, Gyroscope, Ultrasonic, CPU Temperature
    - Jobs: Job progress with items processed
    - Reports: Generates data for reports
    """
    
    # Servo configuration matching tonypi_client.py
    SERVO_NAMES = ["Left Hip", "Left Knee", "Right Hip", "Right Knee", "Head Pan", "Head Tilt"]
    SERVO_COUNT = 6
    
    def __init__(
        self, 
        mqtt_broker: str = "localhost", 
        mqtt_port: int = 1883,
        robot_id: str = None,
        mode: SimulatorMode = SimulatorMode.NORMAL
    ):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.mode = mode
        
        # Generate robot ID similar to tonypi_client.py
        if robot_id:
            self.robot_id = robot_id
        else:
            hostname = platform.node().lower().replace(" ", "_")
            self.robot_id = f"tonypi_{hostname}_sim"
        
        # MQTT Client
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.robot_id)
        self.is_connected = False
        self.running = False
        
        # ==================== ROBOT STATE ====================
        # Battery
        self.battery_level = self._get_initial_battery()
        self.battery_drain_rate = 0.002  # % per second
        
        # Location & Movement
        self.location = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.heading = 0.0
        self.is_moving = False
        self.movement_speed = 0.0
        self.last_movement_time = time.time()
        
        # System Performance (Pi Metrics)
        self.cpu_base = self._get_base_cpu()
        self.memory_base = self._get_base_memory()
        self.disk_usage = random.uniform(35.0, 55.0)
        self.temperature_base = self._get_base_temperature()
        self.start_time = time.time()
        
        # Sensor State
        self.sensors = {}
        
        # Servo State (6 servos for TonyPi - matching tonypi_client.py)
        self.servo_data = self._initialize_servos()
        
        # Job State
        self.job_active = False
        self.job_start_time = None
        self.items_done = 0
        self.items_total = 10
        self.job_history = []
        
        # Terminal Logs
        self.terminal_logs = []
        
        # Hardware simulation flag (always True for simulator)
        self.hardware_available = False  # Simulator mode
        
        # ==================== MQTT TOPICS (matching tonypi_client.py) ====================
        self.topics = {
            "sensors": f"tonypi/sensors/{self.robot_id}",
            "status": f"tonypi/status/{self.robot_id}",
            "location": "tonypi/location",
            "battery": "tonypi/battery",
            "commands": f"tonypi/commands/{self.robot_id}",
            "response": "tonypi/commands/response",
            "servos": f"tonypi/servos/{self.robot_id}",
        }
        
        # Additional topics (matching tonypi_client.py)
        self.items_topic = f"tonypi/items/{self.robot_id}"
        self.scan_topic = f"tonypi/scan/{self.robot_id}"
        self.job_topic = f"tonypi/job/{self.robot_id}"
        self.logs_topic = f"tonypi/logs/{self.robot_id}"  # Aligned with tonypi_client.py
        self.vision_topic = f"tonypi/vision/{self.robot_id}"  # Added for vision data
        
        # Setup MQTT callbacks
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        
        logger.info(f"TonyPi Simulator initialized")
        logger.info(f"  Robot ID: {self.robot_id}")
        logger.info(f"  Mode: {self.mode.value}")
    
    # ==================== INITIALIZATION HELPERS ====================
    
    def _get_initial_battery(self) -> float:
        """Get initial battery based on mode"""
        if self.mode == SimulatorMode.LOW_BATTERY:
            return random.uniform(5.0, 20.0)
        return random.uniform(70.0, 100.0)
    
    def _get_base_cpu(self) -> float:
        """Get base CPU based on mode"""
        if self.mode == SimulatorMode.HIGH_LOAD:
            return random.uniform(75.0, 95.0)
        return random.uniform(15.0, 35.0)
    
    def _get_base_memory(self) -> float:
        """Get base memory based on mode"""
        if self.mode == SimulatorMode.HIGH_LOAD:
            return random.uniform(80.0, 95.0)
        return random.uniform(40.0, 60.0)
    
    def _get_base_temperature(self) -> float:
        """Get base temperature based on mode"""
        if self.mode == SimulatorMode.HIGH_LOAD:
            return random.uniform(65.0, 80.0)
        return random.uniform(40.0, 55.0)
    
    def _initialize_servos(self) -> Dict[str, Dict]:
        """Initialize 6 servos matching tonypi_client.py format"""
        servos = {}
        
        for idx in range(1, self.SERVO_COUNT + 1):
            # Servo warning mode: some servos have high temp
            if self.mode == SimulatorMode.SERVO_WARNING and idx in [2, 4]:
                base_temp = random.uniform(65.0, 80.0)
            else:
                base_temp = random.uniform(40.0, 55.0)
            
            servo_name = self.SERVO_NAMES[idx - 1] if idx <= len(self.SERVO_NAMES) else f"Servo {idx}"
            
            servos[f"servo_{idx}"] = {
                "id": idx,
                "name": servo_name,
                "position": round(random.uniform(-45, 45), 1),
                "temperature": round(base_temp, 1),
                "voltage": round(random.uniform(4.8, 5.2), 2),
                "torque_enabled": True,
                "alert_level": "warning" if base_temp > 60 else "normal",
                "target_position": 0.0,
            }
        
        return servos
    
    # ==================== MQTT CALLBACKS ====================
    
    def on_connect(self, client, userdata, flags, rc, properties=None):
        """Handle MQTT connection"""
        if rc == 0:
            self.is_connected = True
            logger.info(f"Connected to MQTT broker at {self.mqtt_broker}:{self.mqtt_port}")
            
            # Subscribe to commands
            client.subscribe(self.topics["commands"])
            client.subscribe("tonypi/commands/broadcast")
            client.subscribe(self.items_topic)
            
            # Send initial status
            self.add_terminal_log("SYSTEM", "Connected to MQTT broker")
            self.send_status_update()
        else:
            logger.error(f"Connection failed with code: {rc}")
    
    def on_disconnect(self, client, userdata, flags=None, rc=None, properties=None):
        """Handle MQTT disconnection"""
        self.is_connected = False
        logger.warning(f"Disconnected from MQTT broker")
    
    def on_message(self, client, userdata, msg):
        """Handle incoming commands (matching tonypi_client.py)"""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            command_type = payload.get("type", "unknown")
            command_id = payload.get("id", str(uuid.uuid4()))
            
            self.add_terminal_log("COMMAND", f"Received: {command_type}")
            logger.info(f"Received command on {topic}: {command_type}")
            
            response = {
                "robot_id": self.robot_id,
                "command_id": command_id,
                "timestamp": datetime.now().isoformat(),
                "success": True,
                "message": f"Command {command_type} executed"
            }
            
            # Handle commands matching tonypi_client.py
            if command_type == "move":
                response = self._handle_move_command(payload)
            elif command_type == "stop":
                response = self._handle_stop_command(payload)
            elif command_type == "status_request":
                response = self._handle_status_request(payload)
            elif command_type == "battery_request":
                response = self._handle_battery_request(payload)
            elif command_type == "shutdown":
                response = self._handle_shutdown_command(payload)
            elif command_type == "head_nod":
                response = self._handle_head_nod(payload)
            elif command_type == "head_shake":
                response = self._handle_head_shake(payload)
            elif command_type == "start_job":
                self._start_job(payload)
                response["message"] = "Job started"
            elif command_type == "stop_job":
                self._stop_job()
                response["message"] = "Job stopped"
            elif command_type == "set_servo":
                servo_id = payload.get("servo_id", 1)
                position = payload.get("position", 0)
                self._set_servo_position(servo_id, position)
                response["message"] = f"Servo {servo_id} set to {position}"
            elif topic.startswith("tonypi/items/"):
                response = self._handle_item_info(payload)
            
            # Publish response
            self.client.publish(self.topics["response"], json.dumps(response))
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    def _handle_item_info(self, payload: Dict) -> Dict:
        """Handle item info responses (matching tonypi_client.py)"""
        response = {
            "robot_id": self.robot_id,
            "timestamp": datetime.now().isoformat(),
            "success": payload.get('found', False),
            "item": payload.get('item'),
            "message": payload.get('message', 'Item info')
        }
        
        # Update job progress
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
        
        return response
    
    # ==================== COMMAND HANDLERS (matching tonypi_client.py) ====================
    
    def _handle_move_command(self, payload: Dict) -> Dict:
        """Handle movement commands"""
        direction = payload.get("direction", "forward")
        distance = payload.get("distance", 1.0)
        speed = payload.get("speed", 0.5)
        
        self.is_moving = True
        self.movement_speed = speed
        self.last_movement_time = time.time()
        
        # Update position
        if direction == "forward":
            self.location["x"] += distance * math.cos(math.radians(self.heading))
            self.location["y"] += distance * math.sin(math.radians(self.heading))
        elif direction == "backward":
            self.location["x"] -= distance * math.cos(math.radians(self.heading))
            self.location["y"] -= distance * math.sin(math.radians(self.heading))
        elif direction == "left":
            self.location["y"] -= distance
        elif direction == "right":
            self.location["y"] += distance
        
        # Battery consumption
        self.battery_level = max(0, self.battery_level - (distance * 0.1))
        
        self.add_terminal_log("MOTOR", f"Moving {direction} dist={distance:.2f}")
        
        return {
            "robot_id": self.robot_id,
            "command_id": payload.get("id"),
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "message": f"Moved {direction} for {distance} units",
            "new_location": self.location.copy(),
            "battery_level": self.battery_level
        }
    
    def _handle_stop_command(self, payload: Dict) -> Dict:
        """Handle stop command"""
        self.is_moving = False
        self.movement_speed = 0.0
        self.add_terminal_log("MOTOR", "All motors stopped")
        
        return {
            "robot_id": self.robot_id,
            "command_id": payload.get("id"),
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "message": "Robot stopped successfully"
        }
    
    def _handle_status_request(self, payload: Dict) -> Dict:
        """Handle status request"""
        return {
            "robot_id": self.robot_id,
            "command_id": payload.get("id"),
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "message": "Status retrieved",
            "data": {
                "status": "online",
                "battery_level": self.battery_level,
                "location": self.location.copy(),
                "sensors": self.sensors.copy(),
                "system_info": self.get_system_info(),
                "hardware_available": self.hardware_available
            }
        }
    
    def _handle_battery_request(self, payload: Dict) -> Dict:
        """Handle battery status request"""
        return {
            "robot_id": self.robot_id,
            "command_id": payload.get("id"),
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "message": "Battery status retrieved",
            "data": {
                "battery_level": self.battery_level,
                "charging": False,
                "estimated_time": self.battery_level * 2
            }
        }
    
    def _handle_shutdown_command(self, payload: Dict) -> Dict:
        """Handle shutdown command"""
        logger.info("Shutting down simulator")
        self.running = False
        return {
            "robot_id": self.robot_id,
            "command_id": payload.get("id"),
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "message": "Robot shutting down"
        }
    
    def _handle_head_nod(self, payload: Dict) -> Dict:
        """Simulate head nod"""
        self.add_terminal_log("HEAD", "Nodding head")
        # Simulate servo movement
        self._set_servo_position(5, 20)
        time.sleep(0.1)
        self._set_servo_position(5, -20)
        time.sleep(0.1)
        self._set_servo_position(5, 0)
        
        return {
            "robot_id": self.robot_id,
            "command_id": payload.get("id"),
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "message": "Head nod completed"
        }
    
    def _handle_head_shake(self, payload: Dict) -> Dict:
        """Simulate head shake"""
        self.add_terminal_log("HEAD", "Shaking head")
        # Simulate servo movement
        self._set_servo_position(6, 30)
        time.sleep(0.1)
        self._set_servo_position(6, -30)
        time.sleep(0.1)
        self._set_servo_position(6, 0)
        
        return {
            "robot_id": self.robot_id,
            "command_id": payload.get("id"),
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "message": "Head shake completed"
        }
    
    # ==================== JOB SIMULATION ====================
    
    def _start_job(self, payload: Dict = None):
        """Start a simulated job"""
        self.job_active = True
        self.job_start_time = datetime.now().isoformat()
        self.items_done = 0
        self.items_total = payload.get("items_total", 10) if payload else 10
        self.job_history = []
        self.add_terminal_log("JOB", f"Started job with {self.items_total} items")
    
    def _stop_job(self):
        """Stop current job"""
        self.job_active = False
        self.add_terminal_log("JOB", f"Job stopped. Completed {self.items_done}/{self.items_total}")
    
    def _process_job_item(self):
        """Process one item in the job"""
        if not self.job_active or self.items_done >= self.items_total:
            return
        
        self.items_done += 1
        item_data = {
            "item_id": f"ITEM_{self.items_done:04d}",
            "barcode": f"QR{random.randint(10000, 99999)}",
            "status": "processed",
            "timestamp": datetime.now().isoformat()
        }
        
        self.job_history.append({
            "time": datetime.now().isoformat(),
            "item": item_data
        })
        
        self.job_history = self.job_history[-10:]
        self.add_terminal_log("JOB", f"Processed item {self.items_done}/{self.items_total}")
        
        if self.items_done >= self.items_total:
            self.job_active = False
            self.add_terminal_log("JOB", "Job completed successfully!")
    
    # ==================== DATA GENERATION (matching tonypi_client.py) ====================
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get system information (matching tonypi_client.py format exactly)"""
        cpu_temp = self.get_cpu_temperature()
        
        if PSUTIL_AVAILABLE:
            try:
                # Use interval=None for non-blocking CPU measurement (matching tonypi_client.py)
                cpu_percent = psutil.cpu_percent(interval=None)
                return {
                    "platform": platform.platform(),
                    "cpu_percent": cpu_percent,
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_usage": psutil.disk_usage('/').percent if os.name != 'nt' else psutil.disk_usage('C:').percent,
                    "temperature": cpu_temp,           # Legacy field
                    "cpu_temperature": cpu_temp,       # New field for frontend (matching tonypi_client.py)
                    "uptime": time.time() - psutil.boot_time(),
                    "hardware_mode": self.hardware_available,
                    "hardware_sdk": self.hardware_available  # Added for consistency with tonypi_client.py
                }
            except Exception as e:
                logger.error(f"Error getting system info: {e}")
        
        # Fallback simulation
        return {
            "platform": f"TonyPi Simulator ({platform.platform()})",
            "cpu_percent": self.cpu_base + random.uniform(-5, 5),
            "memory_percent": self.memory_base + random.uniform(-3, 3),
            "disk_usage": self.disk_usage,
            "temperature": cpu_temp,           # Legacy field
            "cpu_temperature": cpu_temp,       # New field for frontend (matching tonypi_client.py)
            "uptime": time.time() - self.start_time,
            "hardware_mode": self.hardware_available,
            "hardware_sdk": self.hardware_available  # Added for consistency with tonypi_client.py
        }
    
    def get_cpu_temperature(self) -> float:
        """Get CPU temperature (matching tonypi_client.py)"""
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                return float(f.read()) / 1000.0
        except:
            # Simulation
            current_time = time.time()
            variation = 5.0 * math.sin(current_time / 30.0)
            return round(self.temperature_base + variation + random.uniform(-2, 2), 1)
    
    def get_local_ip(self) -> str:
        """Get the local IP address of the robot/simulator."""
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
    
    def read_sensors(self) -> Dict[str, float]:
        """Read sensor data (matching tonypi_client.py format)"""
        current_time = time.time()
        
        # IMU sensors (accelerometer + gyroscope)
        accel_x = round(random.uniform(-0.5, 0.5), 3)
        accel_y = round(random.uniform(-0.5, 0.5), 3)
        accel_z = round(random.uniform(9.5, 10.0), 3)  # Gravity
        
        if self.is_moving:
            accel_x += self.movement_speed * 0.3
        
        gyro_x = round(random.uniform(-10, 10), 2)
        gyro_y = round(random.uniform(-10, 10), 2)
        gyro_z = round(random.uniform(-10, 10), 2)
        
        if self.is_moving:
            gyro_z += self.movement_speed * 15.0
        
        # Ultrasonic distance
        base_distance = 100.0
        obstacle_factor = 50.0 * math.sin(current_time / 8.0)
        distance = base_distance - obstacle_factor + random.uniform(-10, 10)
        distance = max(5.0, min(200.0, distance))
        
        # Light sensor (matching tonypi_client.py format)
        # Varies with time to simulate day/night or lighting changes
        light_base = 60.0  # Base light level (0-100%)
        light_variation = 20.0 * math.sin(current_time / 60.0)  # Slow variation
        light_level = light_base + light_variation + random.uniform(-5, 5)
        light_level = max(0.0, min(100.0, light_level))
        is_dark = light_level < 30  # Dark if below 30%
        
        sensors = {
            "accelerometer_x": accel_x,
            "accelerometer_y": accel_y,
            "accelerometer_z": accel_z,
            "gyroscope_x": gyro_x,
            "gyroscope_y": gyro_y,
            "gyroscope_z": gyro_z,
            "ultrasonic_distance": round(distance, 1),
            "cpu_temperature": self.get_cpu_temperature(),
            # Light sensor fields matching tonypi_client.py
            "light_sensor_dark": 1 if is_dark else 0,
            "light_level": round(light_level, 1),
        }
        
        self.sensors = sensors
        return sensors
    
    def get_servo_status(self) -> Dict[str, Dict]:
        """Get servo status (matching tonypi_client.py format)"""
        current_time = time.time()
        
        for servo_key, servo in self.servo_data.items():
            # Position oscillation
            base_pos = servo.get("target_position", 0.0)
            oscillation = 3.0 * math.sin(current_time / 4.0 + servo["id"])
            servo["position"] = round(base_pos + oscillation + random.uniform(-1, 1), 1)
            
            # Temperature with activity-based increase
            temp_base = 45.0
            if self.mode == SimulatorMode.SERVO_WARNING and servo["id"] in [2, 4]:
                temp_base = 70.0
            
            temp_variation = 3.0 * math.sin(current_time / 20.0 + servo["id"])
            if self.is_moving:
                temp_variation += 5.0
            
            servo["temperature"] = round(
                min(85.0, max(35.0, temp_base + temp_variation + random.uniform(-1, 1))), 1
            )
            
            # Voltage
            servo["voltage"] = round(5.0 + random.uniform(-0.2, 0.2), 2)
            
            # Alert level (matching tonypi_client.py logic)
            if servo["temperature"] > 70:
                servo["alert_level"] = "critical"
            elif servo["temperature"] > 60:
                servo["alert_level"] = "warning"
            else:
                servo["alert_level"] = "normal"
        
        return self.servo_data
    
    def _set_servo_position(self, servo_id: int, position: float):
        """Set target position for a servo"""
        key = f"servo_{servo_id}"
        if key in self.servo_data:
            self.servo_data[key]["target_position"] = max(-90, min(90, position))
            self.add_terminal_log("SERVO", f"Servo {servo_id} target: {position}")
    
    def get_sensor_unit(self, sensor_name: str) -> str:
        """Get sensor unit (matching tonypi_client.py exactly)"""
        unit_map = {
            "accelerometer_x": "m/s^2",
            "accelerometer_y": "m/s^2",
            "accelerometer_z": "m/s^2",
            "gyroscope_x": "deg/s",
            "gyroscope_y": "deg/s",
            "gyroscope_z": "deg/s",
            "ultrasonic_distance": "cm",
            "cpu_temperature": "C",
            # Light sensor units matching tonypi_client.py
            "light_sensor_dark": "bool",
            "light_level": "%",
            "light_status": "status",
            # System metrics
            "system_cpu_percent": "%",
            "system_memory_percent": "%",
            "system_disk_usage": "%",
            "system_temperature": "C",
            "system_uptime": "s",
        }
        return unit_map.get(sensor_name, "")
    
    # ==================== TERMINAL LOGGING ====================
    
    def add_terminal_log(self, category: str, message: str, send_mqtt: bool = False):
        """Add a terminal log entry and optionally send via MQTT"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] [{category}] {message}"
        self.terminal_logs.append(log_entry)
        self.terminal_logs = self.terminal_logs[-100:]
        logger.debug(log_entry)
        
        # Optionally send to MQTT (matching tonypi_client.py behavior)
        if send_mqtt and self.is_connected:
            self.send_log_message("INFO", message, category.lower())
    
    # ==================== DATA SENDING (matching tonypi_client.py) ====================
    
    def send_sensor_data(self):
        """Send sensor data (matching tonypi_client.py format)"""
        if not self.is_connected:
            return
        
        try:
            sensors = self.read_sensors()
            
            # Also add system performance metrics
            sys_info = self.get_system_info()
            sensors["system_cpu_percent"] = sys_info["cpu_percent"]
            sensors["system_memory_percent"] = sys_info["memory_percent"]
            sensors["system_disk_usage"] = sys_info["disk_usage"]
            sensors["system_temperature"] = sys_info["temperature"]
            sensors["system_uptime"] = sys_info["uptime"]
            
            # Send each sensor as individual message (matching tonypi_client.py)
            for sensor_name, value in sensors.items():
                data = {
                    "robot_id": self.robot_id,
                    "sensor_type": sensor_name,
                    "value": value,
                    "timestamp": datetime.now().isoformat(),
                    "unit": self.get_sensor_unit(sensor_name)
                }
                self.client.publish(self.topics["sensors"], json.dumps(data))
            
            logger.debug(f"Sent {len(sensors)} sensor readings")
            
        except Exception as e:
            logger.error(f"Error sending sensor data: {e}")
    
    def send_servo_data(self):
        """Send servo status (matching tonypi_client.py format)"""
        if not self.is_connected:
            return
        
        try:
            servo_data = self.get_servo_status()
            
            data = {
                "robot_id": self.robot_id,
                "servos": servo_data,
                "servo_count": len(servo_data),
                "timestamp": datetime.now().isoformat()
            }
            
            self.client.publish(self.topics["servos"], json.dumps(data))
            logger.debug(f"Sent servo data: {len(servo_data)} servos")
            
        except Exception as e:
            logger.error(f"Error sending servo data: {e}")
    
    def send_battery_status(self):
        """Send battery status (matching tonypi_client.py format exactly)"""
        if not self.is_connected:
            return
        
        try:
            # Drain battery
            drain = self.battery_drain_rate
            if self.is_moving:
                drain *= 3
            if self.job_active:
                drain *= 2
            
            self.battery_level = max(0, self.battery_level - drain)
            
            if self.battery_level < 15 and self.battery_level > 14.9:
                self.add_terminal_log("BATTERY", "WARNING: Low battery!")
            
            # Calculate voltage using same formula as tonypi_client.py
            # 3S LiPo: 9.0V (0%) to 12.6V (100%)
            voltage = 9.0 + (self.battery_level / 100.0) * 3.6
            
            data = {
                "robot_id": self.robot_id,
                "percentage": round(self.battery_level, 1),
                "voltage": round(voltage, 2),
                "charging": False,
                "timestamp": datetime.now().isoformat()
            }
            
            self.client.publish(self.topics["battery"], json.dumps(data))
            
        except Exception as e:
            logger.error(f"Error sending battery: {e}")
    
    def send_location_update(self):
        """Send location update (matching tonypi_client.py format)"""
        if not self.is_connected:
            return
        
        try:
            data = {
                "robot_id": self.robot_id,
                "x": round(self.location["x"], 2),
                "y": round(self.location["y"], 2),
                "z": round(self.location["z"], 2),
                "timestamp": datetime.now().isoformat()
            }
            
            self.client.publish(self.topics["location"], json.dumps(data))
            
        except Exception as e:
            logger.error(f"Error sending location: {e}")
    
    def send_status_update(self):
        """Send robot status (matching tonypi_client.py format)"""
        if not self.is_connected:
            return
        
        try:
            ip_address = self.get_local_ip()
            camera_url = f"http://{ip_address}:8081/?action=stream"
            
            data = {
                "robot_id": self.robot_id,
                "status": "online",
                "timestamp": datetime.now().isoformat(),
                "system_info": self.get_system_info(),
                "hardware_available": self.hardware_available,
                "ip_address": ip_address,
                "camera_url": camera_url
            }
            
            self.client.publish(self.topics["status"], json.dumps(data))
            self.add_terminal_log("STATUS", f"Status update sent (IP: {ip_address})")
            
        except Exception as e:
            logger.error(f"Error sending status: {e}")
    
    def send_job_update(self):
        """Send job progress update"""
        if not self.is_connected:
            return
        
        try:
            percent = round((self.items_done / max(1, self.items_total)) * 100, 2)
            
            data = {
                "robot_id": self.robot_id,
                "start_time": self.job_start_time,
                "end_time": None if self.job_active else datetime.now().isoformat(),
                "items_total": self.items_total,
                "items_done": self.items_done,
                "percent": percent,
                "status": "working" if self.job_active else ("completed" if self.items_done >= self.items_total else "idle"),
                "last_item": self.job_history[-1]["item"] if self.job_history else None,
                "history": self.job_history[-5:],
                "timestamp": datetime.now().isoformat()
            }
            
            self.client.publish(self.job_topic, json.dumps(data))
            
        except Exception as e:
            logger.error(f"Error sending job update: {e}")
    
    def send_log_message(self, level: str, message: str, source: str = "main"):
        """
        Send terminal/log message to monitoring system (matching tonypi_client.py).
        
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
            
            self.client.publish(self.logs_topic, json.dumps(data))
            
        except Exception as e:
            logger.error(f"Error sending log message: {e}")
    
    def send_vision_data(self, detection_result: Dict[str, Any]):
        """
        Send vision detection results to monitoring system (matching tonypi_client.py).
        
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
            
            self.client.publish(self.vision_topic, json.dumps(data))
            logger.debug(f"Sent vision data: {detection_result.get('label')} ({detection_result.get('confidence', 0):.2f})")
            
        except Exception as e:
            logger.error(f"Error sending vision data: {e}")
    
    # ==================== MAIN LOOP ====================
    
    async def connect(self):
        """Connect to MQTT broker"""
        try:
            self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.client.loop_start()
            
            timeout = 10
            while not self.is_connected and timeout > 0:
                await asyncio.sleep(0.5)
                timeout -= 0.5
            
            if not self.is_connected:
                raise Exception("Connection timeout")
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from MQTT broker (matching tonypi_client.py)"""
        if self.is_connected:
            # Send final log message
            self.send_log_message("INFO", "Robot simulator stopped", "main")
            
            # Send offline status
            offline_data = {
                "robot_id": self.robot_id,
                "status": "offline",
                "timestamp": datetime.now().isoformat()
            }
            self.client.publish(self.topics["status"], json.dumps(offline_data))
            await asyncio.sleep(0.5)
        
        self.client.loop_stop()
        self.client.disconnect()
    
    async def run(self):
        """Main simulation loop"""
        self.running = True
        
        print("\n" + "="*60)
        print("   TONYPI ROBOT SIMULATOR - MONITORING TELEMETRY")
        print("="*60)
        print(f"   Robot ID: {self.robot_id}")
        print(f"   Mode: {self.mode.value}")
        print(f"   MQTT Broker: {self.mqtt_broker}:{self.mqtt_port}")
        print(f"   Hardware Mode: {self.hardware_available} (simulation)")
        print("="*60)
        
        try:
            await self.connect()
            print("✅ Connected to MQTT broker successfully!")
            
            # Send initial data immediately (matching tonypi_client.py)
            print("\n📡 Sending initial telemetry...")
            self.send_status_update()
            self.send_battery_status()
            self.send_sensor_data()
            self.send_servo_data()
            self.send_location_update()
            self.send_log_message("INFO", "Robot simulator started and connected", "main")
            print("✅ Initial telemetry sent!")
            
            print("\n" + "="*60)
            print("✅ SIMULATOR RUNNING - Sending telemetry data")
            print("="*60)
            print("Data being sent (matching tonypi_client.py intervals):")
            print("  • Sensors:  every 2 seconds (IMU, temp, light, ultrasonic)")
            print("  • Servos:   every 3 seconds (position, temp, voltage)")
            print("  • Status:   every 10 seconds (CPU, memory, disk, uptime)")
            print("  • Battery:  every 30 seconds")
            print("  • Location: every 5 seconds")
            print("  • Logs:     every 30 seconds")
            print("="*60)
            print("\nPress Ctrl+C to stop\n")
            
            # Auto-start scenarios based on mode
            if self.mode == SimulatorMode.JOB_DEMO:
                self._start_job({"items_total": 15})
            
            if self.mode == SimulatorMode.MOVEMENT_DEMO:
                self.is_moving = True
                self.movement_speed = 0.5
            
            # Timing trackers (matching tonypi_client.py intervals)
            last_sensor_time = 0
            last_servo_time = 0
            last_battery_time = 0
            last_location_time = 0
            last_status_time = 0
            last_job_time = 0
            last_terminal_time = 0
            last_job_process = 0
            
            loop_count = 0
            
            while self.running:
                current_time = time.time()
                loop_count += 1
                
                # Stop movement after delay
                if self.is_moving and (current_time - self.last_movement_time) > 3.0:
                    if self.mode != SimulatorMode.MOVEMENT_DEMO:
                        self.is_moving = False
                        self.movement_speed = 0.0
                
                # Send sensor data every 2 seconds (matching tonypi_client.py)
                if current_time - last_sensor_time >= 2:
                    self.send_sensor_data()
                    sensors = self.sensors
                    cpu_temp = sensors.get('cpu_temperature', 0)
                    print(f"📊 Sensors: CPU={cpu_temp:.1f}°C, Accel=({sensors.get('accelerometer_x', 0):.2f}, {sensors.get('accelerometer_y', 0):.2f}, {sensors.get('accelerometer_z', 0):.2f})")
                    last_sensor_time = current_time
                
                # Send servo data every 3 seconds (matching tonypi_client.py)
                if current_time - last_servo_time >= 3:
                    self.send_servo_data()
                    print(f"🔧 Servos: {len(self.servo_data)} servos sent")
                    last_servo_time = current_time
                
                # Send battery every 30 seconds (matching tonypi_client.py)
                if current_time - last_battery_time >= 30:
                    self.send_battery_status()
                    print(f"🔋 Battery: {self.battery_level:.1f}%")
                    last_battery_time = current_time
                
                # Send location every 5 seconds (matching tonypi_client.py)
                if current_time - last_location_time >= 5:
                    self.send_location_update()
                    last_location_time = current_time
                
                # Send status every 10 seconds (matching tonypi_client.py)
                if current_time - last_status_time >= 10:
                    self.send_status_update()
                    sys_info = self.get_system_info()
                    print(f"💻 Status: CPU={sys_info.get('cpu_percent', 0):.1f}%, MEM={sys_info.get('memory_percent', 0):.1f}%, TEMP={sys_info.get('temperature', 0):.1f}°C")
                    last_status_time = current_time
                
                # Process job items every 5 seconds
                if self.job_active and current_time - last_job_process >= 5:
                    self._process_job_item()
                    last_job_process = current_time
                
                # Send job update every 3 seconds
                if current_time - last_job_time >= 3:
                    self.send_job_update()
                    last_job_time = current_time
                
                # Send periodic log message every 30 seconds (matching tonypi_client.py)
                if current_time - last_terminal_time >= 30:
                    self.send_log_message("INFO", f"Robot running normally. Cycle: {loop_count}", "telemetry")
                    last_terminal_time = current_time
                
                await asyncio.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\nShutting down...")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            await self.disconnect()
            print("Simulator stopped")


def run_interactive_mode(simulator: TonyPiSimulator):
    """Run interactive command mode"""
    print("\n--- Interactive Mode ---")
    print("Commands: move, stop, job_start, job_stop, servo, status, quit")
    print("------------------------\n")
    
    while simulator.running:
        try:
            cmd = input("> ").strip().lower()
            
            if cmd == "quit" or cmd == "q":
                simulator.running = False
                break
            elif cmd == "move":
                direction = input("Direction (forward/backward/left/right): ").strip()
                simulator._handle_move_command({"direction": direction, "distance": 1.0, "speed": 0.5})
            elif cmd == "stop":
                simulator._handle_stop_command({})
            elif cmd == "job_start":
                items = int(input("Number of items: ") or "10")
                simulator._start_job({"items_total": items})
            elif cmd == "job_stop":
                simulator._stop_job()
            elif cmd == "servo":
                servo_id = int(input("Servo ID (1-6): "))
                position = float(input("Position (-90 to 90): "))
                simulator._set_servo_position(servo_id, position)
            elif cmd == "nod":
                simulator._handle_head_nod({})
            elif cmd == "shake":
                simulator._handle_head_shake({})
            elif cmd == "status":
                print(f"Battery: {simulator.battery_level:.1f}%")
                print(f"Location: {simulator.location}")
                print(f"Moving: {simulator.is_moving}")
                print(f"Job Active: {simulator.job_active} ({simulator.items_done}/{simulator.items_total})")
            else:
                print("Unknown command. Try: move, stop, job_start, job_stop, servo, nod, shake, status, quit")
                
        except (EOFError, KeyboardInterrupt):
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="TonyPi Robot Simulator (Aligned with tonypi_client.py)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test Modes:
  normal          Standard simulation with moderate values
  high-load       High CPU/memory usage simulation
  servo-warning   Simulate servo temperature warnings
  low-battery     Start with low battery level
  job-demo        Auto-start job simulation
  movement-demo   Continuous movement simulation
  all-features    Enable all test scenarios

Examples:
  python simulator.py                     # Normal mode
  python simulator.py --mode high-load    # Test high load warnings
  python simulator.py --mode servo-warning # Test servo alerts
  python simulator.py --interactive       # Enable interactive commands
        """
    )
    
    parser.add_argument("--broker", default="localhost", help="MQTT broker address")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--robot-id", default=None, help="Robot ID (auto-generated if not set)")
    parser.add_argument(
        "--mode", 
        choices=[m.value for m in SimulatorMode],
        default="normal",
        help="Simulation mode"
    )
    parser.add_argument("--interactive", action="store_true", help="Enable interactive command mode")
    
    args = parser.parse_args()
    
    mode = SimulatorMode(args.mode)
    
    simulator = TonyPiSimulator(
        mqtt_broker=args.broker,
        mqtt_port=args.port,
        robot_id=args.robot_id,
        mode=mode
    )
    
    # Run interactive mode in background thread if requested
    if args.interactive:
        interactive_thread = threading.Thread(target=run_interactive_mode, args=(simulator,), daemon=True)
        interactive_thread.start()
    
    try:
        asyncio.run(simulator.run())
    except KeyboardInterrupt:
        print("\nSimulator stopped by user")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
