import cv2

print("--- Scanning Camera Indexes (0 to 10) ---")

available_cameras = []

for index in range(10):
    try:
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                print(f"[SUCCESS] Camera found at Index: {index}")
                print(f"   - Resolution: {int(cap.get(3))}x{int(cap.get(4))}")
                available_cameras.append(index)
            else:
                print(f"[WARNING] Index {index} opens, but returns no image (Virtual/Dummy).")
            cap.release()
    except Exception as e:
        pass

print("---------------------------------------")
if available_cameras:
    print(f"RECOMMENDATION: Use Index {available_cameras[0]} in your code.")
else:
    print("FAIL: No physical cameras found. Check ribbon cable.")