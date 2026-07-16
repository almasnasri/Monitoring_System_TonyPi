#!/usr/bin/env python3
"""
TonyPi Robot Client Module - MQTT Telemetry + Camera Streaming

This module provides:
1. MQTT telemetry for sending robot data to monitoring system
2. MJPEG camera streaming server (receives frames from main.py)

Usage:
    from modules.robot_client import RobotClient
    
    client = RobotClient(mqtt_broker="192.168.1.100", camera_port=8081)
    client.start()  # Connects MQTT + starts camera server
    
    # In your main loop:
    client.update_frame(frame)  # Pass camera frame from main.py
    client.send_vision_data(detection_result)
    client.send_sensor_data(sensors)
    
    # When done:
    client.stop()
"""

import sys
import os
import json
import time
import threading
import platform
import socket
import psutil
import random
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import logging

# Try to import OpenCV for frame encoding
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("RobotClient")

# Try to import MQTT
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logger.warning("paho-mqtt not installed. Run: pip install paho-mqtt")

# Try to import HiWonder SDK for real hardware access
HARDWARE_SDK_AVAILABLE = False
board = None
controller = None

try:
    # Add TonyPi SDK path
    if os.path.exists('/home/pi/TonyPi'):
        sys.path.insert(0, '/home/pi/TonyPi/HiwonderSDK')
        sys.path.insert(0, '/home/pi/TonyPi')
    
    from hiwonder import ros_robot_controller_sdk as rrc
    from hiwonder.Controller import Controller
    
    # Initialize hardware
    board = rrc.Board()
    controller = Controller(board)
    board.enable_reception(True)
    
    HARDWARE_SDK_AVAILABLE = True
    logger.info(f"HiWonder SDK loaded. Hardware mode: {HARDWARE_SDK_AVAILABLE}")
except ImportError as e:
    logger.warning(f"HiWonder SDK not available: {e}")
except Exception as e:
    logger.warning(f"Hardware initialization failed: {e}")


# ==========================================
# MJPEG CAMERA STREAMING SERVER
# ==========================================

# Global frame storage for HTTP handler access
_current_frame = None
_frame_lock = threading.Lock()


class MJPEGHandler(BaseHTTPRequestHandler):
    """HTTP request handler for MJPEG streaming."""
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def do_GET(self):
        """Handle GET requests."""
        global _current_frame
        
        # Handle root/status request
        if self.path == '/' or self.path == '/test' or self.path == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            with _frame_lock:
                has_frame = _current_frame is not None
                frame_shape = _current_frame.shape if has_frame else None
            
            status = "OK - Receiving frames" if has_frame else "Waiting for frames from main.py"
            frame_info = f"{frame_shape}" if frame_shape else "None"
            
            html = f"""
            <html>
            <head><title>TonyPi Camera Stream</title></head>
            <body style="font-family: Arial; background: #1a1a2e; color: white; padding: 20px;">
                <h1>🤖 TonyPi Camera Stream</h1>
                <p><b>Status:</b> {status}</p>
                <p><b>Frame shape:</b> {frame_info}</p>
                <hr>
                <p><a href="/?action=stream" style="color: #00ff88;">📹 MJPEG Stream</a></p>
                <p><a href="/?action=snapshot" style="color: #00ff88;">📷 Snapshot</a></p>
                <hr>
                <p style="color: #888;">Frames are provided by main.py camera loop</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            return
        
        # Handle snapshot request
        if 'action=snapshot' in self.path:
            with _frame_lock:
                frame = _current_frame.copy() if _current_frame is not None else None
            
            if frame is not None and CV2_AVAILABLE:
                try:
                    ret, jpg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                    if ret:
                        jpg_bytes = jpg.tobytes()
                        self.send_response(200)
                        self.send_header('Content-type', 'image/jpeg')
                        self.send_header('Content-length', len(jpg_bytes))
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(jpg_bytes)
                    else:
                        self.send_error(500, 'Failed to encode image')
                except Exception as e:
                    logger.error(f'Snapshot error: {e}')
                    self.send_error(500, str(e))
            else:
                self.send_error(503, 'No frame available')
            return
        
        # Handle MJPEG stream request
        if 'action=stream' in self.path or self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=--frame')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            
            logger.info(f'Camera stream started for {self.client_address[0]}')
            
            while True:
                try:
                    with _frame_lock:
                        frame = _current_frame.copy() if _current_frame is not None else None
                    
                    if frame is not None and CV2_AVAILABLE:
                        ret, jpg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                        if ret:
                            jpg_bytes = jpg.tobytes()
                            self.wfile.write(b'--frame\r\n')
                            self.wfile.write(b'Content-Type: image/jpeg\r\n')
                            self.wfile.write(f'Content-Length: {len(jpg_bytes)}\r\n\r\n'.encode())
                            self.wfile.write(jpg_bytes)
                            self.wfile.write(b'\r\n')
                            self.wfile.flush()
                    
                    # ~30 FPS
                    time.sleep(0.033)
                    
                except (ConnectionResetError, BrokenPipeError, OSError):
                    logger.info(f'Camera stream ended for {self.client_address[0]}')
                    break
                except Exception as e:
                    logger.error(f'Stream error: {e}')
                    break
            return
        
        # Default: redirect to status page
        self.send_response(302)
        self.send_header('Location', '/')
        self.end_headers()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in separate threads."""
    daemon_threads = True
    allow_reuse_address = True


class RobotClient:
    """
    Robot Client for sending telemetry to monitoring system.
    
    This is a lightweight wrapper designed to be used from main.py.
    It handles MQTT connection in the background and provides simple
    methods to send various types of data.
    """
    
    def __init__(
        self,
        mqtt_broker: str = "localhost",
        mqtt_port: int = 1883,
        robot_id: str = None,
        auto_telemetry: bool = True,
        telemetry_interval: float = 5.0,
        camera_port: int = 8081,
        enable_camera_stream: bool = True
    ):
        """
        Initialize the Robot Client.
        
        Args:
            mqtt_broker: MQTT broker address
            mqtt_port: MQTT broker port  
            robot_id: Robot identifier (auto-generated if not provided)
            auto_telemetry: If True, automatically sends status/battery on interval
            telemetry_interval: Interval in seconds for auto telemetry
            camera_port: HTTP port for MJPEG camera stream (default: 8081)
            enable_camera_stream: If True, starts camera streaming server
        """
        if not MQTT_AVAILABLE:
            raise ImportError("paho-mqtt is required. Install with: pip install paho-mqtt")
        
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.auto_telemetry = auto_telemetry
        self.telemetry_interval = telemetry_interval
        self.camera_port = camera_port
        self.enable_camera_stream = enable_camera_stream
        
        # Generate robot ID
        if robot_id:
            self.robot_id = robot_id
        else:
            self.robot_id = os.getenv("ROBOT_ID")
            if not self.robot_id:
                hostname = platform.node().lower().replace(" ", "_")
                self.robot_id = f"tonypi_{hostname}"
        
        # MQTT client
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.robot_id)
        self.is_connected = False
        self.running = False
        
        # Hardware detection
        self.hardware_available = self._detect_hardware()
        
        # State
        self.battery_level = 100.0
        self._last_battery_voltage = 12.6
        self.location = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.status = "online"
        
        # Camera streaming
        self._camera_server = None
        self._camera_thread = None
        self._ip_address = self._get_local_ip()
        
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
        
        # Callbacks
        self.on_command_callback: Optional[Callable] = None
        self.on_emergency_stop_callback: Optional[Callable] = None
        
        # Emergency stop state
        self._emergency_stop_triggered = False
        self._emergency_stop_reason = None
        
        # Setup MQTT callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        # Background thread
        self._telemetry_thread = None
        self._last_status_time = 0
        self._last_battery_time = 0
        
        logger.info(f"RobotClient initialized: {self.robot_id}")
        logger.info(f"Camera stream will be available at: http://{self._ip_address}:{camera_port}/?action=stream")
    
    def _detect_hardware(self) -> bool:
        """Detect if running on TonyPi hardware."""
        if HARDWARE_SDK_AVAILABLE:
            return True
        try:
            # Check for Raspberry Pi
            if os.path.exists('/proc/device-tree/model'):
                with open('/proc/device-tree/model', 'r') as f:
                    if 'raspberry' in f.read().lower():
                        return True
            # Check for TonyPi SDK path
            if os.path.exists('/home/pi/TonyPi'):
                return True
        except:
            pass
        return False
    
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """MQTT connection callback."""
        if rc == 0:
            self.is_connected = True
            logger.info(f"Connected to MQTT broker: {self.mqtt_broker}:{self.mqtt_port}")
            
            # Subscribe to command topics
            client.subscribe(self.topics["commands"])
            client.subscribe("tonypi/commands/broadcast")
            
            # Subscribe to emergency stop topics
            client.subscribe(f"tonypi/emergency_stop/{self.robot_id}")
            client.subscribe("tonypi/emergency_stop/broadcast")
            logger.info(f"Subscribed to emergency stop topics")
            
            # Send initial status
            self.send_status()
        else:
            logger.error(f"MQTT connection failed: rc={rc}")
    
    def _on_disconnect(self, client, userdata, flags=None, rc=None, properties=None):
        """MQTT disconnection callback."""
        self.is_connected = False
        return_code = rc if rc is not None else flags
        logger.warning(f"Disconnected from MQTT: rc={return_code}")
    
    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        try:
            payload = json.loads(msg.payload.decode())
            command_type = payload.get('type', '')
            logger.info(f"Command received on {msg.topic}: {command_type}")
            
            # ==========================================
            # 🚨 EMERGENCY STOP HANDLING
            # ==========================================
            if 'emergency_stop' in msg.topic or command_type == 'emergency_stop':
                self._handle_emergency_stop(payload)
                return
            
            # Handle resume command (to clear emergency stop)
            if command_type == 'resume' or command_type == 'clear_emergency':
                self._handle_resume(payload)
                return
            
            # Pass to general command callback
            if self.on_command_callback:
                self.on_command_callback(msg.topic, payload)
                
        except Exception as e:
            logger.error(f"Message handling error: {e}")
    
    def _handle_emergency_stop(self, payload: Dict[str, Any]):
        """
        Handle emergency stop command from monitoring system.
        
        Args:
            payload: Command payload with optional 'reason' field
        """
        reason = payload.get('reason', 'Emergency stop triggered from monitoring system')
        command_id = payload.get('id', 'unknown')
        
        logger.warning(f"🚨 EMERGENCY STOP RECEIVED: {reason}")
        
        # Set emergency stop state
        self._emergency_stop_triggered = True
        self._emergency_stop_reason = reason
        self.status = "emergency_stopped"
        
        # Stop any hardware actions if SDK available
        if HARDWARE_SDK_AVAILABLE:
            try:
                from hiwonder.ActionGroupControl import stopActionGroup
                stopActionGroup()
                logger.info("Hardware actions stopped")
            except Exception as e:
                logger.error(f"Error stopping hardware actions: {e}")
        
        # Call the emergency stop callback if registered
        if self.on_emergency_stop_callback:
            try:
                self.on_emergency_stop_callback(reason)
            except Exception as e:
                logger.error(f"Error in emergency stop callback: {e}")
        
        # Send acknowledgement
        self.send_log("CRITICAL", f"EMERGENCY STOP: {reason}", "emergency")
        
        # Send response to confirm stop
        response = {
            "robot_id": self.robot_id,
            "command_id": command_id,
            "timestamp": datetime.now().isoformat(),
            "type": "emergency_stop_ack",
            "success": True,
            "message": "Emergency stop executed",
            "reason": reason
        }
        self.client.publish(self.topics["response"], json.dumps(response))
        
        # Send job cancellation event if there's an active job
        self.send_job_event(
            task_name="current_task",
            status="cancelled",
            phase="emergency_stopped",
            reason=reason
        )
        
        # Update status
        self.send_status({"emergency_stop": True, "emergency_reason": reason})
    
    def _handle_resume(self, payload: Dict[str, Any]):
        """
        Handle resume command to clear emergency stop state.
        
        Args:
            payload: Command payload
        """
        command_id = payload.get('id', 'unknown')
        
        if self._emergency_stop_triggered:
            logger.info("✅ Emergency stop cleared - resuming normal operation")
            self._emergency_stop_triggered = False
            self._emergency_stop_reason = None
            self.status = "online"
            
            self.send_log("INFO", "Emergency stop cleared - system ready", "emergency")
            
            # Send response
            response = {
                "robot_id": self.robot_id,
                "command_id": command_id,
                "timestamp": datetime.now().isoformat(),
                "type": "resume_ack",
                "success": True,
                "message": "System resumed from emergency stop"
            }
            self.client.publish(self.topics["response"], json.dumps(response))
            
            self.send_status()
        else:
            logger.info("Resume command received but no emergency stop was active")
    
    def set_emergency_stop_callback(self, callback: Callable[[str], None]):
        """
        Set callback function for emergency stop events.
        
        The callback will be called when an emergency stop command is received.
        Use this to stop your robot's current actions.
        
        Args:
            callback: Function that takes a reason string as argument
                      Example: def on_emergency_stop(reason: str): ...
        """
        self.on_emergency_stop_callback = callback
        logger.info("Emergency stop callback registered")
    
    def is_emergency_stopped(self) -> bool:
        """
        Check if emergency stop is currently active.
        
        Returns:
            True if emergency stop is active
        """
        return self._emergency_stop_triggered
    
    def get_emergency_stop_reason(self) -> Optional[str]:
        """
        Get the reason for the current emergency stop.
        
        Returns:
            Reason string if emergency stop is active, None otherwise
        """
        return self._emergency_stop_reason if self._emergency_stop_triggered else None
    
    def clear_emergency_stop(self):
        """
        Clear the emergency stop state locally.
        Call this after handling the emergency stop in your main code.
        """
        if self._emergency_stop_triggered:
            logger.info("Emergency stop cleared locally")
            self._emergency_stop_triggered = False
            self._emergency_stop_reason = None
            self.status = "online"
            self.send_status()
    
    def _telemetry_loop(self):
        """Background thread for auto telemetry."""
        last_servo_time = 0
        last_imu_time = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                # Send status periodically
                if self.auto_telemetry and self.is_connected:
                    if current_time - self._last_status_time >= self.telemetry_interval:
                        self.send_status()
                        self._last_status_time = current_time
                    
                    if current_time - self._last_battery_time >= 30:
                        self.send_battery()
                        self._last_battery_time = current_time
                    
                    # Send servo data every 3 seconds
                    if current_time - last_servo_time >= 3:
                        servo_data = self.read_servo_data()
                        self.send_servo_data(servo_data)
                        last_servo_time = current_time
                    
                    # Send IMU data every 2 seconds
                    if current_time - last_imu_time >= 2:
                        imu_data = self.read_imu_data()
                        self.send_sensor_data(imu_data)
                        last_imu_time = current_time
                
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Telemetry loop error: {e}")
    
    # ==========================================
    # HARDWARE READING METHODS
    # ==========================================
    
    def read_imu_data(self) -> Dict[str, float]:
        """
        Read IMU sensor data (accelerometer and gyroscope).
        Returns real data if hardware available, otherwise simulated.
        """
        if HARDWARE_SDK_AVAILABLE and board:
            try:
                imu = board.get_imu()
                if imu:
                    return {
                        "accelerometer_x": round(imu[0], 3),
                        "accelerometer_y": round(imu[1], 3),
                        "accelerometer_z": round(imu[2], 3),
                        "gyroscope_x": round(imu[3], 2),
                        "gyroscope_y": round(imu[4], 2),
                        "gyroscope_z": round(imu[5], 2),
                        "cpu_temperature": self._get_cpu_temperature()
                    }
            except Exception as e:
                logger.error(f"Error reading IMU: {e}")
        
        # Simulation mode - generate realistic sensor data
        return {
            "accelerometer_x": round(random.uniform(-0.5, 0.5), 3),
            "accelerometer_y": round(random.uniform(-0.5, 0.5), 3),
            "accelerometer_z": round(random.uniform(9.5, 10.0), 3),
            "gyroscope_x": round(random.uniform(-10, 10), 2),
            "gyroscope_y": round(random.uniform(-10, 10), 2),
            "gyroscope_z": round(random.uniform(-10, 10), 2),
            "cpu_temperature": self._get_cpu_temperature()
        }
    
    def read_servo_data(self) -> Dict[str, Any]:
        """
        Read servo status data (position, temperature, voltage).
        Returns real data if hardware available, otherwise simulated.
        """
        servo_data = {}
        servo_names = ["Left Hip", "Left Knee", "Right Hip", "Right Knee", "Head Pan", "Head Tilt"]
        servo_count = 6  # TonyPi has 6 main bus servos
        
        if HARDWARE_SDK_AVAILABLE and controller:
            for idx in range(1, servo_count + 1):
                try:
                    # Read servo data from hardware
                    pos = controller.get_bus_servo_pulse(idx)
                    temp = controller.get_bus_servo_temp(idx)
                    vin = controller.get_bus_servo_vin(idx)
                    
                    # Convert pulse to degrees
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
                    servo_data[f"servo_{idx}"] = self._get_simulated_servo(idx, servo_names)
        else:
            # Simulation mode
            for idx in range(1, servo_count + 1):
                servo_data[f"servo_{idx}"] = self._get_simulated_servo(idx, servo_names)
        
        return servo_data
    
    def _get_simulated_servo(self, idx: int, servo_names: list) -> Dict[str, Any]:
        """Generate simulated servo data."""
        temp = round(random.uniform(40, 55), 1)
        return {
            "id": idx,
            "name": servo_names[idx - 1] if idx <= len(servo_names) else f"Servo {idx}",
            "position": round(random.uniform(-45, 45), 1),
            "temperature": temp,
            "voltage": round(random.uniform(4.8, 5.2), 2),
            "torque_enabled": True,
            "alert_level": "warning" if temp > 50 else "normal"
        }
    
    def read_battery_voltage(self) -> tuple:
        """
        Read battery voltage and calculate percentage.
        Returns (percentage, voltage).
        
        TonyPi uses a 3S LiPo battery:
        - Full charge: 12.6V (4.2V per cell)
        - Nominal: 11.1V (3.7V per cell)
        - Empty (safe cutoff): 9.0V (3.0V per cell)
        """
        if HARDWARE_SDK_AVAILABLE and board:
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
                        # Invalid reading
                        logger.warning(f"Battery voltage too high ({voltage_v}V), using fallback")
                        return (self.battery_level, self._last_battery_voltage)
                    
                    percentage = self._voltage_to_percentage(voltage_v)
                    self.battery_level = max(0, min(100, percentage))
                    self._last_battery_voltage = voltage_v
                    
                    logger.debug(f"Battery: {voltage_v:.2f}V = {percentage:.1f}%")
                    return (self.battery_level, voltage_v)
                else:
                    logger.warning(f"Invalid battery reading: {voltage_mv}")
            except Exception as e:
                logger.error(f"Error reading battery: {e}")
        else:
            logger.debug(f"Battery hardware not available (SDK={HARDWARE_SDK_AVAILABLE}, board={board is not None})")
        
        # Simulation mode or fallback - slowly decrease battery
        if not HARDWARE_SDK_AVAILABLE:
            # Simulate gradual battery drain for testing
            self.battery_level = max(0, self.battery_level - 0.01)
            # Estimate voltage from percentage for simulation
            self._last_battery_voltage = 9.0 + (self.battery_level / 100.0) * 3.6
        
        return (self.battery_level, self._last_battery_voltage)
    
    def _voltage_to_percentage(self, voltage: float) -> float:
        """Convert battery voltage to percentage (3S LiPo curve)."""
        BATTERY_MIN_V = 9.0
        BATTERY_MAX_V = 12.6
        
        voltage = max(BATTERY_MIN_V, min(BATTERY_MAX_V, voltage))
        
        breakpoints = [
            (9.0, 0), (9.6, 5), (10.2, 15), (10.5, 25),
            (10.8, 40), (11.1, 50), (11.4, 65), (11.7, 80),
            (12.0, 90), (12.3, 95), (12.6, 100),
        ]
        
        for i in range(len(breakpoints) - 1):
            v1, p1 = breakpoints[i]
            v2, p2 = breakpoints[i + 1]
            if v1 <= voltage <= v2:
                ratio = (voltage - v1) / (v2 - v1)
                return p1 + ratio * (p2 - p1)
        
        return 0 if voltage < BATTERY_MIN_V else 100
    
    # ==========================================
    # PUBLIC API
    # ==========================================
    
    def start(self) -> bool:
        """
        Start the robot client (connects to MQTT + starts camera server).
        
        Returns:
            True if started successfully
        """
        try:
            self.running = True
            
            # Start camera streaming server
            if self.enable_camera_stream:
                self._start_camera_server()
            
            # Connect to MQTT
            self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.client.loop_start()
            
            # Wait for connection (with timeout)
            timeout = 5.0
            while not self.is_connected and timeout > 0:
                time.sleep(0.1)
                timeout -= 0.1
            
            if self.is_connected:
                # Start background telemetry thread
                self._telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
                self._telemetry_thread.start()
                logger.info("Robot client started (MQTT + Camera)")
                return True
            else:
                logger.warning("MQTT connection timeout - camera still running")
                # Still start telemetry for camera even without MQTT
                self._telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
                self._telemetry_thread.start()
                return False
                
        except Exception as e:
            logger.error(f"Failed to start client: {e}")
            return False
    
    def stop(self):
        """Stop the robot client, camera server, and disconnect MQTT."""
        self.running = False
        self.status = "offline"
        
        if self.is_connected:
            self.send_status()
            time.sleep(0.5)
        
        # Stop camera server
        self._stop_camera_server()
        
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("Robot client stopped")
    
    def _start_camera_server(self):
        """Start the MJPEG camera streaming server."""
        try:
            self._camera_server = ThreadedHTTPServer(('', self.camera_port), MJPEGHandler)
            self._camera_thread = threading.Thread(target=self._camera_server.serve_forever, daemon=True)
            self._camera_thread.start()
            logger.info(f"📹 Camera stream started: http://{self._ip_address}:{self.camera_port}/?action=stream")
        except OSError as e:
            if e.errno == 98 or e.errno == 10048:  # Address already in use (Linux/Windows)
                logger.warning(f"Camera port {self.camera_port} already in use - stream not available")
            else:
                logger.error(f"Failed to start camera server: {e}")
        except Exception as e:
            logger.error(f"Failed to start camera server: {e}")
    
    def _stop_camera_server(self):
        """Stop the camera streaming server."""
        if self._camera_server:
            try:
                self._camera_server.shutdown()
                logger.info("Camera server stopped")
            except Exception as e:
                logger.error(f"Error stopping camera server: {e}")
    
    def update_frame(self, frame):
        """
        Update the current camera frame for streaming.
        Call this from main.py's camera loop.
        
        Args:
            frame: OpenCV frame (numpy array) from camera
        """
        global _current_frame, _frame_lock
        
        if frame is not None:
            with _frame_lock:
                _current_frame = frame.copy() if hasattr(frame, 'copy') else frame
    
    @property
    def camera_url(self) -> str:
        """Get the camera stream URL."""
        return f"http://{self._ip_address}:{self.camera_port}/?action=stream"
    
    @property  
    def snapshot_url(self) -> str:
        """Get the camera snapshot URL."""
        return f"http://{self._ip_address}:{self.camera_port}/?action=snapshot"
    
    def set_command_callback(self, callback: Callable):
        """
        Set callback for incoming commands.
        
        Args:
            callback: Function(topic, payload) to handle commands
        """
        self.on_command_callback = callback
    
    # ==========================================
    # TELEMETRY METHODS
    # ==========================================
    
    def send_vision_data(
        self,
        label: str = None,
        confidence: float = None,
        bbox: tuple = None,
        center_x: int = None,
        frame_width: int = 640,
        frame_height: int = 480,
        state: str = "UNKNOWN",
        is_locked: bool = False,
        nav_cmd: str = None,
        error: float = None
    ):
        """
        Send vision detection data to monitoring system.
        
        Args:
            label: Detected object class name
            confidence: Detection confidence (0-1)
            bbox: Bounding box (x1, y1, x2, y2)
            center_x: Center X coordinate of detection
            frame_width: Camera frame width
            frame_height: Camera frame height
            state: Current robot state
            is_locked: Whether target is locked
            nav_cmd: Navigation command (TURN_LEFT, TURN_RIGHT, LOCKED)
            error: Position error from center
        """
        if not self.is_connected:
            return
        
        try:
            data = {
                "robot_id": self.robot_id,
                "timestamp": datetime.now().isoformat(),
                "detection": label is not None,
                "label": label,
                "confidence": confidence,
                "bbox": list(bbox) if bbox else None,
                "center_x": center_x,
                "frame_width": frame_width,
                "frame_height": frame_height,
                "state": state,
                "is_locked": is_locked,
                "navigation_command": nav_cmd,
                "error": error
            }
            
            self.client.publish(self.topics["vision"], json.dumps(data))
            
        except Exception as e:
            logger.error(f"Error sending vision data: {e}")
    
    def send_sensor_data(self, sensors: Dict[str, float]):
        """
        Send sensor data to monitoring system.
        
        Args:
            sensors: Dictionary of sensor_name: value pairs
                     e.g. {"ultrasonic_distance": 25.5, "light_level": 80}
        """
        if not self.is_connected:
            return
        
        try:
            for sensor_name, value in sensors.items():
                if isinstance(value, str):
                    continue  # Skip string values
                    
                data = {
                    "robot_id": self.robot_id,
                    "sensor_type": sensor_name,
                    "value": value,
                    "timestamp": datetime.now().isoformat(),
                    "unit": self._get_sensor_unit(sensor_name)
                }
                self.client.publish(self.topics["sensors"], json.dumps(data))
                
        except Exception as e:
            logger.error(f"Error sending sensor data: {e}")
    
    def send_status(self, custom_data: Dict = None):
        """
        Send robot status update with system metrics.
        
        Args:
            custom_data: Optional additional data to include
        """
        if not self.is_connected:
            return
        
        try:
            system_info = self._get_system_info()
            
            data = {
                "robot_id": self.robot_id,
                "status": self.status,
                "timestamp": datetime.now().isoformat(),
                "system_info": system_info,
                "hardware_available": self.hardware_available,
                "ip_address": self._ip_address,
                "camera_url": self.camera_url,
                "snapshot_url": self.snapshot_url
            }
            
            if custom_data:
                data.update(custom_data)
            
            self.client.publish(self.topics["status"], json.dumps(data))
            
        except Exception as e:
            logger.error(f"Error sending status: {e}")
    
    def send_battery(self, percentage: float = None, voltage: float = None):
        """
        Send battery status.
        
        Args:
            percentage: Battery percentage (0-100), reads from hardware if None
            voltage: Battery voltage in volts, reads from hardware if None
        """
        if not self.is_connected:
            return
        
        try:
            # Read from hardware if not provided
            if percentage is None or voltage is None:
                hw_percent, hw_voltage = self.read_battery_voltage()
                if percentage is None:
                    percentage = hw_percent
                if voltage is None:
                    voltage = hw_voltage
            
            data = {
                "robot_id": self.robot_id,
                "percentage": round(percentage, 1),
                "voltage": round(voltage, 2),
                "charging": False,
                "timestamp": datetime.now().isoformat()
            }
            
            self.client.publish(self.topics["battery"], json.dumps(data))
            logger.debug(f"Battery sent: {percentage:.1f}% ({voltage:.2f}V)")
            
        except Exception as e:
            logger.error(f"Error sending battery: {e}")
    
    def send_servo_data(self, servo_data: Dict[str, Any]):
        """
        Send servo status data.
        
        Args:
            servo_data: Dictionary of servo data
        """
        if not self.is_connected:
            return
        
        try:
            data = {
                "robot_id": self.robot_id,
                "servos": servo_data,
                "servo_count": len(servo_data),
                "timestamp": datetime.now().isoformat()
            }
            
            self.client.publish(self.topics["servos"], json.dumps(data))
            
        except Exception as e:
            logger.error(f"Error sending servo data: {e}")
    
    def send_location(self, x: float, y: float, z: float = 0.0):
        """
        Send robot location/position.
        
        Args:
            x, y, z: Position coordinates
        """
        if not self.is_connected:
            return
        
        try:
            self.location = {"x": x, "y": y, "z": z}
            
            data = {
                "robot_id": self.robot_id,
                "x": x,
                "y": y,
                "z": z,
                "timestamp": datetime.now().isoformat()
            }
            
            self.client.publish(self.topics["location"], json.dumps(data))
            
        except Exception as e:
            logger.error(f"Error sending location: {e}")
    
    def send_log(self, level: str, message: str, source: str = "main"):
        """
        Send log message to monitoring system.
        
        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR)
            message: Log message
            source: Source module name
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
            logger.error(f"Error sending log: {e}")
    
    def send_job_event(
        self,
        task_name: str,
        status: str,
        phase: str = None,
        elapsed_time: float = None,
        estimated_duration: float = None,
        action_duration: float = None,
        success: bool = None,
        reason: str = None,
        items_done: int = None,
        items_total: int = None
    ):
        """
        Send job timing event to monitoring system.
        
        Args:
            task_name: Name of the task (e.g., "Peeling", "Transport")
            status: Job status ("started", "in_progress", "completed", "cancelled", "failed")
            phase: Current phase ("scanning", "searching", "executing", "done")
            elapsed_time: Time elapsed since job started (seconds)
            estimated_duration: Estimated total duration for this task type (seconds)
            action_duration: Duration of the physical action execution (seconds)
            success: Whether the job completed successfully
            reason: Reason for cancellation/failure (if applicable)
            items_done: Number of items processed so far
            items_total: Total number of items to process
        """
        if not self.is_connected:
            return
        
        try:
            data = {
                "robot_id": self.robot_id,
                "timestamp": datetime.now().isoformat(),
                "task_name": task_name,
                "status": status,
                "phase": phase
            }
            
            if elapsed_time is not None:
                data["elapsed_time"] = round(elapsed_time, 2)
            
            if estimated_duration is not None:
                data["estimated_duration"] = estimated_duration
                # Calculate progress percentage
                if elapsed_time is not None and estimated_duration > 0:
                    progress = min(100, (elapsed_time / estimated_duration) * 100)
                    data["progress_percent"] = round(progress, 1)
            
            if action_duration is not None:
                data["action_duration"] = round(action_duration, 2)
            
            if success is not None:
                data["success"] = success
            
            if reason is not None:
                data["reason"] = reason
            
            # Item tracking for job progress
            if items_done is not None:
                data["items_done"] = items_done
            
            if items_total is not None:
                data["items_total"] = items_total
            
            # Calculate percent from items if not already set via elapsed_time
            if items_done is not None and items_total is not None and items_total > 0:
                if "progress_percent" not in data:
                    data["progress_percent"] = round((items_done / items_total) * 100, 1)
                # Also include as 'percent' for legacy compatibility
                data["percent"] = round((items_done / items_total) * 100, 1)
            
            # Publish to job topic
            job_topic = f"tonypi/job/{self.robot_id}"
            self.client.publish(job_topic, json.dumps(data))
            
            logger.info(f"Job event: {task_name} - {status} ({phase})" + 
                       (f" [{items_done}/{items_total}]" if items_done is not None else ""))
            
        except Exception as e:
            logger.error(f"Error sending job event: {e}")
    
    def send_command_response(self, command_id: str, success: bool, message: str, data: Dict = None):
        """
        Send response to a command.
        
        Args:
            command_id: ID of the command being responded to
            success: Whether command succeeded
            message: Response message
            data: Optional additional data
        """
        if not self.is_connected:
            return
        
        try:
            response = {
                "robot_id": self.robot_id,
                "command_id": command_id,
                "timestamp": datetime.now().isoformat(),
                "success": success,
                "message": message
            }
            
            if data:
                response["data"] = data
            
            self.client.publish(self.topics["response"], json.dumps(response))
            
        except Exception as e:
            logger.error(f"Error sending command response: {e}")
    
    def send_qr_scan(self, qr_data: str, station_name: str = None, action: str = None):
        """
        Send QR code scan event to monitoring system.
        
        Args:
            qr_data: QR code content/data
            station_name: Name of the station (optional)
            action: Action performed (e.g., 'scanned', 'navigation_complete')
        """
        if not self.is_connected:
            return
        
        try:
            payload = {
                "robot_id": self.robot_id,
                "timestamp": datetime.now().isoformat(),
                "qr_code": qr_data,
                "station": station_name or "unknown",
                "action": action or "scanned"
            }
            
            topic = f"tonypi/scan/{self.robot_id}"
            self.client.publish(topic, json.dumps(payload))
            logger.info(f"QR scan event sent: {qr_data} - {station_name}")
            
        except Exception as e:
            logger.error(f"Error sending QR scan event: {e}")
    
    # ==========================================
    # HELPER METHODS
    # ==========================================
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Get system metrics."""
        try:
            cpu_temp = self._get_cpu_temperature()
            return {
                "platform": platform.platform(),
                "cpu_percent": psutil.cpu_percent(interval=None),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage('/').percent if os.path.exists('/') else 0,
                "temperature": cpu_temp,
                "cpu_temperature": cpu_temp,
                "uptime": time.time() - psutil.boot_time(),
                "hardware_mode": self.hardware_available
            }
        except Exception as e:
            logger.error(f"Error getting system info: {e}")
            return {"error": str(e)}
    
    def _get_cpu_temperature(self) -> float:
        """Get CPU temperature."""
        try:
            # Raspberry Pi
            if os.path.exists('/sys/class/thermal/thermal_zone0/temp'):
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    return float(f.read()) / 1000.0
        except:
            pass
        # Fallback: simulated
        return 45.0 + (time.time() % 10)
    
    def _get_local_ip(self) -> str:
        """Get local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "192.168.149.1"
    
    def _get_sensor_unit(self, sensor_name: str) -> str:
        """Get unit for sensor type."""
        units = {
            "accelerometer_x": "m/s²",
            "accelerometer_y": "m/s²",
            "accelerometer_z": "m/s²",
            "gyroscope_x": "°/s",
            "gyroscope_y": "°/s",
            "gyroscope_z": "°/s",
            "ultrasonic_distance": "cm",
            "cpu_temperature": "°C",
            "light_level": "%",
            "light_sensor_dark": "bool"
        }
        return units.get(sensor_name, "")
    
    @property
    def connected(self) -> bool:
        """Check if connected to MQTT broker."""
        return self.is_connected


# Convenience function for quick setup
def create_client(broker: str = None, robot_id: str = None) -> RobotClient:
    """
    Create and start a robot client.
    
    Args:
        broker: MQTT broker address (default: localhost or MQTT_BROKER env)
        robot_id: Robot ID (default: auto-generated)
    
    Returns:
        Connected RobotClient instance
    """
    if broker is None:
        broker = os.getenv("MQTT_BROKER", "localhost")
    
    port = int(os.getenv("MQTT_PORT", 1883))
    
    client = RobotClient(
        mqtt_broker=broker,
        mqtt_port=port,
        robot_id=robot_id
    )
    client.start()
    return client
