#!/usr/bin/env python3
# encoding: utf-8
"""
STM32 Robot Controller SDK
Handles serial communication with the TonyPi's STM32 board for:
- Servo control (bus servos and PWM servos)
- IMU data (accelerometer and gyroscope)
- Battery voltage monitoring
- LED and buzzer control
- Motor control
"""

import enum
import time
import queue
import struct
import threading

# Try to import serial, provide mock if not available
try:
    import serial
    from serial.serialutil import SerialException
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    class SerialException(Exception):
        pass


class PacketControllerState(enum.IntEnum):
    """Communication protocol format: 0xAA 0x55 Length Function ID Data Checksum"""
    PACKET_CONTROLLER_STATE_STARTBYTE1 = 0
    PACKET_CONTROLLER_STATE_STARTBYTE2 = 1
    PACKET_CONTROLLER_STATE_LENGTH = 2
    PACKET_CONTROLLER_STATE_FUNCTION = 3
    PACKET_CONTROLLER_STATE_ID = 4
    PACKET_CONTROLLER_STATE_DATA = 5
    PACKET_CONTROLLER_STATE_CHECKSUM = 6


class PacketFunction(enum.IntEnum):
    """Control functions available via serial interface"""
    PACKET_FUNC_SYS = 0           # System functions (battery, etc.)
    PACKET_FUNC_LED = 1           # LED control
    PACKET_FUNC_BUZZER = 2        # Buzzer control
    PACKET_FUNC_MOTOR = 3         # Motor control
    PACKET_FUNC_PWM_SERVO = 4     # PWM servo control (1-4)
    PACKET_FUNC_BUS_SERVO = 5     # Bus servo control
    PACKET_FUNC_KEY = 6           # Button input
    PACKET_FUNC_IMU = 7           # IMU data (accelerometer/gyroscope)
    PACKET_FUNC_GAMEPAD = 8       # Gamepad input
    PACKET_FUNC_SBUS = 9          # RC receiver (SBUS)
    PACKET_FUNC_OLED = 10         # OLED display
    PACKET_FUNC_RGB = 11          # RGB LED control
    PACKET_FUNC_NONE = 12


class PacketReportKeyEvents(enum.IntEnum):
    """Button event types"""
    KEY_EVENT_PRESSED = 0x01
    KEY_EVENT_LONGPRESS = 0x02
    KEY_EVENT_LONGPRESS_REPEAT = 0x04
    KEY_EVENT_RELEASE_FROM_LP = 0x08
    KEY_EVENT_RELEASE_FROM_SP = 0x10
    KEY_EVENT_CLICK = 0x20
    KEY_EVENT_DOUBLE_CLICK = 0x40
    KEY_EVENT_TRIPLE_CLICK = 0x80


# CRC8 lookup table for checksum calculation
crc8_table = [
    0, 94, 188, 226, 97, 63, 221, 131, 194, 156, 126, 32, 163, 253, 31, 65,
    157, 195, 33, 127, 252, 162, 64, 30, 95, 1, 227, 189, 62, 96, 130, 220,
    35, 125, 159, 193, 66, 28, 254, 160, 225, 191, 93, 3, 128, 222, 60, 98,
    190, 224, 2, 92, 223, 129, 99, 61, 124, 34, 192, 158, 29, 67, 161, 255,
    70, 24, 250, 164, 39, 121, 155, 197, 132, 218, 56, 102, 229, 187, 89, 7,
    219, 133, 103, 57, 186, 228, 6, 88, 25, 71, 165, 251, 120, 38, 196, 154,
    101, 59, 217, 135, 4, 90, 184, 230, 167, 249, 27, 69, 198, 152, 122, 36,
    248, 166, 68, 26, 153, 199, 37, 123, 58, 100, 134, 216, 91, 5, 231, 185,
    140, 210, 48, 110, 237, 179, 81, 15, 78, 16, 242, 172, 47, 113, 147, 205,
    17, 79, 173, 243, 112, 46, 204, 146, 211, 141, 111, 49, 178, 236, 14, 80,
    175, 241, 19, 77, 206, 144, 114, 44, 109, 51, 209, 143, 12, 82, 176, 238,
    50, 108, 142, 208, 83, 13, 239, 177, 240, 174, 76, 18, 145, 207, 45, 115,
    202, 148, 118, 40, 171, 245, 23, 73, 8, 86, 180, 234, 105, 55, 213, 139,
    87, 9, 235, 181, 54, 104, 138, 212, 149, 203, 41, 119, 244, 170, 72, 22,
    233, 183, 85, 11, 136, 214, 52, 106, 43, 117, 151, 201, 74, 20, 246, 168,
    116, 42, 200, 150, 21, 75, 169, 247, 182, 232, 10, 84, 215, 137, 107, 53
]


def checksum_crc8(data):
    """Calculate CRC8 checksum for data validation"""
    check = 0
    for b in data:
        check = crc8_table[check ^ b]
    return check & 0x00FF


class SBusStatus:
    """SBUS receiver status for RC control"""
    def __init__(self):
        self.channels = [0] * 16
        self.channel_17 = False
        self.channel_18 = False
        self.signal_loss = True
        self.fail_safe = False


class Board:
    """
    Main board communication class.
    Handles all serial communication with the TonyPi's STM32 controller.
    """
    
    buttons_map = {
        'GAMEPAD_BUTTON_MASK_L2':        0x0001,
        'GAMEPAD_BUTTON_MASK_R2':        0x0002,
        'GAMEPAD_BUTTON_MASK_SELECT':    0x0004,
        'GAMEPAD_BUTTON_MASK_START':     0x0008,
        'GAMEPAD_BUTTON_MASK_L3':        0x0020,
        'GAMEPAD_BUTTON_MASK_R3':        0x0040,
        'GAMEPAD_BUTTON_MASK_CROSS':     0x0100,
        'GAMEPAD_BUTTON_MASK_CIRCLE':    0x0200,
        'GAMEPAD_BUTTON_MASK_SQUARE':    0x0800,
        'GAMEPAD_BUTTON_MASK_TRIANGLE':  0x1000,
        'GAMEPAD_BUTTON_MASK_L1':        0x4000,
        'GAMEPAD_BUTTON_MASK_R1':        0x8000
    }

    def __init__(self, device="/dev/ttyAMA0", baudrate=1000000, timeout=5):
        """
        Initialize board communication.
        
        Args:
            device: Serial port device (default: /dev/ttyAMA0 for Raspberry Pi)
            baudrate: Serial baudrate (default: 1000000)
            timeout: Read timeout in seconds
        """
        self.enable_recv = False
        self.frame = []
        self.recv_count = 0
        self.simulation_mode = not SERIAL_AVAILABLE
        
        if SERIAL_AVAILABLE:
            try:
                self.port = serial.Serial(None, baudrate, timeout=timeout)
                self.port.rts = False
                self.port.dtr = False
                self.port.setPort(device)
                self.port.open()
            except Exception as e:
                print(f"Warning: Could not open serial port {device}: {e}")
                print("Running in simulation mode")
                self.simulation_mode = True
                self.port = None
        else:
            print("Serial library not available, running in simulation mode")
            self.port = None

        self.state = PacketControllerState.PACKET_CONTROLLER_STATE_STARTBYTE1
        self.servo_read_lock = threading.Lock()
        self.pwm_servo_read_lock = threading.Lock()
        
        # Data queues for async reception
        self.sys_queue = queue.Queue(maxsize=1)
        self.bus_servo_queue = queue.Queue(maxsize=1)
        self.pwm_servo_queue = queue.Queue(maxsize=1)
        self.key_queue = queue.Queue(maxsize=1)
        self.imu_queue = queue.Queue(maxsize=1)
        self.gamepad_queue = queue.Queue(maxsize=1)
        self.sbus_queue = queue.Queue(maxsize=1)

        # Packet parsers
        self.parsers = {
            PacketFunction.PACKET_FUNC_SYS: self.packet_report_sys,
            PacketFunction.PACKET_FUNC_KEY: self.packet_report_key,
            PacketFunction.PACKET_FUNC_IMU: self.packet_report_imu,
            PacketFunction.PACKET_FUNC_GAMEPAD: self.packet_report_gamepad,
            PacketFunction.PACKET_FUNC_BUS_SERVO: self.packet_report_serial_servo,
            PacketFunction.PACKET_FUNC_SBUS: self.packet_report_sbus,
            PacketFunction.PACKET_FUNC_PWM_SERVO: self.packet_report_pwm_servo
        }

        # Start receive thread if serial is available
        if not self.simulation_mode:
            threading.Thread(target=self.recv_task, daemon=True).start()
            time.sleep(0.1)

    def packet_report_sys(self, data):
        """Handle system data packets (battery, etc.)"""
        try:
            self.sys_queue.put_nowait(data)
        except queue.Full:
            pass

    def packet_report_key(self, data):
        """Handle button input packets"""
        try:
            self.key_queue.put_nowait(data)
        except queue.Full:
            pass

    def packet_report_imu(self, data):
        """Handle IMU data packets"""
        try:
            self.imu_queue.put_nowait(data)
        except queue.Full:
            pass

    def packet_report_gamepad(self, data):
        """Handle gamepad input packets"""
        try:
            self.gamepad_queue.put_nowait(data)
        except queue.Full:
            pass

    def packet_report_serial_servo(self, data):
        """Handle bus servo response packets"""
        try:
            self.bus_servo_queue.put_nowait(data)
        except queue.Full:
            pass

    def packet_report_pwm_servo(self, data):
        """Handle PWM servo response packets"""
        try:
            self.pwm_servo_queue.put_nowait(data)
        except queue.Full:
            pass

    def packet_report_sbus(self, data):
        """Handle SBUS/RC receiver packets"""
        try:
            self.sbus_queue.put_nowait(data)
        except queue.Full:
            pass

    def get_battery(self):
        """
        Get battery voltage in millivolts.
        
        Returns:
            int: Battery voltage in mV, or None if not available
        """
        if self.simulation_mode:
            return 11500  # Simulate ~11.5V
            
        if self.enable_recv:
            try:
                data = self.sys_queue.get(block=False)
                if data[0] == 0x04:
                    return struct.unpack('<H', data[1:])[0]
                else:
                    return None
            except queue.Empty:
                return None
        else:
            return None

    def get_button(self):
        """
        Get button press event.
        
        Returns:
            tuple: (key_id, event_type) or None if no event
        """
        if self.simulation_mode:
            return None
            
        if self.enable_recv:
            try:
                data = self.key_queue.get(block=False)
                key_id = data[0]
                key_event = PacketReportKeyEvents(data[1])
                if key_event == PacketReportKeyEvents.KEY_EVENT_CLICK:
                    return key_id, 0
                elif key_event == PacketReportKeyEvents.KEY_EVENT_PRESSED:
                    return key_id, 1
            except queue.Empty:
                return None
        else:
            return None

    def get_imu(self):
        """
        Get IMU sensor data (accelerometer and gyroscope).
        
        Returns:
            tuple: (ax, ay, az, gx, gy, gz) - accelerometer (m/s^2) and gyroscope (deg/s)
                   Returns None if no data available
        """
        if self.simulation_mode:
            import random
            # Simulate IMU data
            return (
                random.uniform(-0.5, 0.5),   # ax
                random.uniform(-0.5, 0.5),   # ay
                random.uniform(9.5, 10.0),   # az (gravity)
                random.uniform(-5, 5),       # gx
                random.uniform(-5, 5),       # gy
                random.uniform(-5, 5)        # gz
            )
            
        if self.enable_recv:
            try:
                # Returns (ax, ay, az, gx, gy, gz)
                return struct.unpack('<6f', self.imu_queue.get(block=False))
            except queue.Empty:
                return None
        else:
            return None

    def get_gamepad(self):
        """Get gamepad input data."""
        if self.simulation_mode:
            return None
            
        if self.enable_recv:
            try:
                gamepad_data = struct.unpack("<HB4b", self.gamepad_queue.get(block=False))
                axes = [0, 0, 0, 0, 0, 0, 0, 0]
                buttons = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                
                for b in self.buttons_map:
                    if self.buttons_map[b] & gamepad_data[0]:
                        if b == 'GAMEPAD_BUTTON_MASK_R2':
                            axes[4] = 1
                        elif b == 'GAMEPAD_BUTTON_MASK_L2':
                            axes[5] = 1
                        elif b == 'GAMEPAD_BUTTON_MASK_CROSS':
                            buttons[0] = 1
                        elif b == 'GAMEPAD_BUTTON_MASK_CIRCLE':
                            buttons[1] = 1
                        elif b == 'GAMEPAD_BUTTON_MASK_SQUARE':
                            buttons[3] = 1
                        elif b == 'GAMEPAD_BUTTON_MASK_TRIANGLE':
                            buttons[4] = 1
                        elif b == 'GAMEPAD_BUTTON_MASK_L1':
                            buttons[6] = 1
                        elif b == 'GAMEPAD_BUTTON_MASK_R1':
                            buttons[7] = 1
                        elif b == 'GAMEPAD_BUTTON_MASK_SELECT':
                            buttons[10] = 1
                        elif b == 'GAMEPAD_BUTTON_MASK_START':
                            buttons[11] = 1
               
                # Process analog sticks
                if gamepad_data[2] > 0:
                    axes[0] = -gamepad_data[2] / 127
                elif gamepad_data[2] < 0:
                    axes[0] = -gamepad_data[2] / 128

                if gamepad_data[3] > 0:
                    axes[1] = gamepad_data[3] / 127
                elif gamepad_data[3] < 0:
                    axes[1] = gamepad_data[3] / 128

                if gamepad_data[4] > 0:
                    axes[2] = -gamepad_data[4] / 127
                elif gamepad_data[4] < 0:
                    axes[2] = -gamepad_data[4] / 128

                if gamepad_data[5] > 0:
                    axes[3] = gamepad_data[5] / 127
                elif gamepad_data[5] < 0:
                    axes[3] = gamepad_data[5] / 128
            
                # Process d-pad
                if gamepad_data[1] == 9:
                    axes[6] = 1
                elif gamepad_data[1] == 13:
                    axes[6] = -1
                
                if gamepad_data[1] == 11:
                    axes[7] = -1
                elif gamepad_data[1] == 15:
                    axes[7] = 1
                    
                return axes, buttons
            except queue.Empty:
                return None
        else:
            return None

    def get_sbus(self):
        """Get SBUS/RC receiver data."""
        if self.simulation_mode:
            return None
            
        if self.enable_recv:
            try:
                sbus_data = self.sbus_queue.get(block=False)
                status = SBusStatus()
                *status.channels, ch17, ch18, sig_loss, fail_safe = struct.unpack("<16hBBBB", sbus_data)
                status.channel_17 = ch17 != 0
                status.channel_18 = ch18 != 0
                status.signal_loss = sig_loss != 0
                status.fail_safe = fail_safe != 0
                data = []
                if status.signal_loss:
                    data = 16 * [0.5]
                    data[4] = 0
                    data[5] = 0
                    data[6] = 0
                    data[7] = 0
                else:
                    for i in status.channels:
                        data.append((i - 192)/(1792 - 192))
                return data
            except queue.Empty:
                return None
        else:
            return None

    def buf_write(self, func, data):
        """Write a command packet to the serial port."""
        if self.simulation_mode or self.port is None:
            return
            
        buf = [0xAA, 0x55, int(func)]
        buf.append(len(data))
        buf.extend(data)
        buf.append(checksum_crc8(bytes(buf[2:])))
        self.port.write(buf)

    def set_led(self, on_time, off_time, repeat=1, led_id=1):
        """Control LED blinking."""
        on_time = int(on_time * 1000)
        off_time = int(off_time * 1000)
        self.buf_write(PacketFunction.PACKET_FUNC_LED, struct.pack("<BHHH", led_id, on_time, off_time, repeat))

    def set_buzzer(self, freq, on_time, off_time, repeat=1):
        """Control buzzer beeping."""
        on_time = int(on_time * 1000)
        off_time = int(off_time * 1000)
        self.buf_write(PacketFunction.PACKET_FUNC_BUZZER, struct.pack("<HHHH", freq, on_time, off_time, repeat))

    def set_motor_speed(self, speeds):
        """Set motor speeds. speeds is a list of [motor_id, speed] pairs."""
        data = [0x01, len(speeds)]
        for i in speeds:
            data.extend(struct.pack("<Bf", int(i[0] - 1), float(i[1])))
        self.buf_write(PacketFunction.PACKET_FUNC_MOTOR, data)

    def set_oled_text(self, line, text):
        """Set OLED display text."""
        data = [line, len(text)]
        data.extend(bytes(text, encoding='utf-8'))
        self.buf_write(PacketFunction.PACKET_FUNC_OLED, data)

    def set_rgb(self, pixels):
        """Set RGB LED colors. pixels is a list of [index, r, g, b] tuples."""
        data = [0x01, len(pixels)]
        for index, r, g, b in pixels:
            data.extend(struct.pack("<BBBB", int(index - 1), int(r), int(g), int(b)))
        self.buf_write(PacketFunction.PACKET_FUNC_RGB, data)

    def set_motor_duty(self, dutys):
        """Set motor duty cycles."""
        data = [0x05, len(dutys)]
        for i in dutys:
            data.extend(struct.pack("<Bf", int(i[0] - 1), float(i[1])))
        self.buf_write(PacketFunction.PACKET_FUNC_MOTOR, data)

    def pwm_servo_set_position(self, duration, positions):
        """Set PWM servo positions."""
        duration = int(duration * 1000)
        data = [0x01, duration & 0xFF, 0xFF & (duration >> 8), len(positions)]
        for i in positions:
            data.extend(struct.pack("<BH", i[0], i[1]))
        self.buf_write(PacketFunction.PACKET_FUNC_PWM_SERVO, data)
    
    def pwm_servo_set_offset(self, servo_id, offset):
        """Set PWM servo offset."""
        data = struct.pack("<BBb", 0x07, servo_id, int(offset))
        self.buf_write(PacketFunction.PACKET_FUNC_PWM_SERVO, data)

    def pwm_servo_read_and_unpack(self, servo_id, cmd, unpack):
        """Read and unpack PWM servo data."""
        if self.simulation_mode:
            return None
            
        with self.servo_read_lock:
            self.buf_write(PacketFunction.PACKET_FUNC_PWM_SERVO, [cmd, servo_id])
            data = self.pwm_servo_queue.get(block=True)
            servo_id, cmd, info = struct.unpack(unpack, data)
            return info

    def pwm_servo_read_offset(self, servo_id):
        """Read PWM servo offset."""
        return self.pwm_servo_read_and_unpack(servo_id, 0x09, "<BBb")

    def pwm_servo_read_position(self, servo_id):
        """Read PWM servo position."""
        return self.pwm_servo_read_and_unpack(servo_id, 0x05, "<BBH")

    def bus_servo_enable_torque(self, servo_id, enable):
        """Enable or disable bus servo torque."""
        if enable:
            data = struct.pack("<BB", 0x0B, servo_id)
        else:
            data = struct.pack("<BB", 0x0C, servo_id)
        self.buf_write(PacketFunction.PACKET_FUNC_BUS_SERVO, data)
        time.sleep(0.02)

    def bus_servo_set_id(self, servo_id_now, servo_id_new):
        """Set bus servo ID."""
        data = struct.pack("<BBB", 0x10, servo_id_now, servo_id_new)
        self.buf_write(PacketFunction.PACKET_FUNC_BUS_SERVO, data)
        time.sleep(0.02)

    def bus_servo_set_offset(self, servo_id, offset):
        """Set bus servo offset."""
        data = struct.pack("<BBb", 0x20, servo_id, int(offset))
        self.buf_write(PacketFunction.PACKET_FUNC_BUS_SERVO, data)
        time.sleep(0.02)

    def bus_servo_save_offset(self, servo_id):
        """Save bus servo offset to EEPROM."""
        data = struct.pack("<BB", 0x24, servo_id)
        self.buf_write(PacketFunction.PACKET_FUNC_BUS_SERVO, data)
        time.sleep(0.02)

    def bus_servo_set_angle_limit(self, servo_id, limit):
        """Set bus servo angle limits."""
        data = struct.pack("<BBHH", 0x30, servo_id, int(limit[0]), int(limit[1]))
        self.buf_write(PacketFunction.PACKET_FUNC_BUS_SERVO, data)
        time.sleep(0.02)

    def bus_servo_set_vin_limit(self, servo_id, limit):
        """Set bus servo voltage limits."""
        data = struct.pack("<BBHH", 0x34, servo_id, int(limit[0]), int(limit[1]))
        self.buf_write(PacketFunction.PACKET_FUNC_BUS_SERVO, data)
        time.sleep(0.02)

    def bus_servo_set_temp_limit(self, servo_id, limit):
        """Set bus servo temperature limit."""
        data = struct.pack("<BBb", 0x38, servo_id, int(limit))
        self.buf_write(PacketFunction.PACKET_FUNC_BUS_SERVO, data)
        time.sleep(0.02)

    def bus_servo_stop(self, servo_id):
        """Stop bus servos."""
        data = [0x03, len(servo_id)]
        data.extend(struct.pack("<" + 'B' * len(servo_id), *servo_id))
        self.buf_write(PacketFunction.PACKET_FUNC_BUS_SERVO, data)

    def bus_servo_set_position(self, duration, positions):
        """
        Set bus servo positions.
        
        Args:
            duration: Time in seconds for the movement
            positions: List of [servo_id, pulse] pairs (pulse 0-1000)
        """
        duration = int(duration * 1000)
        data = [0x01, duration & 0xFF, 0xFF & (duration >> 8), len(positions)]
        for i in positions:
            data.extend(struct.pack("<BH", i[0], i[1]))
        self.buf_write(PacketFunction.PACKET_FUNC_BUS_SERVO, data)

    def bus_servo_read_and_unpack(self, servo_id, cmd, unpack):
        """Read and unpack bus servo data."""
        if self.simulation_mode:
            return None
            
        with self.servo_read_lock:
            self.buf_write(PacketFunction.PACKET_FUNC_BUS_SERVO, [cmd, servo_id])
            data = self.bus_servo_queue.get(block=True)
            servo_id, cmd, success, *info = struct.unpack(unpack, data)
            if success == 0:
                return info
            return None

    def bus_servo_read_id(self, servo_id=254):
        """Read bus servo ID."""
        return self.bus_servo_read_and_unpack(servo_id, 0x12, "<BBbB")

    def bus_servo_read_offset(self, servo_id):
        """Read bus servo offset."""
        return self.bus_servo_read_and_unpack(servo_id, 0x22, "<BBbb")
    
    def bus_servo_read_position(self, servo_id):
        """Read bus servo position (pulse value)."""
        return self.bus_servo_read_and_unpack(servo_id, 0x05, "<BBbh")

    def bus_servo_read_vin(self, servo_id):
        """Read bus servo voltage in millivolts."""
        return self.bus_servo_read_and_unpack(servo_id, 0x07, "<BBbH")
    
    def bus_servo_read_temp(self, servo_id):
        """Read bus servo temperature in Celsius."""
        return self.bus_servo_read_and_unpack(servo_id, 0x09, "<BBbB")

    def bus_servo_read_temp_limit(self, servo_id):
        """Read bus servo temperature limit."""
        return self.bus_servo_read_and_unpack(servo_id, 0x3A, "<BBbB")

    def bus_servo_read_angle_limit(self, servo_id):
        """Read bus servo angle limits."""
        return self.bus_servo_read_and_unpack(servo_id, 0x32, "<BBb2H")

    def bus_servo_read_vin_limit(self, servo_id):
        """Read bus servo voltage limits."""
        return self.bus_servo_read_and_unpack(servo_id, 0x36, "<BBb2H")

    def bus_servo_read_torque_state(self, servo_id):
        """Read bus servo torque state."""
        return self.bus_servo_read_and_unpack(servo_id, 0x0D, "<BBbb")

    def enable_reception(self, enable=True):
        """Enable or disable data reception."""
        self.enable_recv = enable

    def recv_task(self):
        """Background task for receiving serial data."""
        while True:
            try:
                if self.enable_recv and self.port is not None:
                    recv_data = self.port.read()
                    if not recv_data:
                        raise SerialException('no data')
                    if recv_data:
                        for dat in recv_data:
                            if self.state == PacketControllerState.PACKET_CONTROLLER_STATE_STARTBYTE1:
                                if dat == 0xAA:
                                    self.state = PacketControllerState.PACKET_CONTROLLER_STATE_STARTBYTE2
                                continue
                            elif self.state == PacketControllerState.PACKET_CONTROLLER_STATE_STARTBYTE2:
                                if dat == 0x55:
                                    self.state = PacketControllerState.PACKET_CONTROLLER_STATE_FUNCTION
                                else:
                                    self.state = PacketControllerState.PACKET_CONTROLLER_STATE_STARTBYTE1
                                continue
                            elif self.state == PacketControllerState.PACKET_CONTROLLER_STATE_FUNCTION:
                                if dat < int(PacketFunction.PACKET_FUNC_NONE):
                                    self.frame = [dat, 0]
                                    self.state = PacketControllerState.PACKET_CONTROLLER_STATE_LENGTH
                                else:
                                    self.frame = []
                                    self.state = PacketControllerState.PACKET_CONTROLLER_STATE_STARTBYTE1
                                continue
                            elif self.state == PacketControllerState.PACKET_CONTROLLER_STATE_LENGTH:
                                self.frame[1] = dat
                                self.recv_count = 0
                                if dat == 0:
                                    self.state = PacketControllerState.PACKET_CONTROLLER_STATE_CHECKSUM
                                else:
                                    self.state = PacketControllerState.PACKET_CONTROLLER_STATE_DATA
                                continue
                            elif self.state == PacketControllerState.PACKET_CONTROLLER_STATE_DATA:
                                self.frame.append(dat)
                                self.recv_count += 1
                                if self.recv_count >= self.frame[1]:
                                    self.state = PacketControllerState.PACKET_CONTROLLER_STATE_CHECKSUM
                                continue
                            elif self.state == PacketControllerState.PACKET_CONTROLLER_STATE_CHECKSUM:
                                crc8 = checksum_crc8(bytes(self.frame))
                                if crc8 == dat:
                                    func = PacketFunction(self.frame[0])
                                    data = bytes(self.frame[2:])
                                    if func in self.parsers:
                                        self.parsers[func](data)
                                self.state = PacketControllerState.PACKET_CONTROLLER_STATE_STARTBYTE1
                                continue
                else:
                    time.sleep(0.01)
            except SerialException as e:
                try:
                    if self.port:
                        self.port.close()
                except:
                    pass
                time.sleep(1)
                try:
                    if self.port:
                        self.port.open()
                except Exception as e2:
                    print('Failed to reopen serial:', e2)
                    time.sleep(5)
        
        if self.port:
            self.port.close()


if __name__ == "__main__":
    board = Board()
    board.enable_reception()
    print("Board SDK Test - Running in", "simulation" if board.simulation_mode else "hardware", "mode")
    
    while True:
        try:
            # Test IMU reading
            imu = board.get_imu()
            if imu is not None:
                print(f"IMU: ax={imu[0]:.2f}, ay={imu[1]:.2f}, az={imu[2]:.2f}, "
                      f"gx={imu[3]:.2f}, gy={imu[4]:.2f}, gz={imu[5]:.2f}")
            
            # Test battery reading
            battery = board.get_battery()
            if battery is not None:
                print(f"Battery: {battery}mV ({battery/1000:.2f}V)")
            
            time.sleep(1)
        except KeyboardInterrupt:
            break
