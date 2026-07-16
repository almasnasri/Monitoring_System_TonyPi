#!/usr/bin/env python3
# encoding: utf-8
"""
High-level Controller for TonyPi servos and sensors.
Provides easy-to-use methods for reading servo data (position, temperature, voltage)
and controlling servo movements.
"""

import time
from . import ros_robot_controller_sdk as rrc

# Default board instance (can be overridden)
board = rrc.Board()


class Controller:
    """
    High-level controller for TonyPi robot.
    Wraps the low-level Board class with easier-to-use methods.
    """
    
    def __init__(self, board_instance=None, time_out=50):
        """
        Initialize the controller.
        
        Args:
            board_instance: Optional Board instance. If None, creates a new one.
            time_out: Timeout for servo read operations (number of retries)
        """
        self.board = board_instance if board_instance else board
        self.time_out = time_out

    def get_bus_servo_temp_limit(self, servo_id):
        """
        Get bus servo temperature limit.
        
        Args:
            servo_id: Servo ID (1-6 for TonyPi)
            
        Returns:
            int: Temperature limit in Celsius, or None if read fails
        """
        count = 0
        while True:
            data = self.board.bus_servo_read_temp_limit(servo_id)
            count += 1
            if data is not None:
                return data[0]
            if count > self.time_out:
                return None
            time.sleep(0.01)

    def get_bus_servo_angle_limit(self, servo_id):
        """
        Get bus servo angle limits.
        
        Args:
            servo_id: Servo ID
            
        Returns:
            tuple: (min_angle, max_angle) or None if read fails
        """
        count = 0
        while True:
            data = self.board.bus_servo_read_angle_limit(servo_id)
            count += 1
            if data is not None:
                return data[0]
            if count > self.time_out:
                return None
            time.sleep(0.01)

    def get_bus_servo_vin_limit(self, servo_id):
        """
        Get bus servo voltage limits.
        
        Args:
            servo_id: Servo ID
            
        Returns:
            tuple: (min_voltage, max_voltage) in mV, or None if read fails
        """
        count = 0
        while True:
            data = self.board.bus_servo_read_vin_limit(servo_id)
            count += 1
            if data is not None:
                return data[0]
            if count > self.time_out:
                return None
            time.sleep(0.01)

    def get_bus_servo_id(self):
        """
        Get bus servo ID.
        
        Returns:
            int: Servo ID, or None if read fails
        """
        count = 0
        while True:
            data = self.board.bus_servo_read_id()
            count += 1
            if data is not None:
                return data[0]
            if count > self.time_out:
                return None
            time.sleep(0.01)

    def get_bus_servo_pulse(self, servo_id):
        """
        Get bus servo position (pulse value).
        
        Args:
            servo_id: Servo ID
            
        Returns:
            int: Servo position as pulse value (0-1000), or None if read fails
        """
        count = 0
        while True:
            data = self.board.bus_servo_read_position(servo_id)
            count += 1
            if data is not None:
                return data[0]
            if count > self.time_out:
                return None
            time.sleep(0.01)

    def get_bus_servo_vin(self, servo_id):
        """
        Get bus servo voltage.
        
        Args:
            servo_id: Servo ID
            
        Returns:
            int: Servo voltage in millivolts, or None if read fails
        """
        count = 0
        while True:
            data = self.board.bus_servo_read_vin(servo_id)
            count += 1
            if data is not None:
                return data[0]
            if count > self.time_out:
                return None
            time.sleep(0.01)
    
    def get_bus_servo_voltage(self, servo_id):
        """Alias for get_bus_servo_vin."""
        return self.get_bus_servo_vin(servo_id)

    def get_bus_servo_temp(self, servo_id):
        """
        Get bus servo temperature.
        
        Args:
            servo_id: Servo ID
            
        Returns:
            int: Servo temperature in Celsius, or None if read fails
        """
        count = 0
        while True:
            data = self.board.bus_servo_read_temp(servo_id)
            count += 1
            if data is not None:
                return data[0]
            if count > self.time_out:
                return None
            time.sleep(0.01)

    def get_bus_servo_deviation(self, servo_id):
        """
        Get bus servo deviation/offset.
        
        Args:
            servo_id: Servo ID
            
        Returns:
            int: Servo offset value, or None if read fails
        """
        count = 0
        while True:
            data = self.board.bus_servo_read_offset(servo_id)
            count += 1
            if data is not None:
                return data[0]
            if count > self.time_out:
                return None
            time.sleep(0.01)

    def set_bus_servo_pulse(self, servo_id, pulse, use_time):
        """
        Set bus servo position.
        
        Args:
            servo_id: Servo ID
            pulse: Target position (0-1000)
            use_time: Movement duration in milliseconds
        """
        self.board.bus_servo_set_position(use_time / 1000, [[servo_id, pulse]])

    def set_pwm_servo_pulse(self, servo_id, pulse, use_time):
        """
        Set PWM servo position.
        
        Args:
            servo_id: PWM servo ID (1-4)
            pulse: Target position (500-2500 typically)
            use_time: Movement duration in milliseconds
        """
        self.board.pwm_servo_set_position(use_time / 1000, [[servo_id, pulse]])

    def set_bus_servo_id(self, servo_id_now, servo_id_new):
        """
        Change bus servo ID.
        
        Args:
            servo_id_now: Current servo ID
            servo_id_new: New servo ID
        """
        self.board.bus_servo_set_id(servo_id_now, servo_id_new)

    def set_bus_servo_deviation(self, servo_id, deviation):
        """
        Set bus servo deviation/offset.
        
        Args:
            servo_id: Servo ID
            deviation: Offset value
        """
        self.board.bus_servo_set_offset(servo_id, deviation)

    def set_bus_servo_temp_limit(self, servo_id, temp_limit):
        """
        Set bus servo temperature limit.
        
        Args:
            servo_id: Servo ID
            temp_limit: Maximum temperature in Celsius
        """
        self.board.bus_servo_set_temp_limit(servo_id, temp_limit)

    def set_bus_servo_angle_limit(self, servo_id, angle_limit):
        """
        Set bus servo angle limits.
        
        Args:
            servo_id: Servo ID
            angle_limit: Tuple of (min_angle, max_angle)
        """
        self.board.bus_servo_set_angle_limit(servo_id, angle_limit)

    def set_bus_servo_vin_limit(self, servo_id, vin_limit):
        """
        Set bus servo voltage limits.
        
        Args:
            servo_id: Servo ID
            vin_limit: Tuple of (min_voltage, max_voltage) in mV
        """
        self.board.bus_servo_set_vin_limit(servo_id, vin_limit)

    def save_bus_servo_deviation(self, servo_id):
        """
        Save servo deviation to EEPROM.
        
        Args:
            servo_id: Servo ID
        """
        self.board.bus_servo_save_offset(servo_id)

    def unload_bus_servo(self, servo_id):
        """
        Disable servo torque (servo goes limp).
        
        Args:
            servo_id: Servo ID
        """
        self.board.bus_servo_enable_torque(servo_id, 1)

    def set_buzzer(self, freq, on_time, off_time, repeat=1):
        """
        Control the buzzer.
        
        Args:
            freq: Sound frequency in Hz
            on_time: Time buzzer is on (seconds)
            off_time: Time buzzer is off (seconds)
            repeat: Number of repetitions
        """
        self.board.set_buzzer(freq, on_time, off_time, repeat=repeat)

    def get_imu(self):
        """
        Get IMU data (accelerometer and gyroscope).
        
        Returns:
            tuple: (ax, ay, az, gx, gy, gz) or None if read fails
                   ax, ay, az: Accelerometer data in m/s^2
                   gx, gy, gz: Gyroscope data in deg/s
        """
        count = 0
        while True:
            data = self.board.get_imu()
            count += 1
            if data is not None:
                return data
            if count > self.time_out:
                return None
            time.sleep(0.01)

    def enable_recv(self):
        """Enable data reception from the board."""
        self.board.enable_reception(False)
        time.sleep(1)
        self.board.enable_reception(True)
        time.sleep(1)


if __name__ == "__main__":
    print("Controller Test")
    ctl = Controller()
    ctl.board.enable_reception(True)
    
    # Test reading servo data
    for servo_id in range(1, 7):
        print(f"\nServo {servo_id}:")
        
        pulse = ctl.get_bus_servo_pulse(servo_id)
        print(f"  Position: {pulse}")
        
        temp = ctl.get_bus_servo_temp(servo_id)
        print(f"  Temperature: {temp}C")
        
        vin = ctl.get_bus_servo_vin(servo_id)
        print(f"  Voltage: {vin}mV")
    
    # Test IMU
    imu = ctl.get_imu()
    if imu:
        print(f"\nIMU: ax={imu[0]:.2f}, ay={imu[1]:.2f}, az={imu[2]:.2f}, "
              f"gx={imu[3]:.2f}, gy={imu[4]:.2f}, gz={imu[5]:.2f}")
