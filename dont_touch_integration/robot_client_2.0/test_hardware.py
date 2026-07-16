#!/usr/bin/env python3
"""
TonyPi Robot Hardware Integration Tests
Run this script on the TonyPi robot to verify all hardware components.

Usage:
    python3 test_hardware.py           # Run all tests
    python3 test_hardware.py --quick   # Quick test (no buzzer/LED)
    python3 test_hardware.py --servo   # Test specific servo movement
"""

import sys
import os
import time
import argparse

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Also add TonyPi default path for when running on actual robot
if os.path.exists('/home/pi/TonyPi'):
    sys.path.append('/home/pi/TonyPi')
    sys.path.append('/home/pi/TonyPi/HiwonderSDK')

# Test results tracking
class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.tests = []
    
    def add(self, name, status, message=""):
        self.tests.append({"name": name, "status": status, "message": message})
        if status == "PASS":
            self.passed += 1
        elif status == "FAIL":
            self.failed += 1
        else:
            self.skipped += 1
        
        # Print result immediately
        icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⏭️"
        print(f"  {icon} {name}: {status}" + (f" - {message}" if message else ""))
    
    def summary(self):
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"  ✅ Passed:  {self.passed}")
        print(f"  ❌ Failed:  {self.failed}")
        print(f"  ⏭️  Skipped: {self.skipped}")
        print(f"  📊 Total:   {len(self.tests)}")
        print("=" * 60)
        
        if self.failed == 0:
            print("🎉 All tests passed! Your TonyPi hardware is working correctly.")
        else:
            print("⚠️  Some tests failed. Check the results above.")
            print("\nFailed tests:")
            for test in self.tests:
                if test["status"] == "FAIL":
                    print(f"  - {test['name']}: {test['message']}")

results = TestResults()


def print_header(title):
    """Print a section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_sdk_import():
    """Test 1: SDK Import"""
    print_header("TEST 1: SDK Import")
    
    try:
        from hiwonder import ros_robot_controller_sdk as rrc
        results.add("Import ros_robot_controller_sdk", "PASS")
    except ImportError as e:
        results.add("Import ros_robot_controller_sdk", "FAIL", str(e))
        return None
    
    try:
        from hiwonder.Controller import Controller
        results.add("Import Controller", "PASS")
    except ImportError as e:
        results.add("Import Controller", "FAIL", str(e))
    
    try:
        from hiwonder.Sonar import Sonar
        results.add("Import Sonar", "PASS")
    except ImportError as e:
        results.add("Import Sonar", "FAIL", str(e))
    
    try:
        from hiwonder.ActionGroupControl import runActionGroup
        results.add("Import ActionGroupControl", "PASS")
    except ImportError as e:
        results.add("Import ActionGroupControl", "FAIL", str(e))
    
    return rrc


def test_board_connection(rrc):
    """Test 2: Board Connection"""
    print_header("TEST 2: Board Connection")
    
    if rrc is None:
        results.add("Create Board instance", "SKIP", "SDK not imported")
        return None, None
    
    try:
        board = rrc.Board()
        if board.simulation_mode:
            results.add("Create Board instance", "FAIL", "Running in simulation mode (no hardware)")
            return board, None
        else:
            results.add("Create Board instance", "PASS", "Hardware mode")
    except Exception as e:
        results.add("Create Board instance", "FAIL", str(e))
        return None, None
    
    try:
        board.enable_reception(True)
        time.sleep(0.5)  # Wait for reception to start
        results.add("Enable data reception", "PASS")
    except Exception as e:
        results.add("Enable data reception", "FAIL", str(e))
    
    try:
        from hiwonder.Controller import Controller
        controller = Controller(board)
        results.add("Create Controller instance", "PASS")
    except Exception as e:
        results.add("Create Controller instance", "FAIL", str(e))
        controller = None
    
    return board, controller


def test_battery(board):
    """Test 3: Battery Reading"""
    print_header("TEST 3: Battery Voltage")
    
    if board is None or board.simulation_mode:
        results.add("Read battery voltage", "SKIP", "No hardware")
        return
    
    # Try multiple times
    battery = None
    for _ in range(10):
        battery = board.get_battery()
        if battery is not None:
            break
        time.sleep(0.1)
    
    if battery is not None:
        voltage = battery / 1000.0
        if voltage >= 9.0 and voltage <= 12.6:
            results.add("Read battery voltage", "PASS", f"{voltage:.2f}V")
        elif voltage < 9.0:
            results.add("Read battery voltage", "PASS", f"{voltage:.2f}V (LOW - Please charge!)")
        else:
            results.add("Read battery voltage", "PASS", f"{voltage:.2f}V (Value seems high)")
    else:
        results.add("Read battery voltage", "FAIL", "No data received")


def test_imu(board, controller):
    """Test 4: IMU Sensor"""
    print_header("TEST 4: IMU Sensor (Accelerometer/Gyroscope)")
    
    if board is None or board.simulation_mode:
        results.add("Read IMU data", "SKIP", "No hardware")
        return
    
    # Try multiple times
    imu = None
    for _ in range(10):
        if controller:
            imu = controller.get_imu()
        else:
            imu = board.get_imu()
        if imu is not None:
            break
        time.sleep(0.1)
    
    if imu is not None:
        ax, ay, az, gx, gy, gz = imu
        # Check if accelerometer detects gravity (~9.8 m/s^2)
        gravity_magnitude = (ax**2 + ay**2 + az**2) ** 0.5
        
        if 8.0 <= gravity_magnitude <= 12.0:
            results.add("IMU Accelerometer", "PASS", f"ax={ax:.2f}, ay={ay:.2f}, az={az:.2f}")
        else:
            results.add("IMU Accelerometer", "FAIL", f"Unexpected gravity: {gravity_magnitude:.2f} m/s²")
        
        results.add("IMU Gyroscope", "PASS", f"gx={gx:.2f}, gy={gy:.2f}, gz={gz:.2f}")
    else:
        results.add("Read IMU data", "FAIL", "No data received")


def test_servos(controller, board):
    """Test 5: Servo Readings"""
    print_header("TEST 5: Bus Servos (Reading Only - Safe)")
    
    if controller is None or (board and board.simulation_mode):
        results.add("Read servo data", "SKIP", "No hardware")
        return
    
    print("  Reading data from servos 1-6...")
    print("  (This only READS data, does NOT move servos)")
    print()
    
    servo_data = {}
    
    for servo_id in range(1, 7):
        print(f"  Servo {servo_id}:")
        
        # Read position
        try:
            position = controller.get_bus_servo_pulse(servo_id)
            if position is not None:
                results.add(f"Servo {servo_id} position", "PASS", f"{position} pulse")
                servo_data[servo_id] = {"position": position}
            else:
                results.add(f"Servo {servo_id} position", "FAIL", "No response")
                continue
        except Exception as e:
            results.add(f"Servo {servo_id} position", "FAIL", str(e))
            continue
        
        # Read temperature
        try:
            temp = controller.get_bus_servo_temp(servo_id)
            if temp is not None:
                if temp < 70:
                    results.add(f"Servo {servo_id} temperature", "PASS", f"{temp}°C")
                else:
                    results.add(f"Servo {servo_id} temperature", "PASS", f"{temp}°C (HOT!)")
                servo_data[servo_id]["temp"] = temp
            else:
                results.add(f"Servo {servo_id} temperature", "FAIL", "No response")
        except Exception as e:
            results.add(f"Servo {servo_id} temperature", "FAIL", str(e))
        
        # Read voltage
        try:
            voltage = controller.get_bus_servo_vin(servo_id)
            if voltage is not None:
                v = voltage / 1000.0
                results.add(f"Servo {servo_id} voltage", "PASS", f"{v:.2f}V")
                servo_data[servo_id]["voltage"] = voltage
            else:
                results.add(f"Servo {servo_id} voltage", "FAIL", "No response")
        except Exception as e:
            results.add(f"Servo {servo_id} voltage", "FAIL", str(e))
        
        print()
    
    return servo_data


def test_ultrasonic():
    """Test 6: Ultrasonic Sensor"""
    print_header("TEST 6: Ultrasonic Distance Sensor")
    
    try:
        from hiwonder.Sonar import Sonar
        sonar = Sonar()
        
        if sonar.simulation_mode:
            results.add("Ultrasonic sensor", "SKIP", "No I2C available")
            return
        
        # Read distance multiple times
        readings = []
        for _ in range(5):
            dist = sonar.getDistance()
            if dist != 99999:
                readings.append(dist)
            time.sleep(0.1)
        
        if readings:
            avg_dist = sum(readings) / len(readings)
            results.add("Read distance", "PASS", f"{avg_dist:.0f}mm ({avg_dist/10:.1f}cm)")
            
            # Provide hint
            if avg_dist < 100:
                print("  💡 Object detected very close!")
            elif avg_dist > 4000:
                print("  💡 No object in range or open space detected")
        else:
            results.add("Read distance", "FAIL", "Sensor not responding")
            
    except Exception as e:
        results.add("Ultrasonic sensor", "FAIL", str(e))


def test_buzzer(board, skip=False):
    """Test 7: Buzzer"""
    print_header("TEST 7: Buzzer")
    
    if skip:
        results.add("Buzzer test", "SKIP", "Skipped with --quick flag")
        return
    
    if board is None or board.simulation_mode:
        results.add("Buzzer test", "SKIP", "No hardware")
        return
    
    print("  🔊 Playing a short beep...")
    print("  (If you hear a beep, the buzzer works!)")
    
    try:
        board.set_buzzer(1000, 0.2, 0.1, 1)  # 1000Hz, 200ms on, 100ms off, 1 repeat
        time.sleep(0.5)
        results.add("Buzzer test", "PASS", "Beep sent (did you hear it?)")
    except Exception as e:
        results.add("Buzzer test", "FAIL", str(e))


def test_led(board, skip=False):
    """Test 8: LED"""
    print_header("TEST 8: LED")
    
    if skip:
        results.add("LED test", "SKIP", "Skipped with --quick flag")
        return
    
    if board is None or board.simulation_mode:
        results.add("LED test", "SKIP", "No hardware")
        return
    
    print("  💡 Blinking LED...")
    
    try:
        board.set_led(0.2, 0.2, 3, 1)  # 200ms on, 200ms off, 3 times, LED 1
        time.sleep(1.5)
        results.add("LED test", "PASS", "Blink command sent (did you see it?)")
    except Exception as e:
        results.add("LED test", "FAIL", str(e))


def test_camera():
    """Test 9: Camera"""
    print_header("TEST 9: Camera (Optional)")
    
    try:
        import cv2
        
        # Try to open camera
        cap = cv2.VideoCapture(-1)  # -1 for auto-detect
        if not cap.isOpened():
            cap = cv2.VideoCapture(0)
        
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                h, w = frame.shape[:2]
                results.add("Camera capture", "PASS", f"Resolution: {w}x{h}")
            else:
                results.add("Camera capture", "FAIL", "Could not read frame")
            cap.release()
        else:
            results.add("Camera capture", "FAIL", "Could not open camera")
    except ImportError:
        results.add("Camera test", "SKIP", "OpenCV not installed")
    except Exception as e:
        results.add("Camera test", "FAIL", str(e))


def test_gpio_light_sensor():
    """Test 10: GPIO Light Sensor (Optional)"""
    print_header("TEST 10: GPIO/Light Sensor (Optional)")
    
    try:
        import RPi.GPIO as GPIO
        results.add("GPIO available", "PASS", "RPi.GPIO imported")
    except ImportError:
        results.add("GPIO test", "SKIP", "RPi.GPIO not available (not on Raspberry Pi?)")


def test_servo_movement(controller, board):
    """Interactive test: Servo Movement"""
    print_header("INTERACTIVE: Servo Movement Test")
    
    if controller is None or (board and board.simulation_mode):
        print("  Cannot test servo movement - no hardware available")
        return
    
    print("  ⚠️  WARNING: This will MOVE the robot's servos!")
    print("  Make sure the robot is on a stable surface and won't fall.")
    print()
    
    response = input("  Proceed with servo movement test? (yes/no): ").strip().lower()
    if response != "yes":
        print("  Skipping servo movement test.")
        results.add("Servo movement", "SKIP", "User declined")
        return
    
    print()
    print("  Testing small movement on Servo 1 (head)...")
    
    try:
        # Read current position
        current = controller.get_bus_servo_pulse(1)
        if current is None:
            results.add("Servo movement", "FAIL", "Could not read current position")
            return
        
        print(f"  Current position: {current}")
        
        # Small movement test (±50 pulse)
        target = current + 50
        if target > 1000:
            target = current - 50
        
        print(f"  Moving to: {target}")
        controller.set_bus_servo_pulse(1, target, 500)  # 500ms
        time.sleep(0.7)
        
        # Read new position
        new_pos = controller.get_bus_servo_pulse(1)
        print(f"  New position: {new_pos}")
        
        # Move back
        print(f"  Moving back to: {current}")
        controller.set_bus_servo_pulse(1, current, 500)
        time.sleep(0.7)
        
        results.add("Servo movement", "PASS", "Servo moved successfully")
        
    except Exception as e:
        results.add("Servo movement", "FAIL", str(e))


def main():
    parser = argparse.ArgumentParser(description="TonyPi Hardware Integration Tests")
    parser.add_argument("--quick", action="store_true", help="Skip buzzer and LED tests")
    parser.add_argument("--servo", action="store_true", help="Include servo movement test")
    parser.add_argument("--camera", action="store_true", help="Include camera test")
    args = parser.parse_args()
    
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║        TonyPi Robot Hardware Integration Tests             ║")
    print("╠════════════════════════════════════════════════════════════╣")
    print("║  This script tests all hardware components on your robot.  ║")
    print("║  Make sure the robot is powered on and connected.          ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    
    # Run tests
    rrc = test_sdk_import()
    board, controller = test_board_connection(rrc)
    test_battery(board)
    test_imu(board, controller)
    test_servos(controller, board)
    test_ultrasonic()
    test_buzzer(board, skip=args.quick)
    test_led(board, skip=args.quick)
    
    if args.camera:
        test_camera()
    
    test_gpio_light_sensor()
    
    if args.servo:
        test_servo_movement(controller, board)
    
    # Print summary
    results.summary()
    
    return 0 if results.failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
