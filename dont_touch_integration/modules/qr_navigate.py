import cv2
import hiwonder.ActionGroupControl as AGC
from hiwonder import Controller, ros_robot_controller_sdk as rrc
import time
from pyzbar import pyzbar
import threading
import queue

# ============ INITIALIZATION ============
rrc_board = rrc.Board()
ctl = Controller.Controller(rrc_board)

HEAD_PAN_SERVO = 2
HEAD_TILT_SERVO = 1

# Configuration Constants
PAN_CENTER = 1450  
TILT_CENTER = 1150  # Fixed stable position - looking at table level (no upward scanning)
TILT_START = 1150   # Start at stable table-level position
SERVO_PAN_MIN = 1000
SERVO_PAN_MAX = 1900
SERVO_TILT_MIN = 1150  # Fixed tilt - no vertical scanning
SERVO_TILT_MAX = 1150  # Fixed tilt - no vertical scanning

# Communication & State
scan_result_queue = queue.Queue()
current_frame_shared = None
navigation_active = False
qr_scanning = False

object_center_x = -1
object_width = 0
lost_frames = 0  # Counter to prevent losing lock during walking shakes
MAX_LOST_FRAMES = 30  # ~0.6 seconds of memory to maintain lock while walking
qr_locked = False  # Track if QR has been locked
last_known_x = -1  # Remember last QR position

head_turn = 'left_right'
x_dis = PAN_CENTER
y_dis = TILT_START  # Start scanning at table level
d_x = 20  
d_y = 15  # Slower vertical scan for thorough table-level coverage
scan_time_last = 0

# ============ HELPER FUNCTIONS ============

def run_action_async(action_name):
    t = threading.Thread(target=AGC.runActionGroup, args=(action_name,), daemon=True)
    t.start()

# ============ MOVEMENT THREAD ============

def move():
    global object_center_x, object_width, x_dis, y_dis, head_turn, d_x, d_y, qr_scanning, lost_frames, scan_time_last, qr_locked, last_known_x
    
    while True:
        if qr_scanning:
            # --- CASE 1: TARGET LOCKED AND TRACKING ---
            if qr_locked and (object_center_x >= 0 or lost_frames < MAX_LOST_FRAMES):
                
                # Keep head centered when tracking locked QR
                if lost_frames < MAX_LOST_FRAMES // 2 and object_center_x >= 0:
                    # Adjust head to track QR position for better visual lock
                    target_x = PAN_CENTER
                    if object_center_x < 240:
                        target_x = PAN_CENTER - 100
                    elif object_center_x > 400:
                        target_x = PAN_CENTER + 100
                    x_dis = target_x
                    ctl.set_pwm_servo_pulse(HEAD_PAN_SERVO, x_dis, 50)
                
                # 1. Align Head/Body
                if abs(x_dis - PAN_CENTER) > 80:
                    if x_dis > PAN_CENTER:
                        AGC.runActionGroup('turn_right')
                    else:
                        AGC.runActionGroup('turn_left')
                    
                    # Align head to center immediately
                    x_dis, y_dis = PAN_CENTER, TILT_CENTER
                    ctl.set_pwm_servo_pulse(HEAD_TILT_SERVO, y_dis, 100)
                    ctl.set_pwm_servo_pulse(HEAD_PAN_SERVO, x_dis, 100)
                
                # 2. Fine-tune Body Alignment based on pixel position
                elif object_center_x < 240 and object_center_x != -1:
                    run_action_async('turn_left')
                elif object_center_x > 400 and object_center_x != -1:
                    run_action_async('turn_right')
                
                # 3. Walk Forward
                else:
                    if object_width < 145 and object_width != 0:
                        run_action_async('go_forward')
                    elif object_width >= 145:
                        print("🎯 STATION REACHED")
                        qr_scanning = False 
                        qr_locked = False

            # --- CASE 2: INITIAL SEARCHING (not locked yet) ---
            elif not qr_locked and object_center_x == -1:
                current_time = time.time()
                if current_time - scan_time_last > 0.03:
                    # Only scan left-right (PAN), keep TILT fixed at 1150
                    x_dis += d_x
                    if x_dis >= SERVO_PAN_MAX or x_dis <= SERVO_PAN_MIN:
                        d_x = -d_x
                    
                    # Keep y_dis fixed at TILT_CENTER
                    y_dis = TILT_CENTER
                    
                    ctl.set_pwm_servo_pulse(HEAD_TILT_SERVO, y_dis, 20)
                    ctl.set_pwm_servo_pulse(HEAD_PAN_SERVO, x_dis, 20)
                    scan_time_last = current_time
            
            # --- CASE 3: LOCKED BUT LOST VISION (keep walking toward last known position) ---
            elif qr_locked and lost_frames >= MAX_LOST_FRAMES:
                # Don't rescan, just keep walking toward where we last saw it
                if last_known_x < 240:
                    run_action_async('turn_left')
                elif last_known_x > 400:
                    run_action_async('turn_right')
                else:
                    run_action_async('go_forward')
                
        time.sleep(0.02)

# Start thread
th = threading.Thread(target=move)
th.daemon = True
th.start()

# ============ VISION PROCESS ============

def navigate_to_station(frame_getter, timeout=60):
    global qr_scanning, object_center_x, object_width, lost_frames, qr_locked, last_known_x

    print("[INFO] Locking QR Station...")
    qr_scanning = True
    qr_locked = False
    start_time = time.time()
    station_data = None

    while qr_scanning:
        if time.time() - start_time > timeout:
            break

        frame = frame_getter()
        if frame is None: continue
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        barcodes = pyzbar.decode(frame_rgb)

        if barcodes:
            # RESET lost frames as soon as we see it
            lost_frames = 0
            barcode = barcodes[0]
            station_data = barcode.data.decode("utf-8")
            (x, y, w, h) = barcode.rect
            object_center_x = x + (w // 2)
            object_width = w
            last_known_x = object_center_x
            
            # Lock QR after first detection
            if not qr_locked:
                qr_locked = True
                print("[INFO] 🎯 QR LOCKED! Starting navigation...")
            
            # Debug: Show tracking info every 10 frames
            if lost_frames % 10 == 0:
                print(f"[TRACK] QR detected: x={object_center_x}, width={object_width}, lost_frames={lost_frames}")
        else:
            # Increment lost frames instead of immediately going to -1
            lost_frames += 1
            if lost_frames >= MAX_LOST_FRAMES:
                object_center_x = -1
                object_width = 0

        time.sleep(0.02)

    return station_data

# ============ THREADING WRAPPERS ============

def _navigate_background_worker(timeout=60):
    global current_frame_shared, navigation_active
    def get_current_frame():
        return current_frame_shared.copy() if current_frame_shared is not None else None
    
    result = navigate_to_station(get_current_frame, timeout=timeout)
    scan_result_queue.put(result)
    navigation_active = False

def start_qr_navigation_async(timeout=60):
    global navigation_active
    if navigation_active: return False
    navigation_active = True
    t = threading.Thread(target=_navigate_background_worker, args=(timeout,), daemon=True)
    t.start()
    return True

def get_navigation_result():
    try: return scan_result_queue.get_nowait()
    except queue.Empty: return None