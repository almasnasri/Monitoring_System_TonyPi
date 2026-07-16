#!/bin/bash
# Quick Start Script for Raspberry Pi 4 Simulation
# Usage: ./quick_start_pi4.sh [BROKER_IP] [ROBOT_ID]

# Default values
BROKER_IP="${1:-localhost}"
ROBOT_ID="${2:-tonypi_pi4_sim}"

echo "=========================================="
echo "TonyPi Robot Client - Pi 4 Simulation"
echo "=========================================="
echo ""
echo "Broker IP: $BROKER_IP"
echo "Robot ID:  $ROBOT_ID"
echo ""
echo "Starting in simulation mode..."
echo "Press Ctrl+C to stop"
echo ""

# Check if dependencies are installed
if ! python3 -c "import paho.mqtt.client" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install --user paho-mqtt psutil
fi

# Run the client
python3 tonypi_client.py --broker "$BROKER_IP" --robot-id "$ROBOT_ID"
