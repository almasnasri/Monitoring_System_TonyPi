import serial
import os
import time
import subprocess
import hashlib

# --- CONFIG ---
# Set audio output to headphone jack/HDMI (standard Pi behavior)
os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"

# DIRECTORY SETUP
# 1. Get the directory where THIS file (voice_module.py) is located (e.g., .../FYP_Robot/modules)
CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Go ONE LEVEL UP to find the main robot folder (e.g., .../FYP_Robot)
# This is crucial because 'piper_venv' and 'piper_models' are in the main folder, not inside 'modules'
BASE_DIR = os.path.dirname(CURRENT_FILE_DIR)

# 3. Point to the Virtual Environment python we created
VENV_PYTHON = os.path.join(BASE_DIR, "piper_venv/bin/python3")

# 4. Point to the HIGH quality model we downloaded
PIPER_MODEL = os.path.join(BASE_DIR, "piper_models/en_US-ryan-high.onnx")

CACHE_DIR = os.path.join(BASE_DIR, "sounds_cache")

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR, exist_ok=True)

# --- COMMANDS (From your Excel Sheet) ---
HEX_COMMANDS = {
    b'\xaa\x55\x01\x00\xfb': 'Greeting',
    b'\xaa\x55\x02\x00\xfb': 'Sleep',
    b'\xaa\x55\x03\x00\xfb': 'Wake Up',
    b'\xaa\x55\x00\x01\xfb': 'Forward',
    b'\xaa\x55\x00\x02\xfb': 'Back',
    b'\xaa\x55\x00\x03\xfb': 'Turn Left',
    b'\xaa\x55\x00\x04\xfb': 'Turn Right',
    b'\xaa\x55\x00\x05\xfb': 'Peeling',
    b'\xaa\x55\x00\x06\xfb': 'Flip',
    b'\xaa\x55\x00\x07\xfb': 'Insert Label',
    b'\xaa\x55\x00\x08\xfb': 'Pick Up',
    b'\xaa\x55\x00\x09\xfb': 'Transport',
    b'\xaa\x55\x00\x0a\xfb': 'Stop'
}

def speak(text):
    if not text: return
    print(f"[Tony Speaking]: {text}")
    
    # 1. Try Piper (Ryan High Quality)
    try:
        # Create a unique filename for this sentence
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        wav_path = os.path.join(CACHE_DIR, f"{text_hash}.wav")
        
        # Only generate if it doesn't exist yet
        if not os.path.exists(wav_path):
            clean_text = text.replace('"', '').replace("'", "")
            
            # We call Piper using the module syntax via our venv python
            # This is safer than calling a binary directly
            cmd = f'echo "{clean_text}" | {VENV_PYTHON} -m piper --model {PIPER_MODEL} --output_file {wav_path}'
            subprocess.run(cmd, shell=True, check=True, stderr=subprocess.DEVNULL)
        
        # Play the file
        if os.path.exists(wav_path):
            # Try hardware direct playback first, then standard aplay
            os.system(f"aplay -q {wav_path}")
            return
            
    except Exception as e:
        print(f"[VOICE WARN] Piper failed, falling back to espeak. Error: {e}")

    # 2. Fallback (Robot Voice - Espeak)
    os.system(f'espeak -s150 "{text}" &')

class WonderEcho:
    def __init__(self):
        self.ser = None
        # Note: Added /dev/ttyAMA0 as it is common on Pi
        ports = ['/dev/ttyUSB0', '/dev/ttyAMA0', '/dev/serial0']
        
        for port in ports:
            if os.path.exists(port):
                try:
                    # FIX: Changed baud rate from 9600 to 115200 to match official robot code
                    self.ser = serial.Serial(port, 115200, timeout=0.02)
                    print(f"[VOICE] Connected to Voice Module at {port}")
                    break
                except Exception as e:
                    print(f"[VOICE] Failed to connect to {port}: {e}")

    def get_command(self):
        if not self.ser: return None
        try:
            # The official code reads 5 bytes at once usually
            if self.ser.in_waiting > 0:
                # Read 5 bytes (header + data + footer)
                data = self.ser.read(5)
                if data in HEX_COMMANDS:
                    return HEX_COMMANDS[data]
        except: 
            pass
        return None