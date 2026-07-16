#!/usr/bin/python3
import cv2
import time
import sys
import os
import threading
import subprocess

# Add TonyPi default path for when running on actual robot
if os.path.exists('/home/pi/TonyPi'):
    sys.path.insert(0, '/home/pi/TonyPi/HiwonderSDK/hiwonder')
    sys.path.insert(0, '/home/pi/TonyPi/HiwonderSDK')
    sys.path.insert(0, '/home/pi/TonyPi')

# --- HARDWARE IMPORTS ---
import hiwonder.Camera as Camera
from modules import voice_module
from modules import vision_module
from modules import light_sensor
from modules import ultrasonic_sensor
from modules import qr_navigate
from modules.robot_client import RobotClient

# --- CONFIGURATION ---
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# MQTT Configuration (can be overridden via environment variables)
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
TELEMETRY_ENABLED = os.getenv("TELEMETRY_ENABLED", "true").lower() == "true"
CAMERA_STREAM_PORT = int(os.getenv("CAMERA_PORT", 8081))

# ROBOT STATES
STATE_IDLE = "IDLE"           
STATE_SEARCHING = "SEARCHING" 
STATE_ACTING = "ACTING"
STATE_NAVIGATE_QR = "NAVIGATE_QR"

# THREADING SHARED VARS
latest_frame = None
latest_result = None
running = True
frame_lock = threading.Lock()
result_lock = threading.Lock()
detected_station = None  # For QR navigation

# ==========================================
# 🧠 VISION THREAD
# ==========================================
def inference_worker(vision):
    global latest_frame, latest_result, running
    print("🧠 AI Vision Thread Started...")
    while running:
        img_to_process = None
        with frame_lock:
            if latest_frame is not None:
                img_to_process = latest_frame.copy()
        
        if img_to_process is not None:
            detection_data = vision.detect(img_to_process)
            with result_lock:
                latest_result = detection_data
        time.sleep(0.01)

# ==========================================
# 🎮 MAIN CONTROLLER
# ==========================================
def main():
    global latest_frame, running, latest_result
    print("------------------------------------------")
    print("      TONYPI ROBOT: MAIN CONTROLLER       ")
    print("------------------------------------------")

    # 1. Setup Hardware
    voice = voice_module.WonderEcho()
    vision = vision_module.VisionController()
    
    # Initialize Light Sensor on Pin 24
    try:
        sensor = light_sensor.LightSensor(pin=24)
    except Exception as e:
        print(f"⚠️ Light sensor hardware not available or busy: {e}")
        class MockLightSensor:
            def is_dark(self): return False
            def cleanup(self): pass
        sensor = MockLightSensor()
    
    # Initialize Ultrasonic Sensor for obstacle detection
    try:
        ultrasonic = ultrasonic_sensor.UltrasonicSensor()
    except Exception as e:
        print(f"⚠️ Ultrasonic sensor hardware not available or busy: {e}")
        class MockUltrasonic:
            def get_distance(self): return 999.0
            def cleanup(self): pass
        ultrasonic = MockUltrasonic()
    
    # ==========================================
    # 🚨 EMERGENCY STOP STATE
    # ==========================================
    emergency_stop_triggered = False
    emergency_stop_reason = None
    
    def handle_emergency_stop(reason: str):
        """Callback for emergency stop from monitoring system."""
        nonlocal emergency_stop_triggered, emergency_stop_reason
        nonlocal current_state, current_task, job_start_time, job_task_name, job_phase
        
        print(f"🚨🚨🚨 EMERGENCY STOP: {reason} 🚨🚨🚨")
        emergency_stop_triggered = True
        emergency_stop_reason = reason
        
        # Stop any current actions
        if current_state != STATE_IDLE:
            voice_module.speak("Emergency stop activated.")
            current_state = STATE_IDLE
            current_task = None
            vision.reset()
        
        # Cancel any active job
        if job_start_time is not None:
            job_start_time = None
            job_task_name = None
            job_phase = None
    
    # Initialize Robot Client for telemetry (MQTT monitoring + Camera streaming)
    robot_client = None
    if TELEMETRY_ENABLED:
        print(f"📡 Connecting to monitoring system at {MQTT_BROKER}:{MQTT_PORT}...")
        print(f"📹 Camera stream will be on port {CAMERA_STREAM_PORT}")
        try:
            robot_client = RobotClient(
                mqtt_broker=MQTT_BROKER,
                mqtt_port=MQTT_PORT,
                auto_telemetry=True,
                telemetry_interval=10.0,
                camera_port=CAMERA_STREAM_PORT,
                enable_camera_stream=True
            )
            if robot_client.start():
                print("✅ Connected to monitoring system")
                print(f"📹 Camera stream: {robot_client.camera_url}")
                robot_client.send_log("INFO", "Main controller started", "main")
                
                # Register emergency stop callback
                robot_client.set_emergency_stop_callback(handle_emergency_stop)
                print("🚨 Emergency stop handler registered")
            else:
                print("⚠️ MQTT unavailable - camera stream still running")
                print(f"📹 Camera stream: {robot_client.camera_url}")
        except Exception as e:
            print(f"⚠️ Could not connect to monitoring: {e}")
            robot_client = None

    # 2. Open Camera
    print("📷 Opening Hiwonder Camera...")
    try:
        cap = Camera.Camera()
        cap.camera_open()
    except Exception as e:
        print(f"❌ CRITICAL: Could not open camera. {e}")
        if robot_client:
            robot_client.send_log("ERROR", f"Camera failed: {e}", "main")
            robot_client.stop()
        return

    # 3. Start Vision Brain
    ai_thread = threading.Thread(target=inference_worker, args=(vision,))
    ai_thread.daemon = True
    ai_thread.start()

    current_state = STATE_IDLE
    current_task = None
    was_dark_last_frame = False
    search_start_time = None  # Track when search started
    SEARCH_TIMEOUT = 60  # seconds - timeout if cardboard not found
    
    # ==========================================
    # 📊 JOB TIMING INTEGRATION
    # ==========================================
    job_start_time = None       # When current job started
    job_task_name = None        # Name of current task
    job_phase = None            # Current phase: "scanning", "searching", "executing"
    
    # Estimated durations for each task type (in seconds)
    TASK_ESTIMATED_DURATIONS = {
        "Peeling": 45,
        "Insert Label": 30,
        "Flip": 25,
        "Transport": 40,
        "Pick Up Cardboard": 35,
        "Transport Cardboard": 50
    }
    
    # Telemetry timing
    last_sensor_send = 0
    SENSOR_SEND_INTERVAL = 2.0  # Send sensor data every 2 seconds
    last_location_send = 0
    LOCATION_SEND_INTERVAL = 5.0  # Send location every 5 seconds
    
    # Location tracking (simulated/estimated position)
    robot_position = {"x": 0.0, "y": 0.0, "z": 0.0}
    
    # Initial Voice Check
    voice_module.speak("System online.")
    print("✅ System Ready.")

    try:
        while True:
            # A. UPDATE CAMERA
            ret, frame = cap.read()
            if not ret: 
                time.sleep(0.01)
                continue
            with frame_lock: latest_frame = frame

            # ==========================================
            # 🚨 EMERGENCY STOP CHECK (from monitoring system)
            # ==========================================
            if robot_client and robot_client.is_emergency_stopped():
                # Check if we just entered emergency stop
                if not emergency_stop_triggered:
                    emergency_stop_triggered = True
                    emergency_stop_reason = robot_client.get_emergency_stop_reason()
                    print(f"🚨 EMERGENCY STOP ACTIVE: {emergency_stop_reason}")
                    voice_module.speak("Emergency stop active.")
                    
                    # Cancel current job if any
                    if job_start_time is not None:
                        if robot_client:
                            elapsed = time.time() - job_start_time
                            robot_client.send_job_event(
                                task_name=job_task_name or current_task or "unknown",
                                status="cancelled",
                                phase=job_phase,
                                elapsed_time=elapsed,
                                reason=emergency_stop_reason
                            )
                        job_start_time = None
                        job_task_name = None
                        job_phase = None
                    
                    current_state = STATE_IDLE
                    current_task = None
                    vision.reset()
                
                # Display emergency stop on frame
                cv2.rectangle(frame, (0, 0), (FRAME_WIDTH, FRAME_HEIGHT), (0, 0, 255), 10)
                cv2.rectangle(frame, (50, 180), (FRAME_WIDTH - 50, 300), (0, 0, 150), -1)
                cv2.putText(frame, "EMERGENCY STOP", (120, 230), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
                cv2.putText(frame, "Press RESUME in monitoring system", (80, 270), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # Send frame to stream
                if robot_client:
                    robot_client.update_frame(frame)
                
                cv2.imshow("TonyPi", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): break
                continue
            else:
                # Emergency stop cleared
                if emergency_stop_triggered:
                    emergency_stop_triggered = False
                    emergency_stop_reason = None
                    print("✅ Emergency stop cleared - resuming normal operation")
                    voice_module.speak("Emergency stop cleared. System ready.")

            # ==========================================
            # 🚨 SAFETY CHECK: LIGHT SENSOR
            # ==========================================
            # Check if it is dark using your class
            is_dark_now = sensor.is_dark()
            
            if is_dark_now:
                # 🛑 DANGER: TOO DARK!
                if not was_dark_last_frame:
                    voice_module.speak("Too dark. Stopping now.")
                    if robot_client:
                        robot_client.send_log("WARNING", "Darkness detected - stopping", "safety")
                
                # If we were doing something, STOP and SPEAK.
                if current_state != STATE_IDLE:
                    print("⚠️ DARKNESS DETECTED! ABORTING ACTION!")
                    
                    # 📊 JOB TIMING: Job cancelled due to darkness
                    if robot_client and job_start_time:
                        elapsed = time.time() - job_start_time
                        robot_client.send_job_event(
                            task_name=job_task_name or current_task,
                            status="cancelled",
                            phase=job_phase,
                            elapsed_time=elapsed,
                            reason="Darkness detected - safety stop"
                        )
                    job_start_time = None
                    job_task_name = None
                    job_phase = None
                    
                    current_state = STATE_IDLE
                    current_task = None
                    vision.reset() # Reset vision memory
                
                # Visual Warning on Screen
                cv2.rectangle(frame, (0,0), (FRAME_WIDTH, FRAME_HEIGHT), (0,0,255), 5)
                cv2.putText(frame, "⚠️ TOO DARK - STOPPED", (150, 240), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
                
                was_dark_last_frame = True
                
                # IMPORTANT: Send frame to stream BEFORE skipping (so red boundary appears in stream)
                if robot_client:
                    robot_client.update_frame(frame)
                
                # Skip the rest of the loop (Don't listen or look)
                cv2.imshow("TonyPi", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): break
                continue
            
            # If light just came back on, notify user ONE time
            if was_dark_last_frame and not is_dark_now:
                voice_module.speak("Light levels normal. System ready.")
                was_dark_last_frame = False

            # ==========================================
            # 🚨 OBSTACLE DETECTION: ULTRASONIC SENSOR
            # ==========================================
            if current_state != STATE_IDLE:
                distance = ultrasonic.get_distance()
                if distance is not None and ultrasonic.is_obstacle_detected():
                    print(f"⚠️ OBSTACLE DETECTED at {distance}cm! ABORTING ACTION!")
                    voice_module.speak(f"Obstacle detected. Stopping.")
                    
                    if robot_client:
                        robot_client.send_log("WARNING", f"Obstacle detected at {distance}cm", "safety")
                    
                    # 📊 JOB TIMING: Job cancelled due to obstacle
                    if robot_client and job_start_time:
                        elapsed = time.time() - job_start_time
                        robot_client.send_job_event(
                            task_name=job_task_name or current_task,
                            status="cancelled",
                            phase=job_phase,
                            elapsed_time=elapsed,
                            reason=f"Obstacle detected at {distance}cm"
                        )
                    job_start_time = None
                    job_task_name = None
                    job_phase = None
                    
                    # Stop current action and return to idle
                    current_state = STATE_IDLE
                    current_task = None
                    vision.reset()
                    
                    # Visual warning
                    cv2.rectangle(frame, (0,0), (FRAME_WIDTH, FRAME_HEIGHT), (0, 165, 255), 5)
                    cv2.putText(frame, f"🚨 OBSTACLE: {distance}cm", (150, 240), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 3)

            # ==========================================
            # 🎤 VOICE COMMANDS
            # ==========================================
            if current_state != STATE_ACTING:
                cmd = voice.get_command()
                if cmd:
                    print(f"🎤 Command: {cmd}")
                    
                    if cmd == "Wake Up":
                        voice_module.speak("Listening.")
                        current_state = STATE_IDLE
                    
                    elif cmd == "Stop":
                        voice_module.speak("Stopping.")
                        
                        # 📊 JOB TIMING: Job cancelled by user command
                        if robot_client and job_start_time:
                            elapsed = time.time() - job_start_time
                            robot_client.send_job_event(
                                task_name=job_task_name or current_task,
                                status="cancelled",
                                phase=job_phase,
                                elapsed_time=elapsed,
                                reason="User stop command"
                            )
                        job_start_time = None
                        job_task_name = None
                        job_phase = None
                        
                        current_state = STATE_IDLE
                        current_task = None
                        vision.reset()
                    
                    # --- TASK COMMANDS: Go directly to searching for cardboard using YOLO ---
                    elif cmd in ["Peeling", "Insert Label", "Flip", "Transport", "Pick Up Cardboard", "Transport Cardboard", "Pick Up"]:
                        if not sensor.is_dark():
                            # Normalize voice command "Pick Up" to task "Pick Up Cardboard"
                            current_task = "Pick Up Cardboard" if cmd == "Pick Up" else cmd
                            # Bypassing QR navigation, go directly to target search
                            voice_module.speak(f"Searching for cardboard.")
                            current_state = STATE_SEARCHING
                            vision.reset()
                            
                            # ==========================================
                            # 📊 JOB TIMING: Start tracking job
                            # ==========================================
                            job_start_time = time.time()
                            job_task_name = current_task
                            job_phase = "searching"
                            estimated_duration = TASK_ESTIMATED_DURATIONS.get(current_task, 30)
                            
                            if robot_client:
                                robot_client.send_log("INFO", f"Task started: {current_task}", "voice")
                                # Send job started event (items_total=1 for single task job)
                                robot_client.send_job_event(
                                    task_name=current_task,
                                    status="started",
                                    phase="searching",
                                    estimated_duration=estimated_duration,
                                    items_done=0,
                                    items_total=1
                                )
                        else:
                            voice_module.speak("Cannot start. It is too dark.")

            # ==========================================
            # 🤖 ROBOT LOGIC
            # ==========================================
            if current_state == STATE_IDLE:
                cv2.putText(frame, "IDLE", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            elif current_state == STATE_NAVIGATE_QR:
                cv2.putText(frame, "SCANNING FOR STATION QR...", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                cv2.putText(frame, "Press ESC to cancel", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
                
                # Start QR navigation in background thread (only once)
                if not qr_navigate.navigation_active:
                    with frame_lock:
                        qr_navigate.current_frame_shared = latest_frame.copy() if latest_frame is not None else None
                    qr_navigate.start_qr_navigation_async(timeout=60)
                
                # Update shared frame for navigation thread
                with frame_lock:
                    qr_navigate.current_frame_shared = latest_frame.copy() if latest_frame is not None else None
                
                # Check if navigation completed
                if not qr_navigate.navigation_active:
                    detected_station = qr_navigate.get_navigation_result()
                    if detected_station:
                        voice_module.speak(f"Reached station {detected_station}. Searching for cardboard.")
                        
                        # Send QR scan event to monitoring system
                        if robot_client:
                            robot_client.send_qr_scan(
                                qr_data=detected_station,
                                station_name=detected_station,
                                action="navigation_complete"
                            )
                            robot_client.send_log("INFO", f"Arrived at station: {detected_station}", "navigation")
                        
                        # ====================================================
                        # 📝 AUTO QR FLOW: After finding station, search for cardboard
                        # ====================================================
                        current_state = STATE_SEARCHING
                        
                        # 📊 JOB TIMING: Update phase to searching
                        job_phase = "searching"
                        if robot_client and job_start_time:
                            elapsed = time.time() - job_start_time
                            robot_client.send_job_event(
                                task_name=job_task_name,
                                status="in_progress",
                                phase="searching",
                                elapsed_time=elapsed
                            )
                    else:
                        voice_module.speak("QR scan cancelled or timeout.")
                        current_state = STATE_IDLE
                        
                        # 📊 JOB TIMING: Job cancelled
                        if robot_client and job_start_time:
                            elapsed = time.time() - job_start_time
                            robot_client.send_job_event(
                                task_name=job_task_name,
                                status="cancelled",
                                phase="scanning",
                                elapsed_time=elapsed,
                                reason="QR scan timeout or cancelled"
                            )
                        job_start_time = None
                        job_task_name = None
                        job_phase = None
                        current_task = None

            elif current_state == STATE_SEARCHING:
                current_det = None
                with result_lock: current_det = latest_result
                
                # Display distance and debug info
                distance = ultrasonic.get_distance()
                if distance is not None:
                    cv2.putText(frame, f"Distance: {distance}cm", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                if current_det:
                    label, conf, box, cx = current_det
                    x1, y1, x2, y2 = box
                    nav_cmd, error = vision.get_navigation_command(cx, FRAME_WIDTH)
                    
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"{label} ({conf:.2f})", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    
                    # Send vision telemetry
                    if robot_client:
                        robot_client.send_vision_data(
                            label=label,
                            confidence=conf,
                            bbox=box,
                            center_x=cx,
                            frame_width=FRAME_WIDTH,                            frame_height=FRAME_HEIGHT,                            state=current_state,
                            is_locked=(nav_cmd == "LOCKED"),
                            nav_cmd=nav_cmd,
                            error=error
                        )

                    if nav_cmd == "LOCKED":
                        cv2.putText(frame, "LOCKED", (x1, y1-30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
                        voice_module.speak("Target locked.")
                        
                        if robot_client:
                            robot_client.send_log("INFO", f"Target locked: {label}", "vision")
                        
                        # ====================================================
                        # 📝 LOGIC STEP 2: VISION LOCK
                        # ====================================================
                        # The vision system has successfully centered the cardboard.
                        # Now we switch to ACTING to perform the physical task.
                        current_state = STATE_ACTING
                        
                        # 📊 JOB TIMING: Update phase to executing
                        job_phase = "executing"
                        if robot_client and job_start_time:
                            elapsed = time.time() - job_start_time
                            robot_client.send_job_event(
                                task_name=job_task_name,
                                status="in_progress",
                                phase="executing",
                                elapsed_time=elapsed
                            )
                        
                    elif nav_cmd == "TURN_LEFT":
                        cv2.arrowedLine(frame, (320, 240), (270, 240), (255, 255, 0), 3)
                        cv2.putText(frame, "TURN LEFT", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                    elif nav_cmd == "TURN_RIGHT":
                        cv2.arrowedLine(frame, (320, 240), (370, 240), (255, 255, 0), 3)
                        cv2.putText(frame, "TURN RIGHT", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                else:
                    cv2.putText(frame, "Scanning for cardboard...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                    print(f"[Main] Searching for cardboard but none detected. Model loaded: {vision.model is not None}\")")

            elif current_state == STATE_ACTING:
                cv2.putText(frame, f"TASK: {current_task}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
                # Show job timing on screen
                if job_start_time:
                    elapsed = time.time() - job_start_time
                    cv2.putText(frame, f"Time: {elapsed:.1f}s", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                
                if robot_client:
                    robot_client.send_log("INFO", f"Executing task: {current_task}", "action")
                
                # ====================================================
                # 📝 LOGIC STEP 3: EXECUTE ACTION
                # ====================================================
                # We now run the specific script for the task we saved in Step 1.
                print(f"[Main] Running action: {current_task}")
                action_start = time.time()
                success = vision.run_action(current_task)
                action_duration = time.time() - action_start
                
                if not success:
                    time.sleep(3) 
                
                voice_module.speak(f"{current_task} complete.")
                
                # ==========================================
                # 📊 JOB TIMING: Job completed - calculate total duration
                # ==========================================
                if job_start_time:
                    total_duration = time.time() - job_start_time
                    estimated = TASK_ESTIMATED_DURATIONS.get(job_task_name, 30)
                    
                    print(f"[Job Timer] Task '{job_task_name}' completed in {total_duration:.1f}s (estimated: {estimated}s)")
                    
                    if robot_client:
                        robot_client.send_log("INFO", f"Task completed: {current_task} in {total_duration:.1f}s", "action")
                        robot_client.send_job_event(
                            task_name=job_task_name,
                            status="completed",
                            phase="done",
                            elapsed_time=total_duration,
                            estimated_duration=estimated,
                            action_duration=action_duration,
                            success=success,
                            items_done=1,
                            items_total=1
                        )
                else:
                    if robot_client:
                        robot_client.send_log("INFO", f"Task completed: {current_task}", "action")
                
                # Reset job timing
                job_start_time = None
                job_task_name = None
                job_phase = None
                
                current_state = STATE_IDLE
                current_task = None

            # ==========================================
            # 📡 TELEMETRY: Send sensor data periodically
            # ==========================================
            current_time = time.time()
            if robot_client and (current_time - last_sensor_send) >= SENSOR_SEND_INTERVAL:
                # Collect sensor data
                distance = ultrasonic.get_distance()
                is_dark = sensor.is_dark()
                
                sensor_data = {
                    "ultrasonic_distance": distance if distance is not None else -1,
                    "light_sensor_dark": 1 if is_dark else 0,
                    "light_level": 20 if is_dark else 80
                }
                robot_client.send_sensor_data(sensor_data)
                last_sensor_send = current_time
            
            # Send location updates periodically
            if robot_client and (current_time - last_location_send) >= LOCATION_SEND_INTERVAL:
                # Update location based on state (simple simulation)
                # In a real scenario, you'd use odometry or SLAM
                if current_state == STATE_ACTING:
                    robot_position["x"] += 0.1  # Simulate movement
                
                robot_client.send_location(
                    x=robot_position["x"],
                    y=robot_position["y"],
                    z=robot_position["z"]
                )
                last_location_send = current_time

            # Send frame to robot client for streaming (with all overlays)
            if robot_client:
                robot_client.update_frame(frame)
            
            if os.getenv("DISPLAY"):
                try:
                    cv2.imshow("TonyPi", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'): break
                except Exception:
                    time.sleep(0.03)
            else:
                # Headless mode (SSH/no monitor)
                time.sleep(0.03)

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        running = False
        
        # Cleanup robot client
        if robot_client:
            robot_client.send_log("INFO", "Main controller shutting down", "main")
            robot_client.stop()
            print("📡 Disconnected from monitoring system")
        
        sensor.cleanup()
        ultrasonic.cleanup()
        cap.camera_close()
        cv2.destroyAllWindows()
        ai_thread.join()

if __name__ == "__main__":
    main()