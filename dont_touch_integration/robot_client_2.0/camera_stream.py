#!/usr/bin/env python3
"""
MJPEG Camera Streaming Server for TonyPi Robot
Captures frames from USB camera and serves them as MJPEG stream over HTTP.
Integrated with light sensor for low-light warning popup.

Usage:
    python camera_stream.py [--port 8080]
    
Access the stream at:
    http://<tonypi-ip>:8080/?action=stream
    http://<tonypi-ip>:8080/?action=snapshot
"""

import time
import threading
import argparse
import random
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

# Try to import OpenCV
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("Warning: OpenCV not available. Camera will run in simulation mode.")

# Try to import GPIO for light sensor
LIGHT_SENSOR_AVAILABLE = False
try:
    import RPi.GPIO as GPIO
    LIGHT_SENSOR_AVAILABLE = True
    print("RPi.GPIO available for light sensor")
except ImportError:
    print("Warning: RPi.GPIO not available - light sensor will be simulated")

# ==========================================
# LIGHT SENSOR CLASS (with debouncing)
# ==========================================
class LightSensor:
    """
    Light sensor class for reading ambient light via GPIO.
    Includes debouncing to prevent rapid state flickering.
    Falls back to simulation mode if GPIO is not available.
    """
    
    def __init__(self, pin=24, invert_logic=False, disabled=False, debounce_time=1.0):
        """
        Initialize light sensor.
        
        Args:
            pin: GPIO pin number (BCM mode)
            invert_logic: If True, inverts the dark detection logic.
            disabled: If True, sensor always returns "not dark" (light OK)
            debounce_time: Seconds the sensor must be stable before state changes (default 1.0s)
        """
        self.pin = pin
        self.initialized = False
        self.invert_logic = invert_logic
        self.disabled = disabled
        self.debounce_time = debounce_time
        
        # Debouncing state
        self._stable_state = False  # The debounced/stable "is dark" state
        self._last_raw_dark = False  # Last raw reading
        self._state_stable_since = time.time()  # When current raw state started
        
        if disabled:
            print(f"Light sensor DISABLED (--disable-light-sensor flag)")
            return
        
        if LIGHT_SENSOR_AVAILABLE:
            try:
                GPIO.setwarnings(False)
                # Try to set mode, but handle if already set
                try:
                    GPIO.setmode(GPIO.BCM)
                except RuntimeError:
                    # GPIO mode already set - this is OK, continue
                    pass
                except Exception as e:
                    print(f"Warning: GPIO mode issue (may already be initialized): {e}")
                
                # Try to setup pin, but handle if already configured
                try:
                    GPIO.setup(self.pin, GPIO.IN)
                except RuntimeError as e:
                    if "GPIO channel" in str(e) and "already in use" in str(e):
                        print(f"Warning: GPIO pin {pin} already in use. Trying to use existing setup...")
                        # Try to read it anyway - might work if already configured
                        try:
                            _ = GPIO.input(self.pin)
                            self.initialized = True
                            print(f"Light sensor using existing GPIO pin {pin} configuration")
                        except:
                            print(f"Failed to use existing GPIO pin {pin}: {e}")
                            return
                    else:
                        raise
                except Exception as e:
                    print(f"Failed to setup GPIO pin {pin}: {e}")
                    return
                
                self.initialized = True
                print(f"Light sensor initialized on GPIO pin {pin}")
                print(f"  -> Debounce time: {debounce_time}s (sensor must be stable this long)")
                if invert_logic:
                    print(f"  -> Logic INVERTED (--invert-light-sensor flag)")
            except Exception as e:
                print(f"Failed to initialize light sensor: {e}")
                print(f"  -> Tip: If GPIO is busy, try: sudo systemctl stop [other-service]")
                print(f"  -> Or use --disable-light-sensor to disable light sensor")
    
    def _read_raw_dark(self) -> bool:
        """Read raw sensor value and interpret as dark/not dark."""
        if self.initialized and LIGHT_SENSOR_AVAILABLE:
            try:
                raw_value = GPIO.input(self.pin)
                # Default (same as FYP_Robot): HIGH (1) = dark/blocked, LOW (0) = bright
                # With invert_logic: LOW (0) = dark, HIGH (1) = bright
                if self.invert_logic:
                    return raw_value == 0
                else:
                    return raw_value == 1  # HIGH = dark (sensor blocked)
            except Exception as e:
                print(f"Error reading light sensor: {e}")
                return False
        return False
    
    def is_dark(self) -> bool:
        """
        Returns True if sensor detects darkness (debounced).
        
        The sensor must read the same state for `debounce_time` seconds
        before the state actually changes. This prevents flickering when
        the sensor is near its threshold.
        """
        # If disabled, always return False (not dark)
        if self.disabled:
            return False
        
        # Simulation mode
        if not self.initialized or not LIGHT_SENSOR_AVAILABLE:
            # Simulation: 5% chance of being dark (for testing)
            return random.random() < 0.05
        
        # Read current raw state
        current_raw_dark = self._read_raw_dark()
        current_time = time.time()
        
        # If raw state changed, reset the stability timer
        if current_raw_dark != self._last_raw_dark:
            self._last_raw_dark = current_raw_dark
            self._state_stable_since = current_time
        
        # Check if raw state has been stable long enough to change the debounced state
        time_stable = current_time - self._state_stable_since
        if time_stable >= self.debounce_time:
            # State has been stable long enough - update the debounced state
            if self._stable_state != current_raw_dark:
                old_state = self._stable_state
                self._stable_state = current_raw_dark
                # Get raw GPIO value for logging
                raw_gpio_value = self.get_raw_value()
                # Print when state actually changes (with more detail)
                if current_raw_dark:
                    print(f"[Light Sensor] ⚠️ LOW LIGHT DETECTED! (stable for {self.debounce_time:.1f}s)")
                    print(f"  -> Raw GPIO pin {self.pin}: {raw_gpio_value} (HIGH = blocked/dark)")
                    print(f"  -> Previous state: {'DARK' if old_state else 'BRIGHT'} → New state: DARK")
                else:
                    print(f"[Light Sensor] ✅ Light levels restored to normal (stable for {self.debounce_time:.1f}s)")
                    print(f"  -> Raw GPIO pin {self.pin}: {raw_gpio_value} (LOW = bright)")
                    print(f"  -> Previous state: {'DARK' if old_state else 'BRIGHT'} → New state: BRIGHT")
        
        return self._stable_state
    
    def get_raw_value(self) -> int:
        """
        Get the raw GPIO value for debugging.
        Returns 0 or 1, or -1 if not available.
        """
        if self.disabled:
            return -1
        if self.initialized and LIGHT_SENSOR_AVAILABLE:
            try:
                return GPIO.input(self.pin)
            except:
                return -1
        return -1
    
    def debug_print(self):
        """Print debug info about sensor state."""
        if self.disabled:
            print(f"[Light Sensor] DISABLED - always returns 'not dark'")
            return -1, False
        raw = self.get_raw_value()
        raw_dark = self._read_raw_dark()
        stable_dark = self._stable_state
        print(f"[Light Sensor] GPIO Pin {self.pin}:")
        print(f"  raw_value={raw} ({'HIGH' if raw == 1 else 'LOW'})")
        print(f"  raw_is_dark={raw_dark}, debounced_is_dark={stable_dark}")
        print(f"  Logic: {'HIGH=dark (default)' if not self.invert_logic else 'LOW=dark (inverted)'}")
        print(f"  debounce_time={self.debounce_time}s")
        print(f"")
        print(f"  >> Current light status: {'DARK' if raw_dark else 'BRIGHT'}")
        print(f"  >> Cover the sensor now - raw_value should change to 1 (HIGH)")
        return raw, stable_dark
    
    def cleanup(self):
        """Clean up GPIO resources."""
        if self.initialized and LIGHT_SENSOR_AVAILABLE:
            try:
                GPIO.cleanup(self.pin)
            except Exception as e:
                print(f"Error cleaning up light sensor: {e}")


# Global frame storage
img_show = None
quality = (int(cv2.IMWRITE_JPEG_QUALITY) if CV2_AVAILABLE else 0, 70)

# Light sensor instance (global for access in camera task)
light_sensor = None
is_dark_warning = False  # Global flag to track dark state for overlay


class Camera:
    """
    Camera capture class using OpenCV.
    Runs frame capture in a background thread.
    """
    
    def __init__(self, resolution=(640, 480), device=-1):
        """
        Initialize camera.
        
        Args:
            resolution: Tuple of (width, height)
            device: Camera device index (-1 for auto-detect)
        """
        self.cap = None
        self.width = resolution[0]
        self.height = resolution[1]
        self.device = device
        self.frame = None
        self.opened = False
        self.flip = False
        self.flip_param = 0
        self.simulation_mode = not CV2_AVAILABLE
        
        # Try to load camera settings
        try:
            import yaml
            with open('/boot/camera_setting.yaml', 'r') as f:
                camera_setting = yaml.safe_load(f)
                self.flip = camera_setting.get('flip', False)
                self.flip_param = camera_setting.get('flip_param', 0)
        except:
            pass
        
        # Start capture thread
        self.running = True
        self.th = threading.Thread(target=self.camera_task, daemon=True)
        self.th.start()
        
        # Give thread a moment to start
        time.sleep(0.1)

    def camera_open(self):
        """Open the camera."""
        if self.simulation_mode:
            self.opened = True
            print("Camera running in simulation mode (test pattern)")
            return True
            
        try:
            # Try to open camera - try device index first, then try common device paths
            if self.device == -1:
                # Auto-detect: try common device indices
                for dev_idx in [0, 1, 2]:
                    print(f"Trying to open camera device {dev_idx}...")
                    self.cap = cv2.VideoCapture(dev_idx)
                    if self.cap.isOpened():
                        ret, test_frame = self.cap.read()
                        if ret and test_frame is not None:
                            self.device = dev_idx
                            print(f"✅ Camera found on device {dev_idx}")
                            break
                        else:
                            self.cap.release()
                            self.cap = None
                else:
                    print("❌ No camera found on devices 0, 1, or 2")
                    return False
            else:
                self.cap = cv2.VideoCapture(self.device)
            
            if self.cap is not None and self.cap.isOpened():
                # Configure camera properties
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('Y', 'U', 'Y', 'V'))
                self.cap.set(cv2.CAP_PROP_FPS, 30)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                
                # Test read to make sure it works
                ret, test_frame = self.cap.read()
                if ret and test_frame is not None:
                    self.opened = True
                    print(f"✅ Camera opened successfully: {self.width}x{self.height}")
                    print(f"   Device: {self.device}, Test frame: {test_frame.shape}")
                    return True
                else:
                    print("❌ Camera opened but cannot read frames")
                    self.cap.release()
                    self.cap = None
                    return False
            else:
                print(f"❌ Failed to open camera device {self.device}")
                return False
        except Exception as e:
            print(f'❌ Failed to open camera: {e}')
            import traceback
            traceback.print_exc()
            return False

    def camera_close(self):
        """Close the camera."""
        try:
            self.opened = False
            time.sleep(0.2)
            if self.cap is not None:
                self.cap.release()
                time.sleep(0.05)
            self.cap = None
        except Exception as e:
            print(f'Failed to close camera: {e}')
    
    def read(self):
        """
        Read the current frame.
        
        Returns:
            tuple: (success, frame) where frame is numpy array or None
        """
        if self.frame is None:
            return False, self.frame
        else:
            return True, self.frame
    
    def camera_task(self):
        """Background task for capturing frames with light sensor integration."""
        global light_sensor, is_dark_warning
        
        was_dark_last_frame = False
        
        while self.running:
            try:
                if self.simulation_mode:
                    # Generate test pattern
                    if self.opened:
                        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                        # Add text
                        cv2.putText(frame, "TonyPi Camera", (50, self.height // 2 - 20),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                        cv2.putText(frame, time.strftime("%H:%M:%S"), (50, self.height // 2 + 30),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        # Add moving element
                        x = int((time.time() % 5) / 5 * self.width)
                        cv2.circle(frame, (x, 50), 20, (0, 0, 255), -1)
                        
                        # Check light sensor and add overlay if dark
                        frame = self._add_light_sensor_overlay(frame)
                        self.frame = frame
                    time.sleep(0.033)  # ~30fps
                    continue
                    
                if self.opened and self.cap is not None and self.cap.isOpened():
                    ret, frame_tmp = self.cap.read()
                    if ret and frame_tmp is not None:
                        frame = cv2.resize(frame_tmp, (self.width, self.height), 
                                          interpolation=cv2.INTER_NEAREST)
                        if self.flip:
                            frame = cv2.flip(frame, self.flip_param)
                        
                        # Check light sensor and add overlay if dark
                        frame = self._add_light_sensor_overlay(frame)
                        self.frame = frame
                    else:
                        # Frame read failed - try to reopen camera
                        if self.frame is None:
                            # Only log once when frame becomes None
                            pass
                        self.frame = None
                        # Try to reopen
                        try:
                            if self.cap is not None:
                                self.cap.release()
                            cap = cv2.VideoCapture(self.device)
                            ret, _ = cap.read()
                            if ret:
                                self.cap = cap
                                print(f"[Camera Thread] Reopened camera device {self.device}")
                        except Exception as e:
                            print(f"[Camera Thread] Error reopening camera: {e}")
                elif self.opened:
                    # Camera marked as opened but cap is None - try to open
                    try:
                        cap = cv2.VideoCapture(self.device)
                        ret, _ = cap.read()
                        if ret:
                            self.cap = cap
                            print(f"[Camera Thread] Opened camera device {self.device}")
                    except Exception as e:
                        print(f"[Camera Thread] Error opening camera: {e}")
                else:
                    # Camera not opened yet - wait
                    time.sleep(0.1)
            except Exception as e:
                print(f'Camera capture error: {e}')
                time.sleep(0.01)
    
    def _add_light_sensor_overlay(self, frame):
        """
        Check light sensor and add visual warning overlay if dark.
        Same visual style as FYP_Robot main.py
        """
        global light_sensor, is_dark_warning
        
        if light_sensor is None:
            return frame
        
        try:
            is_dark_now = light_sensor.is_dark()
            is_dark_warning = is_dark_now  # Update global state
            
            if is_dark_now:
                # ==========================================
                # LOW LIGHT WARNING POPUP (same as FYP_Robot)
                # ==========================================
                # Draw thick red border around the entire frame
                cv2.rectangle(frame, (0, 0), (self.width - 1, self.height - 1), (0, 0, 255), 8)
                
                # Create semi-transparent overlay at top
                overlay = frame.copy()
                cv2.rectangle(overlay, (0, 0), (self.width, 80), (0, 0, 100), -1)
                cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
                
                # Warning text - "LOW LIGHT LEVEL DETECTED"
                warning_text = "LOW LIGHT LEVEL DETECTED"
                text_size = cv2.getTextSize(warning_text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)[0]
                text_x = (self.width - text_size[0]) // 2
                cv2.putText(frame, warning_text, (text_x, 35), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                
                # Sub-warning text
                sub_text = "Vision system may not work properly"
                sub_size = cv2.getTextSize(sub_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0]
                sub_x = (self.width - sub_size[0]) // 2
                cv2.putText(frame, sub_text, (sub_x, 60), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                
                # Add timestamp
                cv2.putText(frame, time.strftime("%H:%M:%S"), (10, self.height - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            
            # Note: State change messages are now handled by LightSensor class with debouncing
        
        except Exception as e:
            print(f"Error checking light sensor: {e}")
        
        return frame


class MJPGHandler(BaseHTTPRequestHandler):
    """HTTP request handler for MJPEG streaming."""
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def do_GET(self):
        """Handle GET requests."""
        global img_show
        
        # Handle root/test request
        if self.path == '/' or self.path == '/test':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            status = "OK" if img_show is not None else "NO FRAME"
            frame_info = f"{img_show.shape}" if img_show is not None else "None"
            html = f"""
            <html>
            <head><title>Camera Stream Status</title></head>
            <body>
                <h1>Camera Stream Server</h1>
                <p>Status: {status}</p>
                <p>Frame available: {img_show is not None}</p>
                <p>Frame shape: {frame_info}</p>
                <p><a href="/?action=stream">MJPEG Stream</a></p>
                <p><a href="/?action=snapshot">Snapshot</a></p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            return
        
        # Handle snapshot request
        if 'action=snapshot' in self.path:
            if img_show is not None:
                try:
                    ret, jpg = cv2.imencode('.jpg', img_show, 
                                           [int(cv2.IMWRITE_JPEG_QUALITY), 100])
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
                    print(f'[HTTP] Snapshot error: {e}')
                    import traceback
                    traceback.print_exc()
                    self.send_error(500, str(e))
            else:
                print('[HTTP] Snapshot requested but no frame available')
                self.send_error(503, 'No frame available')
        else:
            # MJPEG stream - handle both /?action=stream and /stream
            print(f'[HTTP] Stream request from {self.client_address[0]}, path: {self.path}')
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=--boundarydonotcross')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            frame_count = 0
            last_log_time = time.time()
            no_frame_count = 0
            
            while True:
                try:
                    if img_show is not None:
                        try:
                            ret, jpg = cv2.imencode('.jpg', img_show, 
                                                   [int(cv2.IMWRITE_JPEG_QUALITY), 70,
                                                    cv2.IMWRITE_JPEG_OPTIMIZE, 1])
                            if ret:
                                jpg_bytes = jpg.tobytes()
                                
                                # MJPEG stream format
                                self.wfile.write(b'--boundarydonotcross\r\n')
                                self.send_header('Content-type', 'image/jpeg')
                                self.send_header('Content-length', str(len(jpg_bytes)))
                                self.end_headers()  # This sends the final CRLF
                                self.wfile.write(jpg_bytes)
                                self.wfile.write(b'\r\n')  # CRLF after image data (required for MJPEG)
                                self.wfile.flush()  # Ensure data is sent immediately
                                
                                frame_count += 1
                                no_frame_count = 0
                                
                                # Log every 5 seconds
                                if time.time() - last_log_time >= 5.0:
                                    print(f'[HTTP] Stream: sent {frame_count} frames to {self.client_address[0]}')
                                    last_log_time = time.time()
                            else:
                                print(f'[HTTP] Failed to encode frame')
                        except Exception as e:
                            print(f'[HTTP] Error encoding/sending frame: {e}')
                            import traceback
                            traceback.print_exc()
                    else:
                        no_frame_count += 1
                        # Log if no frames for a while
                        if no_frame_count == 1:
                            print(f'[HTTP] Stream: waiting for frames (img_show is None)')
                        elif no_frame_count % 100 == 0:  # Log every ~3 seconds
                            print(f'[HTTP] Stream: still waiting for frames... ({no_frame_count} checks)')
                    
                    # CRITICAL: Add frame rate limiting for smooth streaming (~30fps)
                    time.sleep(0.033)
                except (ConnectionResetError, BrokenPipeError, OSError) as e:
                    print(f'[HTTP] Client disconnected: {e}')
                    break
                except Exception as e:
                    print(f"[HTTP] Stream error: {e}")
                    import traceback
                    traceback.print_exc()
                    break


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in separate threads."""
    daemon_threads = True
    allow_reuse_address = True  # Allow reuse of address after server closes


def start_camera_server(port=8080, camera_device=-1, resolution=(640, 480), 
                        light_sensor_pin=24, invert_light_sensor=False, 
                        disable_light_sensor=False, debounce_time=1.0):
    """
    Start the MJPEG camera streaming server with light sensor integration.
    
    Args:
        port: HTTP server port (default: 8080)
        camera_device: Camera device index (-1 for auto)
        resolution: Camera resolution tuple (width, height)
        light_sensor_pin: GPIO pin for light sensor (default: 24)
        invert_light_sensor: If True, inverts the light sensor logic
        disable_light_sensor: If True, disables light sensor entirely
        debounce_time: Seconds sensor must be stable before state changes
    """
    global img_show, light_sensor
    
    print("=" * 50)
    print("   TONYPI CAMERA STREAM SERVER")
    print("=" * 50)
    print(f"   Port: {port}")
    print(f"   Resolution: {resolution[0]}x{resolution[1]}")
    print(f"   OpenCV available: {CV2_AVAILABLE}")
    if disable_light_sensor:
        print(f"   Light sensor: DISABLED")
    else:
        print(f"   Light sensor GPIO: {light_sensor_pin}")
        print(f"   Light sensor inverted: {invert_light_sensor}")
        print(f"   Light sensor debounce: {debounce_time}s")
    print("=" * 50)
    
    # Initialize light sensor
    print("\nInitializing light sensor...")
    light_sensor = LightSensor(
        pin=light_sensor_pin, 
        invert_logic=invert_light_sensor,
        disabled=disable_light_sensor,
        debounce_time=debounce_time
    )
    
    if disable_light_sensor:
        print("Light sensor DISABLED - no low-light warnings will appear")
    elif light_sensor.initialized:
        # Debug print to help troubleshoot
        print("\n--- Light Sensor Debug ---")
        light_sensor.debug_print()
        print("\nTroubleshooting:")
        print("  - If always shows 'dark' when bright: use --invert-light-sensor")
        print("  - If flickering rapidly: increase --debounce-time (default 1.0s)")  
        print("  - To disable entirely: use --disable-light-sensor")
        print("--------------------------\n")
    else:
        print("Light sensor running in simulation mode")
    
    # Initialize camera
    print("\nInitializing camera...")
    camera = Camera(resolution=resolution, device=camera_device)
    camera_opened = camera.camera_open()
    if not camera_opened:
        print("⚠️ Warning: Camera failed to open, running with test pattern")
        print("   -> Camera will show test pattern instead of live feed")
    else:
        print("✅ Camera opened successfully")
        # Wait for camera thread to start capturing
        print("   Waiting for first frame...")
        max_wait = 3.0  # Wait up to 3 seconds
        waited = 0.0
        frame_received = False
        while waited < max_wait:
            ret, test_frame = camera.read()
            if ret and test_frame is not None:
                print(f"✅ Camera is capturing frames ({test_frame.shape[1]}x{test_frame.shape[0]})")
                frame_received = True
                break
            time.sleep(0.1)
            waited += 0.1
        
        if not frame_received:
            print("⚠️ Warning: Camera opened but no frames received yet")
            print("   -> Stream may start working after a few moments")
    
    # Start HTTP server
    try:
        server = ThreadedHTTPServer(('', port), MJPGHandler)
    except OSError as e:
        if e.errno == 98:  # Address already in use
            print(f"\nError: Port {port} is already in use!")
            print(f"To fix this, run one of these commands:")
            print(f"  sudo fuser -k {port}/tcp   # Kill process using port {port}")
            print(f"  python camera_stream.py --port {port + 1}  # Use different port")
            return
        raise
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    
    print(f"Camera server started!")
    print(f"Stream URL: http://localhost:{port}/?action=stream")
    print(f"Snapshot URL: http://localhost:{port}/?action=snapshot")
    
    print("\n" + "=" * 50)
    print("CAMERA SERVER RUNNING")
    print("=" * 50)
    
    # Get local IP for network access
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        print(f"Local IP address: {local_ip}")
        print(f"Stream URL (local): http://{local_ip}:{port}/?action=stream")
        print(f"Snapshot URL (local): http://{local_ip}:{port}/?action=snapshot")
        print(f"Status page: http://{local_ip}:{port}/test")
    except:
        print(f"Stream URL: http://localhost:{port}/?action=stream")
        print(f"Snapshot URL: http://localhost:{port}/?action=snapshot")
    
    print(f"\n⚠️  NETWORK REQUIREMENTS:")
    print(f"   - Frontend/browser must be on the SAME network as this robot")
    print(f"   - Or robot IP must be accessible from your network")
    print(f"   - Firewall must allow port {port}")
    print(f"\nLight sensor integration enabled:")
    print("  - Red border popup will appear when low light is detected")
    print("  - Warning: 'LOW LIGHT LEVEL DETECTED'")
    print("=" * 50)
    print("\nPress Ctrl+C to stop\n")
    
    # Main loop - update img_show with camera frames
    # Using proper frame timing for smooth streaming
    try:
        target_fps = 30
        frame_time = 1.0 / target_fps
        last_frame_time = time.time()
        frame_count = 0
        last_status_time = time.time()
        
        print("\n📹 Starting camera frame loop...")
        print(f"   Initial img_show state: {img_show is not None}")
        while True:
            ret, frame = camera.read()
            if ret and frame is not None:
                # Make a copy to avoid threading issues
                img_show = frame.copy() if hasattr(frame, 'copy') else frame
                frame_count += 1
                # Print status every 5 seconds
                if time.time() - last_status_time >= 5.0:
                    print(f"📹 Camera streaming: {frame_count} frames captured, {img_show.shape[1]}x{img_show.shape[0]}")
                    print(f"   img_show is set: {img_show is not None}, type: {type(img_show)}")
                    last_status_time = time.time()
            else:
                # No frame available - this is OK if camera just started
                if frame_count == 0 and time.time() - last_status_time >= 2.0:
                    print(f"⏳ Waiting for camera frames... (camera.opened={camera.opened}, simulation={camera.simulation_mode})")
                    print(f"   camera.read() returned: ret={ret}, frame is None={frame is None}")
                    last_status_time = time.time()
            
            # Maintain consistent frame rate
            current_time = time.time()
            elapsed = current_time - last_frame_time
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
            last_frame_time = time.time()
    except KeyboardInterrupt:
        print("\nShutting down camera server...")
        camera.camera_close()
        if light_sensor:
            light_sensor.cleanup()
            print("Light sensor cleaned up")
        server.shutdown()
        print("Camera server stopped")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="TonyPi Camera Streaming Server with Light Sensor Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Light Sensor Integration:
  When the light sensor detects low light levels, the camera stream will show:
  - Red border around the frame
  - "LOW LIGHT LEVEL DETECTED" warning popup
  - Warning message in console
  
Light Sensor Troubleshooting:
  If the sensor always shows "LOW LIGHT" even when bright:
    python camera_stream.py --invert-light-sensor
    
  If the sensor flickers rapidly between dark/bright:
    python camera_stream.py --debounce-time 2.0
    
  To disable the light sensor entirely:
    python camera_stream.py --disable-light-sensor
    
  You can also adjust the threshold potentiometer on your sensor module.
        """
    )
    parser.add_argument("--port", type=int, default=8081, help="HTTP server port (default: 8081)")
    parser.add_argument("--device", type=int, default=-1, help="Camera device index (-1 for auto)")
    parser.add_argument("--width", type=int, default=640, help="Frame width (default: 640)")
    parser.add_argument("--height", type=int, default=480, help="Frame height (default: 480)")
    parser.add_argument("--light-sensor-pin", type=int, default=24, help="GPIO pin for light sensor (default: 24)")
    parser.add_argument("--invert-light-sensor", action="store_true", 
                       help="Invert light sensor logic (use if sensor always shows wrong state)")
    parser.add_argument("--disable-light-sensor", action="store_true",
                       help="Disable light sensor entirely (no low-light warnings)")
    parser.add_argument("--debounce-time", type=float, default=1.0,
                       help="Seconds sensor must be stable before state changes (default: 1.0)")
    
    args = parser.parse_args()
    
    start_camera_server(
        port=args.port,
        camera_device=args.device,
        resolution=(args.width, args.height),
        light_sensor_pin=args.light_sensor_pin,
        invert_light_sensor=args.invert_light_sensor,
        disable_light_sensor=args.disable_light_sensor,
        debounce_time=args.debounce_time
    )


if __name__ == "__main__":
    main()
