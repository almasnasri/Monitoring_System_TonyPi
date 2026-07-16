#!/usr/bin/python3
# coding=utf8
import sys
import os
import cv2 
import numpy as np 
import time

# --- 1. SETUP PATHS ---
FACTORY_PATH = '/home/pi/TonyPi/HiwonderSDK'
ROOT_PATH = '/home/pi/TonyPi'
CALIBRATION_PATH = '/home/pi/TonyPi/CameraCalibration/CalibrationConfig.py'

print(f"--- Camera Calibration Test (V2) ---")
sys.path.append(FACTORY_PATH)
sys.path.append(ROOT_PATH)

# Add Calibration Path
cali_dir = os.path.dirname(CALIBRATION_PATH)
if os.path.exists(cali_dir):
    sys.path.append(cali_dir)

# --- 2. LOAD CAMERA DRIVER ---
try:
    import hiwonder.yaml_handle as yaml_handle
    try:
        import hiwonder.Camera as Camera
    except ImportError:
        import Camera 
    print("[INIT] Drivers Loaded.")
except ImportError as e:
    print(f"[CRITICAL] Driver Error: {e}")
    sys.exit(1)

# --- 3. LOAD CALIBRATION ---
print("--- Loading Calibration Data ---")
mapx, mapy = None, None
try:
    import CalibrationConfig
    param_path = CalibrationConfig.calibration_param_path + '.npz'
    param_data = np.load(param_path)
    mtx = param_data['mtx_array']
    dist = param_data['dist_array']
    newcameramtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (640, 480), 0, (640, 480))
    mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, newcameramtx, (640, 480), 5)
    print("[SUCCESS] Undistort maps generated.")
except Exception as e:
    print(f"[FAIL] Calibration Error: {e}")
    sys.exit(1)

# --- 4. SMART CAMERA OPENER (The Fix) ---
def open_camera_smart():
    """ 
    Tries to open the camera using the Factory Logic.
    If 'open_once' is True, it uses the local web stream.
    Otherwise, it opens the hardware directly.
    """
    cap = None
    try:
        # Check factory setting
        # This file controls if the background streamer is running
        camera_config = yaml_handle.get_yaml_data('/boot/camera_setting.yaml')
        open_once = camera_config.get('open_once', False)
        
        if open_once:
            print("[INFO] Background Stream Detected. Connecting to local stream...")
            stream_url = 'http://127.0.0.1:8080/?action=stream?dummy=param.mjpg'
            cap = cv2.VideoCapture(stream_url)
        else:
            print("[INFO] Camera is free. Opening hardware directly...")
            cam_obj = Camera.Camera()
            cam_obj.camera_open()
            cap = cam_obj.cap # Access the internal cv2 object
            
        return cap

    except Exception as e:
        print(f"[ERROR] Logic failed: {e}")
        return None

# --- 5. EXECUTE TEST ---
print("--- Capturing Image ---")
cap = open_camera_smart()

if cap is None or not cap.isOpened():
    print("[ERROR] Could not open camera source.")
    sys.exit(1)

# Warm up
for i in range(5):
    ret, frame = cap.read()

if not ret:
    print("[ERROR] Camera opened but returned empty frame.")
    print("TIP: Try restarting the camera service: 'sudo systemctl restart mjpg_streamer'")
    sys.exit(1)

print("[SUCCESS] Image captured.")

# --- 6. APPLY CALIBRATION ---
def draw_grid(img, color=(0, 255, 0)):
    h, w = img.shape[:2]
    for x in range(0, w, 80): cv2.line(img, (x, 0), (x, h), color, 1)
    for y in range(0, h, 60): cv2.line(img, (0, y), (w, y), color, 1)
    return img

raw_debug = frame.copy()
draw_grid(raw_debug, color=(0, 0, 255))
cv2.putText(raw_debug, "RAW", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

flat_frame = cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR)
flat_debug = flat_frame.copy()
draw_grid(flat_debug, color=(0, 255, 0))
cv2.putText(flat_debug, "CALIBRATED", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

# Save
output_filename = "calibration_result.jpg"
combined = np.hstack((raw_debug, flat_debug))
cv2.imwrite(output_filename, combined)

print(f"\n[DONE] Image saved to: {output_filename}")
cap.release()