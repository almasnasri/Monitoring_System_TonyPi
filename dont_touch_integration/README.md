## TonyPi Packaging Assistant

Autonomous workflow for the Hiwonder TonyPi robot that watches a production line, listens for voice prompts, and executes choreographed actions (peeling, inserting labels, transporting stock, flipping sheets) while staying safe via a live light sensor guard. The stack combines YOLO-based vision, a serial voice command module, and locally cached Piper TTS for audible status.

---

### Key Capabilities
- **Hands-free command flow** – hardware voice module converts wake/stop/task phrases into structured commands surfaced through `WonderEcho`.
- **Real-time vision** – [modules/vision_module.py](modules/vision_module.py) wraps an Ultralytics YOLO model tuned for cardboard detection with smoothing, lock-on logic, and task execution hooks.
- **Environmental safety** – [modules/light_sensor.py](modules/light_sensor.py) halts the robot the moment ambient light drops and announces status recovery once conditions normalize.
- **Status feedback** – [modules/voice_module.py](modules/voice_module.py) handles Piper/Espeak speech playback with caching so the robot can narrate its state and task transitions.
- **Action library** – pre-recorded hijet moves sit in [actions](actions) (`.d6a` sequences) and are triggered from `vision.run_action()` when a target is centered.

---

### Repository Layout
- [main.py](main.py) – launches camera/vision threads, arbitrates robot states, wires the light sensor kill-switch, and voices system events.
- [modules](modules)
	- [vision_module.py](modules/vision_module.py) – YOLO inference, detection smoothing, navigation cues, action glue.
	- [voice_module.py](modules/voice_module.py) – serial command ingestion, Piper TTS cache, Espeak fallback.
	- [light_sensor.py](modules/light_sensor.py) – BCM GPIO helper for the photoresistor circuit.
	- [qr_scanner.py](modules/qr_scanner.py) – standalone PyZbar utility to verify QR reads/camera focus.
- [actions](actions) – TonyStudio `.d6a` choreography files referenced by the main controller.
- [debug](debug) – small scripts to validate individual subsystems (camera feed, lighting, computer vision, voice pipeline).
- [resources/models](resources/models) – YOLO weights such as `cardboard_v1.pt`.
- [install_piper.sh](install_piper.sh) – convenience script that provisions the Piper virtual environment and voice models on the Pi.
- [logs](logs) – placeholder for runtime traces (git-ignored).

---

### Hardware & Software Prerequisites
1. **TonyPi platform** with the Hiwonder Camera, voice command board, and GPIO-connected light sensor on BCM pin 24.
2. **Operating system** – Raspberry Pi OS (Bookworm) or other Debian-based distro with audio output routed to the headphone jack/HDMI.
3. **Python** – 3.10+ with pip and virtualenv available.
4. **Native dependencies** – `libzbar0`, `portaudio19-dev`, `alsa-utils`, `libopenblas-dev`, plus `python3-opencv` if installing from apt.


```bash
sudo apt update && sudo apt install -y \
	python3-venv python3-pip libzbar0 portaudio19-dev alsa-utils libopenblas-dev
```


---

### Python Environment & Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel
pip install ultralytics opencv-python pyzbar pyserial RPi.GPIO
```

> **Tip:** Run `bash install_piper.sh` once to build the dedicated `piper_venv` and download `en_US-ryan-high.onnx` referenced by `voice_module.py`.


---

### Configuration
- Confirm `piper_venv/` and `piper_models/` directories sit beside `modules/` so `voice_module.py` can find the binary and voice weight.
- Define ALSA/ASOUND defaults if you need to force audio to HDMI or the 3.5mm jack.

---

### Running the Robot
```bash
source .venv/bin/activate
python main.py
```

1. The controller initializes Piper/voice, loads YOLO, and opens the Hiwonder camera.
2. The inference worker thread continuously updates `latest_result`; the main loop blends voice commands, vision cues, and the light sensor state machine.
3. Supported task phrases (case-sensitive as emitted by the hardware module): `Wake Up`, `Stop`, `Peeling`, `Insert Label`, `Transport`, `Flip`.
4. When a valid target is centered (`LOCKED`), `vision.run_action()` triggers the matching `.d6a` routine and announces completion.
5. Darkness triggers an emergency stop, overlays red warnings, and blocks new commands until light recovers.

Exit at any time with `Ctrl+C` or by pressing `q` in the preview window.

---

### Debug Utilities
- [debug/camera_debug.py](debug/camera_debug.py) – verify sensor exposure/FPS without touching the main stack.
- [debug/vision.py](debug/debug_vision.py) – run YOLO inference loops with overlays to tune thresholds.
- [debug/light.py](debug/debug_light.py) – confirm GPIO wiring for the safety sensor.
- [debug/voice.py](debug/debug_voice.py) – check serial packets and TTS output.
- [modules/qr_scanner.py](modules/qr_scanner.py) – confirm PyZbar scanning for die-cut labels.

---

### Development Workflow
1. **Model updates** – drop new weights into `resources/models`, update `MODEL_PATH` if needed, and keep `CONFIDENCE_THRESHOLD`, `LOCK_ENTER_TOLERANCE`, and `LOCK_EXIT_TOLERANCE` in sync with real-world tests.
2. **New actions** – add `.d6a` programs under `actions/` and extend `vision.run_action()` to map detection labels to sequences.
3. **Voice phrases** – extend `HEX_COMMANDS` inside `voice_module.py` plus the command branching in `main.py` to respond to new packets.
4. **Voice responses** – adjust phrases or add new Piper cache entries inside `voice_module.py` for richer narration.

---

### Troubleshooting
- **Camera fails to open** – ensure the Hiwonder driver is installed and no other process is locking `/dev/video0`.
- **No voice output** – confirm `piper_venv/bin/python3` exists and `aplay` can access the ALSA device; falling back to Espeak will log `[VOICE WARN]` messages.
- **Robot never locks target** – lower `LOCK_ENTER_TOLERANCE` or verify the `cardboard_v1.pt` class names line up with `VisionController.actions` keys.
- **Light sensor stuck in dark mode** – check BCM pin mapping and make sure `is_dark()` returns `False` when illuminated; call `sensor.cleanup()` after tests.

---

### Future Ideas
- Fuse QR data with YOLO detections to automatically label inventory.
- Stream telemetry to `logs/` and surface it in a lightweight web dashboard.
- Add arm joint calibration routines plus battery diagnostics to the voice responses.

---

### License
Will update as soon as distribution terms are finalized.

