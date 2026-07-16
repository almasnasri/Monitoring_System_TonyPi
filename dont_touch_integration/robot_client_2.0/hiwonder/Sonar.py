#!/usr/bin/env python3
# encoding: utf-8
"""
HiWonder I2C Ultrasonic Sensor Driver
Provides distance measurement using the ultrasonic sensor connected via I2C.
Also supports RGB LED control on the sensor module.
"""

import sys
import time

# Try to import smbus2 for I2C communication
try:
    from smbus2 import SMBus, i2c_msg
    I2C_AVAILABLE = True
except ImportError:
    I2C_AVAILABLE = False
    print("Warning: smbus2 not available. Ultrasonic sensor will run in simulation mode.")


class Sonar:
    """
    Ultrasonic distance sensor with RGB LED support.
    Uses I2C communication to read distance and control LEDs.
    """
    
    # Register addresses
    __units = {"mm": 0, "cm": 1}
    __dist_reg = 0

    __RGB_MODE = 2
    __RGB1_R = 3
    __RGB1_G = 4
    __RGB1_B = 5
    __RGB2_R = 6
    __RGB2_G = 7
    __RGB2_B = 8

    __RGB1_R_BREATHING_CYCLE = 9
    __RGB1_G_BREATHING_CYCLE = 10
    __RGB1_B_BREATHING_CYCLE = 11
    __RGB2_R_BREATHING_CYCLE = 12
    __RGB2_G_BREATHING_CYCLE = 13
    __RGB2_B_BREATHING_CYCLE = 14

    def __init__(self, i2c_bus=1, i2c_addr=0x77):
        """
        Initialize the ultrasonic sensor.
        
        Args:
            i2c_bus: I2C bus number (default: 1 for Raspberry Pi)
            i2c_addr: I2C address of the sensor (default: 0x77)
        """
        self.i2c_addr = i2c_addr
        self.i2c = i2c_bus
        self.simulation_mode = not I2C_AVAILABLE
        
        # RGB state
        self.R1 = 0
        self.G1 = 0
        self.B1 = 0
        self.R2 = 0
        self.G2 = 0
        self.B2 = 0
        self.RGBMode = 0

    def __getattr(self, attr):
        if attr in self.__units:
            return self.__units[attr]
        if attr == "Distance":
            return self.getDistance()
        else:
            raise AttributeError('Unknown attribute: %s' % attr)
    
    def setRGBMode(self, mode):
        """
        Set RGB LED mode.
        
        Args:
            mode: 0 for color mode, 1 for breathing mode
        """
        if self.simulation_mode:
            self.RGBMode = mode
            return
            
        try:
            with SMBus(self.i2c) as bus:
                bus.write_byte_data(self.i2c_addr, self.__RGB_MODE, mode)
        except Exception as e:
            print(f'Sensor not connected: {e}')
    
    def setRGB(self, index, rgb):
        """
        Set RGB LED color.
        
        Args:
            index: 1 for left LED, 0 for right LED
            rgb: Tuple of (r, g, b) values (0-255 each)
        """
        if self.simulation_mode:
            if index == 1:
                self.R1, self.G1, self.B1 = rgb
            else:
                self.R2, self.G2, self.B2 = rgb
            return
            
        start_reg = 3 if index == 1 else 6
        try:
            with SMBus(self.i2c) as bus:
                bus.write_byte_data(self.i2c_addr, start_reg, rgb[0])
                bus.write_byte_data(self.i2c_addr, start_reg + 1, rgb[1])
                bus.write_byte_data(self.i2c_addr, start_reg + 2, rgb[2])
        except Exception as e:
            print(f'Sensor not connected: {e}')
    
    def setBreathCycle(self, index, rgb, cycle):
        """
        Set breathing light mode cycle.
        
        Args:
            index: 1 for left LED, 0 for right LED
            rgb: Color channel (0=R, 1=G, 2=B)
            cycle: Color change cycle in milliseconds
        """
        if self.simulation_mode:
            return
            
        start_reg = 9 if index == 1 else 12
        cycle = int(cycle / 100)
        try:
            with SMBus(self.i2c) as bus:
                bus.write_byte_data(self.i2c_addr, start_reg + rgb, cycle)
        except Exception as e:
            print(f'Sensor not connected: {e}')

    def startSymphony(self):
        """Start a colorful breathing light pattern."""
        self.setRGBMode(1)
        self.setBreathCycle(1, 0, 2000)
        self.setBreathCycle(1, 1, 3300)
        self.setBreathCycle(1, 2, 4700)
        self.setBreathCycle(0, 0, 4600)
        self.setBreathCycle(0, 1, 2000)
        self.setBreathCycle(0, 2, 3400)

    def getDistance(self):
        """
        Get distance measurement from the ultrasonic sensor.
        
        Returns:
            int: Distance in millimeters (max 5000mm = 5m)
                 Returns 99999 if sensor is not connected or error occurs
        """
        if self.simulation_mode:
            # Simulate distance reading
            import random
            return random.randint(50, 2000)  # 5cm to 2m
            
        dist = 99999
        try:
            with SMBus(self.i2c) as bus:
                msg = i2c_msg.write(self.i2c_addr, [0])
                bus.i2c_rdwr(msg)
                read = i2c_msg.read(self.i2c_addr, 2)
                bus.i2c_rdwr(read)
                dist = int.from_bytes(bytes(list(read)), byteorder='little', signed=False)
                if dist > 5000:
                    dist = 5000
        except Exception as e:
            print(f'Sensor not connected: {e}')
        return dist
    
    def getDistanceCm(self):
        """
        Get distance in centimeters.
        
        Returns:
            float: Distance in centimeters
        """
        dist_mm = self.getDistance()
        if dist_mm == 99999:
            return None
        return dist_mm / 10.0


if __name__ == '__main__':
    print("Ultrasonic Sensor Test")
    s = Sonar()
    
    if not s.simulation_mode:
        # Set up RGB LEDs
        s.setRGBMode(0)
        s.setRGB(1, (35, 205, 55))
        s.setRGB(0, (235, 205, 55))
        s.startSymphony()
    
    print("Reading distance...")
    while True:
        dist = s.getDistance()
        if dist != 99999:
            print(f"Distance: {dist}mm ({dist/10:.1f}cm)")
        else:
            print("Sensor error or not connected")
            break
        time.sleep(0.5)
