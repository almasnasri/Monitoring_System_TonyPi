# TonyPi Robot Client

This module contains the robot client that runs on the TonyPi Raspberry Pi and communicates with the monitoring system.

## Features

- **Real Hardware Integration**: Reads actual sensor data from TonyPi hardware when available
- **Automatic Fallback**: Gracefully falls back to simulation mode when running on non-TonyPi systems
- **MQTT Communication**: Sends sensor/servo data and receives commands via MQTT
- **Camera Streaming**: MJPEG video stream server for camera feed

## Files

| File | Description |
|------|-------------|
| `tonypi_client.py` | Main robot client with MQTT communication |
| `camera_stream.py` | MJPEG camera streaming server |
| `simulator.py` | Standalone simulator for testing |
| `hiwonder/` | HiWonder SDK for TonyPi hardware |

## HiWonder SDK

The `hiwonder/` folder contains the SDK for TonyPi hardware:

| Module | Description |
|--------|-------------|
| `ros_robot_controller_sdk.py` | Serial communication with STM32 board (IMU, battery, servos) |
| `Controller.py` | High-level servo control wrapper |
| `Sonar.py` | Ultrasonic distance sensor driver |
| `ActionGroupControl.py` | Pre-recorded movement action execution |

## Installation

### On TonyPi Raspberry Pi

```bash
# Navigate to robot_client folder
cd robot_client

# Install dependencies
pip install -r requirements.txt

# The TonyPi already has the SDK at /home/pi/TonyPi/HiwonderSDK/
# The client will automatically use it
```

### On Development Machine (Simulation Mode)

```bash
# Install dependencies (serial/smbus will fail gracefully)
pip install paho-mqtt psutil pyyaml

# Run in simulation mode
python tonypi_client.py --broker <mqtt-server-ip>
```

### On Raspberry Pi 4 (Without Hardware - Simulation Mode)

Perfect for testing when you don't have the actual robot hardware! The client automatically detects no hardware and runs in simulation mode.

**Quick Setup:**
```bash
# 1. Copy robot_client folder to Pi 4
scp -r robot_client/ pi@<pi4-ip>:/home/pi/

# 2. SSH into Pi 4
ssh pi@<pi4-ip>

# 3. Install minimal dependencies
cd ~/robot_client
pip3 install -r requirements_simulation.txt

# 4. Run in simulation mode
python3 tonypi_client.py --broker <mqtt-broker-ip>
```

**Or use the quick start script:**
```bash
chmod +x quick_start_pi4.sh
./quick_start_pi4.sh <mqtt-broker-ip> [robot-id]
```

**For detailed setup instructions, see:** [`PI4_SIMULATION_SETUP.md`](PI4_SIMULATION_SETUP.md)

## Usage

### Running the Robot Client

```bash
# Connect to local MQTT broker
python tonypi_client.py

# Connect to remote MQTT broker
python tonypi_client.py --broker 192.168.1.100 --port 1883

# Specify custom robot ID
python tonypi_client.py --robot-id tonypi_001
```

### Running the Camera Server

```bash
# Start camera streaming on port 8080
python camera_stream.py

# Custom port and resolution
python camera_stream.py --port 8081 --width 1280 --height 720
```

Access the camera stream at:
- Stream: `http://<tonypi-ip>:8080/?action=stream`
- Snapshot: `http://<tonypi-ip>:8080/?action=snapshot`

## Data Published via MQTT

### Topics

| Topic | Description |
|-------|-------------|
| `tonypi/sensors/{robot_id}` | IMU and sensor readings |
| `tonypi/servos/{robot_id}` | Servo status (position, temp, voltage) |
| `tonypi/battery` | Battery level |
| `tonypi/status/{robot_id}` | Robot status |
| `tonypi/location` | Robot location |

### Sensor Data Format

```json
{
  "robot_id": "tonypi_001",
  "sensor_type": "accelerometer_x",
  "value": 0.123,
  "unit": "m/s^2",
  "timestamp": "2024-01-01T12:00:00"
}
```

### Servo Data Format

```json
{
  "robot_id": "tonypi_001",
  "servos": {
    "servo_1": {
      "id": 1,
      "name": "Left Hip",
      "position": 45.0,
      "temperature": 42.5,
      "voltage": 5.1,
      "torque_enabled": true,
      "alert_level": "normal"
    }
  },
  "servo_count": 6,
  "timestamp": "2024-01-01T12:00:00"
}
```

## Commands via MQTT

Subscribe to `tonypi/commands/{robot_id}` and send:

```json
{"type": "move", "direction": "forward", "distance": 1.0}
{"type": "stop"}
{"type": "head_nod"}
{"type": "head_shake"}
{"type": "status_request"}
{"type": "battery_request"}
```

## Available Movement Actions

| Direction | Action |
|-----------|--------|
| `forward` | Walk forward |
| `backward` | Walk backward |
| `left` | Turn left |
| `right` | Turn right |
| `stop` | Stop all movement |
| `stand` | Standing position |
| `wave` | Wave hand |
| `kick_left` | Left kick |
| `kick_right` | Right kick |

## Deployment to TonyPi

```bash
# Copy files to TonyPi
scp -r robot_client/ pi@<tonypi-ip>:/home/pi/monitoring/

# SSH to TonyPi and run
ssh pi@<tonypi-ip>
cd /home/pi/monitoring/robot_client
python tonypi_client.py --broker <server-ip>
```

## Troubleshooting

### Hardware not detected

If hardware is not detected, check:
1. Serial port `/dev/ttyAMA0` is accessible
2. I2C is enabled (`sudo raspi-config` -> Interface Options -> I2C)
3. User has permission for serial/I2C (`sudo usermod -a -G dialout,i2c $USER`)

### Camera not working

1. Check camera is connected: `ls /dev/video*`
2. Test with: `python -c "import cv2; print(cv2.VideoCapture(-1).isOpened())"`

### MQTT connection failed

1. Verify MQTT broker is running
2. Check firewall allows port 1883
3. Test with: `mosquitto_pub -h <broker> -t test -m "hello"`
