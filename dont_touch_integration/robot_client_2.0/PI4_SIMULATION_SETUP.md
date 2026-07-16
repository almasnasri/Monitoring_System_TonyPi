# Raspberry Pi 4 Simulation Setup Guide

This guide will help you set up your Raspberry Pi 4 (without sensors/servos) to simulate a robot connection to your monitoring system.

## Overview

The `tonypi_client.py` automatically detects when hardware is unavailable and runs in **simulation mode**. This means you can run it on any Raspberry Pi 4 without the TonyPi robot hardware, and it will generate simulated sensor and servo data.

## Prerequisites

- Raspberry Pi 4 with Raspberry Pi OS installed
- Network connection to reach your MQTT broker (monitoring system)
- Python 3.7+ installed

## Step 1: Transfer Files to Pi 4

### Option A: Using SCP (from your Windows PC)

```powershell
# Replace 192.168.1.XXX with your Pi 4's IP address
# Replace pi with your Pi username if different
scp -r C:\Users\aiman\Projects\Monitoring_System_TonyPi\robot_client pi@192.168.1.XXX:/home/pi/
```

### Option B: Using Git (if Pi 4 has git)

```bash
# On Pi 4
cd ~
git clone <your-repo-url>
cd Monitoring_System_TonyPi/robot_client
```

### Option C: Using USB Drive

1. Copy the `robot_client` folder to a USB drive
2. Plug USB into Pi 4
3. Copy files: `cp -r /media/pi/USB_NAME/robot_client ~/`

## Step 2: SSH into Pi 4

```bash
# From your Windows PC (PowerShell or Git Bash)
ssh pi@192.168.1.XXX

# Or use PuTTY on Windows
# Host: 192.168.1.XXX
# Username: pi
# Password: (your Pi password)
```

## Step 3: Install Python Dependencies

On the Pi 4, run:

```bash
# Navigate to robot_client folder
cd ~/robot_client

# Install minimal dependencies for simulation mode
pip3 install paho-mqtt psutil

# If pip3 is not found, install it first:
# sudo apt-get update
# sudo apt-get install python3-pip
```

**Note:** For simulation mode, you only need `paho-mqtt` and `psutil`. The hardware-specific libraries (pyserial, smbus2) are not required and will fail gracefully.

## Step 4: Find Your MQTT Broker IP

You need to know the IP address of your monitoring system's MQTT broker:

- If running on your PC: Check your PC's IP address (`ipconfig` on Windows)
- If running on a server: Use that server's IP address
- Default MQTT port: `1883`

**Example:** If your monitoring system is at `192.168.1.100`, that's your broker IP.

## Step 5: Run the Robot Client in Simulation Mode

```bash
# Basic usage - connects to MQTT broker
python3 tonypi_client.py --broker 192.168.1.100

# With custom robot ID
python3 tonypi_client.py --broker 192.168.1.100 --robot-id tonypi_pi4_sim

# With custom port (if MQTT is not on 1883)
python3 tonypi_client.py --broker 192.168.1.100 --port 1883
```

**Expected Output:**
```
============================================================
   TONYPI ROBOT CLIENT - MONITORING TELEMETRY
============================================================
   Robot ID: tonypi_raspberrypi
   MQTT Broker: 192.168.1.100:1883
   Hardware Mode: False
============================================================

📡 Sending initial telemetry...
✅ Initial telemetry sent!

============================================================
✅ ROBOT CLIENT RUNNING - Sending telemetry data
============================================================
Data being sent:
  • Sensors:  every 2 seconds (IMU, temp, light, ultrasonic)
  • Servos:   every 3 seconds (position, temp, voltage)
  • Status:   every 10 seconds (CPU, memory, disk, uptime)
  • Battery:  every 30 seconds
  • Location: every 5 seconds
  • Logs:     real-time
============================================================
```

## Step 6: Verify Connection

1. Check the monitoring system dashboard - you should see your robot appear
2. The robot will show as "online" with simulated data
3. All sensor readings, servo data, and system metrics will be simulated

## Step 7: Run as a Service (Optional)

To run the robot client automatically on boot:

```bash
# Copy the service file
sudo cp ~/robot_client/tonypi-robot.service /etc/systemd/system/

# Edit the service file to set your broker IP
sudo nano /etc/systemd/system/tonypi-robot.service

# Update the ExecStart line with your broker IP:
# ExecStart=/usr/bin/python3 /home/pi/robot_client/tonypi_client.py --broker YOUR_BROKER_IP

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable tonypi-robot.service
sudo systemctl start tonypi-robot.service

# Check status
sudo systemctl status tonypi-robot.service
```

## What Gets Simulated?

When running in simulation mode, the client generates:

- **Sensors:**
  - Accelerometer (X, Y, Z) - random values
  - Gyroscope (X, Y, Z) - random values
  - Ultrasonic distance - random 5-200 cm
  - CPU temperature - actual Pi 4 temperature
  - Light sensor - simulated light levels

- **Servos (6 servos):**
  - Position - random angles
  - Temperature - simulated 40-55°C
  - Voltage - simulated 4.8-5.2V

- **System Metrics (Real Pi 4 data):**
  - CPU usage - actual Pi 4 CPU
  - Memory usage - actual Pi 4 memory
  - Disk usage - actual Pi 4 disk
  - Temperature - actual Pi 4 CPU temperature
  - Uptime - actual Pi 4 uptime

- **Battery:**
  - Simulated battery level (drains slowly)
  - Simulated voltage

- **Location:**
  - Simulated X, Y, Z coordinates

## Troubleshooting

### Connection Issues

```bash
# Test MQTT broker connectivity
ping YOUR_BROKER_IP

# Test MQTT port
telnet YOUR_BROKER_IP 1883
# (Press Ctrl+] then type 'quit' to exit)
```

### Python Import Errors

```bash
# Make sure you're using Python 3
python3 --version

# Reinstall dependencies
pip3 install --upgrade paho-mqtt psutil
```

### Permission Errors

```bash
# If GPIO errors appear (they're harmless in simulation)
# The client will automatically use simulated GPIO
```

### Check Logs

```bash
# View service logs (if running as service)
sudo journalctl -u tonypi-robot.service -f

# Or run directly to see output
python3 tonypi_client.py --broker YOUR_BROKER_IP
```

## Environment Variables (Alternative)

You can also set environment variables instead of command-line arguments:

```bash
export MQTT_BROKER=192.168.1.100
export MQTT_PORT=1883
export ROBOT_ID=tonypi_pi4_sim

python3 tonypi_client.py
```

## Quick Test Script

Create a test script `test_connection.sh`:

```bash
#!/bin/bash
BROKER_IP="192.168.1.100"  # Change this to your broker IP
ROBOT_ID="tonypi_pi4_test"

echo "Testing connection to $BROKER_IP..."
python3 tonypi_client.py --broker $BROKER_IP --robot-id $ROBOT_ID
```

Make it executable:
```bash
chmod +x test_connection.sh
./test_connection.sh
```

## Next Steps

1. Verify the robot appears in your monitoring system dashboard
2. Test sending commands from the dashboard (move, stop, head_nod, etc.)
3. Monitor the simulated sensor data in real-time
4. Check that all features work (sensors, servos, battery, location, logs)

## Notes

- The simulation mode is **identical** to the real hardware mode in terms of data format
- All MQTT topics and message formats are the same
- The monitoring system cannot tell the difference between simulated and real data
- This is perfect for testing and development without the actual robot hardware
