import os
import json
import requests
import base64
import cv2
import datetime
from dotenv import load_dotenv

# --- CONFIGURATION ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
env_path = os.path.join(project_root, ".env")

load_dotenv(env_path)
API_KEY = os.getenv("GEMINI_API_KEY")

# Direct URL to Gemini 1.5 Flash (Fastest model)
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"

FALLBACKS = {
    "greeting": "Hello boss. Systems online.",
    "wake_up": "Yes boss?",
    "pick_up_cardboard": "Target locked.",
    "stop": "Emergency stop.",
    "obstacle": "Object detected."
}

def send_to_gemini(payload):
    """ Sends raw JSON to Google. Returns None if internet fails. """
    if not API_KEY:
        print("[AI DEBUG] No API Key found.")
        return None
    
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=8)
        if response.status_code == 200:
            result = response.json()
            try:
                return result['candidates'][0]['content']['parts'][0]['text'].strip()
            except (KeyError, IndexError):
                return None
        else:
            print(f"[AI DEBUG] Error {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"[AI DEBUG] Connection failed: {e}")
        return None

def get_dynamic_response(trigger_event):
    """ Text-Only Request """
    prompt = (f"You are a futuristic robot named Tony. User command: '{trigger_event}'. "
              f"Generate a short, cool 1-sentence response (max 10 words).")
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    reply = send_to_gemini(payload)
    return reply if reply else FALLBACKS.get(trigger_event, "Command received.")

def analyze_obstacle(cv2_frame):
    """ Vision Request """
    try:
        _, buffer = cv2.imencode('.jpg', cv2_frame)
        img_b64 = base64.b64encode(buffer).decode('utf-8')
        
        prompt = "I am a robot stopped by an obstacle. Look at this image. What is blocking me? (1 sentence)"
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        reply = send_to_gemini(payload)
        return reply if reply else "Visual systems offline."
    except: return "Cannot identify obstacle."

def generate_smart_greeting(cv2_frame):
    """ Smart Greeting Request """
    try:
        hour = datetime.datetime.now().hour
        time_msg = "Good morning" if 5 <= hour < 12 else "Good afternoon" if 12 <= hour < 18 else "Good evening"

        _, buffer = cv2.imencode('.jpg', cv2_frame)
        img_b64 = base64.b64encode(buffer).decode('utf-8')

        prompt = (f"You are a robot named Tony. It is {time_msg}. User just said hello. "
                  f"Look at this image. Generate a cool 1-sentence greeting describing what you see.")

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        reply = send_to_gemini(payload)
        return reply if reply else f"{time_msg} boss. Ready."
    except: return "Hello boss. Systems ready."