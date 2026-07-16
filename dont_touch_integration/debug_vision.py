#!/usr/bin/python3
import cv2
import time
import sys
import threading
import hiwonder.Camera as Camera  # <--- FIXED IMPORT
from modules import vision_module

# SHARED VARIABLES
latest_frame = None
latest_result = None
running = True
frame_lock = threading.Lock()
result_lock = threading.Lock()

def inference_worker(vision):
    global latest_frame, latest_result, running
    print("🧠 AI Brain Thread Started...")
    while running:
        img_to_process = None
        with frame_lock:
            if latest_frame is not None:
                img_to_process = latest_frame.copy()
        
        if img_to_process is not None:
            # Run detection
            detection_data = vision.detect(img_to_process)
            with result_lock:
                latest_result = detection_data
        time.sleep(0.01)

def main():
    global latest_frame, running
    print("------------------------------------------")
    print("    SMOOTH THREADED VISION DEBUGGER       ")
    print("------------------------------------------")
    
    vision = vision_module.VisionController()
    
    # --- CAMERA FIX ---
    print("📷 Opening Hiwonder Camera...")
    try:
        cap = Camera.Camera()
        cap.camera_open()
    except Exception as e:
        print(f"❌ CRITICAL: Could not open camera. {e}")
        return
    # ------------------

    ai_thread = threading.Thread(target=inference_worker, args=(vision,))
    ai_thread.daemon = True
    ai_thread.start()

    print("✅ System Online. Video should be smooth now.")
    print("   (Press 'q' to quit)")

    while True:
        # READ FRAME FROM HIWONDER CAMERA
        ret, frame = cap.read()
        if not ret: 
            time.sleep(0.01)
            continue

        with frame_lock: latest_frame = frame

        # GET AI RESULTS
        current_data = None
        with result_lock: current_data = latest_result

        if current_data:
            label, conf, box, cx = current_data
            if label:
                x1, y1, x2, y2 = box
                nav_cmd, error = vision.get_navigation_command(cx, 640)
                
                color = (0, 255, 0)
                if nav_cmd == "LOCKED": 
                    color = (0, 0, 255)
                    cv2.putText(frame, "LOCKED", (x1, y1-30), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"{label} {conf:.2f}", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        else:
            # If no detection, verify we are scanning
            cv2.putText(frame, "Scanning...", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 2)

        cv2.line(frame, (320, 0), (320, 480), (100, 100, 100), 1)
        cv2.imshow("Threaded Vision", frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    running = False
    cap.camera_close()
    cv2.destroyAllWindows()
    ai_thread.join()

if __name__ == "__main__":
    main()