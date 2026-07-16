import os
import time
import sys
from collections import deque

# Handle missing vision modules gracefully
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    print("[WARNING] OpenCV (cv2) not available. Vision features disabled.")
    CV2_AVAILABLE = False
    cv2 = None

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    print("[WARNING] YOLO (ultralytics) not available. Object detection disabled.")
    YOLO_AVAILABLE = False
    YOLO = None

# Import actions module
from . import action_module

# CONFIGURATION
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CURRENT_DIR) 
MODEL_PATH = os.path.join(BASE_DIR, "resources", "models", "cardboard_v1.pt")

# --- TUNING SETTINGS ---
CONFIDENCE_THRESHOLD = 0.25 
LOCK_ENTER_TOLERANCE = 80   # <--- WIDENED (Was 60) to catch it easier
LOCK_EXIT_TOLERANCE = 120   # <--- WIDENED (Was 100)
MAX_MISSED_FRAMES = 10
SMOOTHING_BUFFER = 5

class VisionController:
    def __init__(self):
        print(f"[Vision] Loading YOLO model from: {MODEL_PATH}")
        if YOLO_AVAILABLE:
            try:
                self.model = YOLO(MODEL_PATH)
                self.class_names = self.model.names
                print(f"✅ Model Loaded Successfully!")
            except Exception as e:
                print(f"❌ CRITICAL ERROR: Could not load model. {e}")
                self.model = None
        else:
            print("[WARNING] YOLO not available - running without object detection")
            self.model = None

        self.last_action_time = 0
        self.is_locked = False 
        
        # Stability Variables
        self.missed_counter = 0
        self.last_valid_detection = None
        self.center_history = deque(maxlen=SMOOTHING_BUFFER)

        self.actions = {
            "cardboard": "Active",
            "box": "Active",
            "package": "Active"
        }

        # Initialize actions module
        self.robot_actions = action_module.RobotActions()

    def reset(self):
        """
        Clears all memory. Call this when starting a new voice command.
        """
        self.is_locked = False
        self.missed_counter = 0
        self.last_valid_detection = None
        self.center_history.clear()
        print("[Vision] Logic Reset.")

    def detect(self, frame):
        if not self.model or not YOLO_AVAILABLE:
            print("[WARNING] Object detection not available")
            return None, 0, None, 0

        results = self.model(frame, verbose=False, conf=CONFIDENCE_THRESHOLD)
        
        raw_det = None
        max_conf = 0
        
        for r in results:
            for box in r.boxes:
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                label = self.class_names[cls_id]
                
                if label.lower() in self.actions and conf > max_conf:
                    max_conf = conf
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cx = int((x1 + x2) / 2)
                    raw_det = (label, conf, (x1, y1, x2, y2), cx)

        if raw_det:
            self.missed_counter = 0
            label, conf, box, cx = raw_det
            self.center_history.append(cx)
            smoothed_cx = int(sum(self.center_history) / len(self.center_history))
            self.last_valid_detection = (label, conf, box, smoothed_cx)
            return self.last_valid_detection
        else:
            if self.missed_counter < MAX_MISSED_FRAMES and self.last_valid_detection is not None:
                self.missed_counter += 1
                return self.last_valid_detection
            else:
                self.center_history.clear()
                self.is_locked = False
                return None

    def get_navigation_command(self, center_x, frame_width):
        screen_center = frame_width // 2
        error = center_x - screen_center
        limit = LOCK_EXIT_TOLERANCE if self.is_locked else LOCK_ENTER_TOLERANCE

        if abs(error) < limit:
            self.is_locked = True
            return "LOCKED", error
        else:
            self.is_locked = False
            return ("TURN_LEFT" if error < 0 else "TURN_RIGHT"), error

    def get_all_detections(self, frame):
        """Get all detected objects in frame for debugging
        
        Returns:
            list: List of all detections with confidence scores
        """
        if not self.model or not YOLO_AVAILABLE:
            return []
        
        results = self.model(frame, verbose=False, conf=0.1)  # Lower threshold for debug
        all_dets = []
        
        for r in results:
            for box in r.boxes:
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                label = self.class_names[cls_id]
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                all_dets.append((label, conf, (x1, y1, x2, y2)))
        
        return all_dets

    def run_action(self, label):
        if label == "Peeling":
            return self.robot_actions.run_diecut_peeling()
        elif label == "Insert Label":
            return self.robot_actions.run_label_insertion()
        elif label == "Transport":
            return self.robot_actions.run_transport_box()
        elif label == "Flip":
            return self.robot_actions.run_sheet_flip_over()
        elif label == "Pick Up Cardboard":
            return self.robot_actions.run_pick_up_cardboard()
        elif label == "Transport Cardboard":
            return self.robot_actions.run_transport_cardboard()
        else:
            print(f"[Vision] Unknown action: {label}")
            return False