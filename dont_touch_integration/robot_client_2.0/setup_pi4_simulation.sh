#!/bin/bash
# Raspberry Pi 4 Simulation Setup Script
# This script sets up the robot client to run in simulation mode on a Pi 4

set -e  # Exit on error

echo "=========================================="
echo "Raspberry Pi 4 Simulation Setup"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running on Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo -e "${YELLOW}Warning: This doesn't appear to be a Raspberry Pi${NC}"
    echo "The script will continue anyway..."
fi

# Get current directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "Current directory: $SCRIPT_DIR"
echo ""

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 not found${NC}"
    echo "Please install Python 3 first:"
    echo "  sudo apt-get update"
    echo "  sudo apt-get install python3 python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}Found: $PYTHON_VERSION${NC}"

# Check pip3
if ! command -v pip3 &> /dev/null; then
    echo -e "${YELLOW}pip3 not found. Installing...${NC}"
    sudo apt-get update
    sudo apt-get install -y python3-pip
fi

echo -e "${GREEN}Found: pip3 $(pip3 --version)${NC}"
echo ""

# Install dependencies
echo "Installing Python dependencies for simulation mode..."
echo ""

# Core dependencies (required)
pip3 install --user paho-mqtt psutil

# Check if installation was successful
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Dependencies installed successfully${NC}"
else
    echo -e "${RED}✗ Failed to install dependencies${NC}"
    echo "Trying with sudo..."
    sudo pip3 install paho-mqtt psutil
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "To run the robot client in simulation mode:"
echo ""
echo "  python3 tonypi_client.py --broker YOUR_BROKER_IP"
echo ""
echo "Example:"
echo "  python3 tonypi_client.py --broker 192.168.1.100"
echo ""
echo "Or with custom robot ID:"
echo "  python3 tonypi_client.py --broker 192.168.1.100 --robot-id tonypi_pi4_sim"
echo ""
echo "The client will automatically run in simulation mode"
echo "since no hardware is detected."
echo ""
echo "Press Ctrl+C to stop the client when running."
echo ""
