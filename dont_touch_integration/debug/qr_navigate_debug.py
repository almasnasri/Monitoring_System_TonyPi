import cv2
import hiwonder.ActionGroupControl as AGC
from hiwonder import Controller, ros_robot_controller_sdk as rrc
import time
from pyzbar import pyzbar
import threading
import queue

# ============ INITIALIZATION ============
rrc_board = rrc.Board()
Board = Controller.Controller(rrc_board)

# Servo IDs
HEAD_PAN_SERVO = 2
HEAD_TILT_SERVO = 1

# Configuration Constants (TonyPi Pro Standard)
PAN_CENTER = 800  
TILT_CENTER = 800
SERVO_PAN_MIN = 400
SERVO_PAN_MAX = 1200
SERVO_TILT_MIN = 500
SERVO_TILT_MAX = 1100

# Thread-safe communication
scan_result_queue = queue.Queue()
current_frame_shared = None
navigation_active = False
qr_scanning = False

# Head Scanning State
head_turn = 'left_right'
x_dis = PAN_CENTER
y_dis = TILT_CENTER
d_x = 25  # Increased step size for smoother detection loops
d_y = 25
scan_time_last = 0

# ============ HELPER FUNCTIONS ============

def run_action_async(action_name):
    """Runs a robot action group in a background thread to prevent blocking vision."""
    t = threading.Thread(
        target=AGC.runActionGroup,
        args=(action_name,),
        daemon=True
    )
    t.start()

def reset_head_scan():
    """Resets head variables to center."""
    global head_turn, x_dis, y_dis, d_x, d_y
    head_turn = 'left_right'
    x_dis = PAN_CENTER
    y_dis = TILT_CENTER
    d_x = 25
    d_y = 25
    rrc_board.pwm_servo_set_position(0.5, [[HEAD_PAN_SERVO, PAN_CENTER], [HEAD_TILT_SERVO, TILT_CENTER]])

# ============ CORE MOVEMENT LOGIC (TRANSPORT.PY STYLE) ============



def scan_360_head():
    """
    Implements the zigzag scanning logic from transport.py.
    Uses 'abs' to force direction reversal so the head doesn't get stuck.
    """
    global head_turn, x_dis, y_dis, d_x, d_y, scan_time_last
    
    current_time = time.time()
    if current_time - scan_time_last < 0.03: # 30ms throttle
        return
    scan_time_last = current_time
    
    if head_turn == 'left_right':
        x_dis += d_x
        # Force direction reversal at limits
        if x_dis >= SERVO_PAN_MAX:
            x_dis = SERVO_PAN_MAX
            d_x = -abs(d_x) # Force move LEFT
            head_turn = 'up_down'
        elif x_dis <= SERVO_PAN_MIN:
            x_dis = SERVO_PAN_MIN
            d_x = abs(d_x)  # Force move RIGHT
            head_turn = 'up_down'
            
    elif head_turn == 'up_down':
        y_dis += d_y
        # Flip vertical direction if we hit top/bottom
        if y_dis >= SERVO_TILT_MAX or y_dis <= SERVO_TILT_MIN:
            d_y = -d_y
        head_turn = 'left_right' # Go back to horizontal sweep

    rrc_board.pwm_servo_set_position(0.02, [
        [HEAD_PAN_SERVO, int(x_dis)], 
        [HEAD_TILT_SERVO, int(y_dis)]
    ])

def navigate_to_station(frame_getter, timeout=60):
    """
    Main Navigation Loop.
    Coordinates Head (Vision) with Body (Legs).
    """
    global qr_scanning, x_dis, y_dis

    print("[INFO] Starting QR Navigation...")
    qr_scanning = True
    start_time = time.time()
    reset_head_scan()

    while qr_scanning:
        if time.time() - start_time > timeout:
            print("[INFO] Navigation Timeout")
            break

        frame = frame_getter()
        if frame is None:
            time.sleep(0.01)
            continue
        
        # QR Detection
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        barcodes = pyzbar.decode(frame_rgb)

        if barcodes:
            # --- TARGET FOUND ---
            barcode = barcodes[0]
            data = barcode.data.decode("utf-8")
            (bx, by, bw, bh) = barcode.rect
            
            # Calculate error relative to frame center
            frame_center_x = frame.shape[1] // 2
            qr_center_x = bx + (bw // 2)
            pixel_error = qr_center_x - frame_center_x

            # --- HEAD-BODY COORDINATION (THE 'SECRET' LOGIC) ---
            # Instead of just pixels, we check where the head is pointed.
            pan_error_from_center = x_dis - PAN_CENTER
            
            # If head is tilted too far, rotate body to face that way
            if pan_error_from_center < -120:
                print(f"↩ QR on LEFT ({pan_error_from_center}) - Rotating Body")
                run_action_async('turn_left')
                x_dis += 30 # Gradually move head back to center
            elif pan_error_from_center > 120:
                print(f"↪ QR on RIGHT ({pan_error_from_center}) - Rotating Body")
                run_action_async('turn_right')
                x_dis -= 30 # Gradually move head back to center
            
            # --- FORWARD APPROACH ---
            else:
                # Small adjustments based on image pixels
                if pixel_error < -50:
                    run_action_async('turn_left')
                elif pixel_error > 50:
                    run_action_async('turn_right')
                else:
                    # If centered, check distance (QR width)
                    if bw < 140: 
                        print("→ Moving forward")
                        run_action_async('go_forward')
                    else:
                        print(f"🎯 STATION REACHED: {data}")
                        qr_scanning = False
                        return data
            
            # Maintain visual lock
            rrc_board.pwm_servo_set_position(0.08, [[HEAD_PAN_SERVO, int(x_dis)], [HEAD_TILT_SERVO, int(y_dis)]])
        
        else:
            # --- SEARCH MODE ---
            scan_360_head()

        time.sleep(0.02)

    return None

# ============ THREADING WRAPPERS ============

def _navigate_background_worker(timeout=60):
    global qr_scanning, current_frame_shared, navigation_active

    def get_current_frame():
        return current_frame_shared.copy() if current_frame_shared is not None else None

    try:
        result = navigate_to_station(get_current_frame, timeout=timeout)
        scan_result_queue.put(result)
    except Exception as e:
        print(f"[ERROR] Thread failure: {e}")
        scan_result_queue.put(None)
    finally:
        navigation_active = False

def start_qr_navigation_async(timeout=60):
    global navigation_active
    if navigation_active: return False

    navigation_active = True
    t = threading.Thread(target=_navigate_background_worker, args=(timeout,), daemon=True)
    t.start()
    return True

def get_navigation_result():
    try:
        return scan_result_queue.get_nowait()
    except queue.Empty:
        return None

# ============ ENTRY POINT ============
if __name__ == "__main__":
    print("This module is designed to be imported into your main.py loop.")
    print("Example Usage:")
    print("1. Set: qr_navigate.current_frame_shared = frame")
    print("2. Call: qr_navigate.start_qr_navigation_async()")