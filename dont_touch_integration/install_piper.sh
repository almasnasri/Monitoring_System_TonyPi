#!/bin/bash

# Stop the script if any command fails
set -e

echo "--- Starting Clean Install of Piper & Ryan Model ---"

# 1. Install System Dependencies (Required for Piper)
# Note: 'sudo' is used here. You may need to enter your password.
echo "[1/5] Installing system dependencies (espeak-ng)..."
sudo apt-get update && sudo apt-get install -y python3-venv espeak-ng

# 2. Set up a fresh Python Virtual Environment
# This avoids 'invalid syntax' or conflicts with other python projects
echo "[2/5] Setting up Python virtual environment..."
# Remove old venv if it exists to ensure a clean reinstall
rm -rf piper_venv
python3 -m venv piper_venv
source piper_venv/bin/activate

# 3. Install Piper TTS via pip
echo "[3/5] Installing piper-tts..."
pip install --upgrade pip
pip install piper-tts

# 4. Create Directory and Download Ryan Voice Model
echo "[4/5] Downloading Ryan (High Quality) voice model..."
mkdir -p piper_models
cd piper_models

# Download the ONNX model file
wget -O en_US-ryan-high.onnx "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/high/en_US-ryan-high.onnx?download=true"

# Download the JSON config file
wget -O en_US-ryan-high.onnx.json "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/high/en_US-ryan-high.onnx.json?download=true"

cd ..

# 5. Verify the installation
echo "[5/5] Verifying installation..."
echo "Generating test audio..."
echo "Piper is installed and Ryan is ready." | piper \
  --model piper_models/en_US-ryan-high.onnx \
  --output_file test_ryan.wav

echo "---------------------------------------------------"
echo "✅ SUCCESS! Piper and Ryan model installed."
echo "   - Virtual Env: ./piper_venv"
echo "   - Model Path:  ./piper_models/en_US-ryan-high.onnx"
echo "   - Test Audio:  ./test_ryan.wav"
echo ""
echo "To use it later, run:"
echo "   source piper_venv/bin/activate"
echo "   echo 'Hello' | piper --model piper_models/en_US-ryan-high.onnx --output_file output.wav"
echo "---------------------------------------------------"