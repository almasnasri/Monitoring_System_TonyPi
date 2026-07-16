#!/bin/bash
# ============================================
# TonyPi Camera Service Setup Script
# Run this on the TonyPi to enable camera streaming on boot
# ============================================

set -e

echo "=========================================="
echo "  TonyPi Camera Service Setup"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo: sudo bash setup_camera_service.sh"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/tonypi-camera.service"

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo "ERROR: tonypi-camera.service not found in $SCRIPT_DIR"
    exit 1
fi

# Copy service file to systemd
echo "1. Installing systemd service..."
cp "$SERVICE_FILE" /etc/systemd/system/tonypi-camera.service

# Reload systemd daemon
echo "2. Reloading systemd daemon..."
systemctl daemon-reload

# Enable service to start on boot
echo "3. Enabling service to start on boot..."
systemctl enable tonypi-camera.service

# Start the service now
echo "4. Starting camera service..."
systemctl start tonypi-camera.service

# Check status
echo ""
echo "=========================================="
echo "  Service Status"
echo "=========================================="
systemctl status tonypi-camera.service --no-pager

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Camera stream URL: http://$(hostname -I | awk '{print $1}'):8080/?action=stream"
echo "Snapshot URL:      http://$(hostname -I | awk '{print $1}'):8080/?action=snapshot"
echo ""
echo "Useful commands:"
echo "  - Check status:  sudo systemctl status tonypi-camera"
echo "  - View logs:     sudo journalctl -u tonypi-camera -f"
echo "  - Stop service:  sudo systemctl stop tonypi-camera"
echo "  - Restart:       sudo systemctl restart tonypi-camera"
echo "  - Disable:       sudo systemctl disable tonypi-camera"
echo ""
