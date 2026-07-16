#!/usr/bin/python3
import time
import sys
import os

# --- IMPORT FIX ---
# This tells Python to look inside the 'modules' folder
try:
    from modules import voice_module
except ImportError:
    # Fallback: simple import if you move the file back to the main folder later
    import voice_module
# ------------------

# Define the responses for the debug test
RESPONSES = {
    'Greeting': "Welcome. I am online.",
    'Sleep': "Entering sleep mode. Goodbye.",
    'Wake Up': "System ready. What is your command?",
    'Forward': "Moving forward.",
    'Back': "Retreating.",
    'Turn Left': "Turning left.",
    'Turn Right': "Turning right.",
    'Peeling': "Die-cut peeling sequence initiated.",
    'Flip': "Flipping sheet over.",
    'Insert Label': "Inserting label now.",
    'Pick Up': "Gripper activated. Picking up object.",
    'Transport': "Transporting object to destination.",
    'Stop': "Emergency stop triggered."
}

def main():
    print("------------------------------------------------")
    print("       VOICE COMMAND DEBUGGER (RYAN MODEL)      ")
    print("------------------------------------------------")
    print("1. Speak a command to the Voice Module (e.g. 'Hello Tony')")
    print("2. The script will print the HEX code received.")
    print("3. Piper will speak the response.")
    print("------------------------------------------------")

    # Initialize the serial connection
    voice = voice_module.WonderEcho()
    
    if not voice.ser:
        print("❌ ERROR: Could not find Voice Module! Check connections.")
        return

    print("✅ Listening for commands...")

    try:
        while True:
            # Check for incoming commands
            command = voice.get_command()
            
            if command:
                print(f"🎤 RECEIVED COMMAND: [{command}]")
                
                # Get the response text
                response_text = RESPONSES.get(command, "Unknown command received.")
                
                # Speak it using the Ryan model
                voice_module.speak(response_text)
                
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nExiting Debugger.")

if __name__ == "__main__":
    main()