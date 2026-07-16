import cv2
from pyzbar import pyzbar # Import the pyzbar library
import time
import sys # Added for exiting

# --- Initialize Camera ---
camera_index = 0 # Default camera index
cap = cv2.VideoCapture(camera_index)

if not cap.isOpened():
    print(f"Error: Cannot open camera at index {camera_index}")
    # Attempt alternative index if default fails
    camera_index = 1
    print(f"Trying camera index {camera_index}...")
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
         print(f"Error: Cannot open camera at index {camera_index} either.")
         sys.exit(1) # Exit if camera fails

print(f"Camera opened successfully on index {camera_index}. Press 'q' to quit.")

# --- Main Loop ---
fps = 0
frame_count = 0
start_time_total = time.time()

while True:
    try:
        ret, frame = cap.read()
        if not ret:
            print("Warning: Failed to grab frame, skipping...")
            time.sleep(0.1)
            continue

        frame_count += 1
        start_time_frame = time.time()

        # --- Find and Decode QR Codes ---
        # Use pyzbar to detect barcodes in the frame
        barcodes = pyzbar.decode(frame)

        # --- Process Detected Barcodes ---
        for barcode in barcodes:
            # Extract the bounding box location
            (x, y, w, h) = barcode.rect
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2) # Draw green box

            # Decode barcode data to string
            barcode_data = barcode.data.decode("utf-8")
            barcode_type = barcode.type

            # Draw the barcode data and type on the image
            text = f"{barcode_type}: {barcode_data}"
            cv2.putText(frame, text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # Print detected data to terminal (optional)
            # print(f"Detected {barcode_type}: {barcode_data}")


        # Calculate and display FPS
        end_time_frame = time.time()
        if end_time_frame > start_time_frame:
            fps = 1 / (end_time_frame - start_time_frame)

        cv2.putText(frame, f"FPS: {fps:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.imshow('TonyPi Pro - QR Code Scanner', frame)

        # Press 'q' to exit
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    except KeyboardInterrupt:
        print("Interrupted by user.")
        break
    except Exception as e:
        print(f"An error occurred in the main loop: {e}")
        time.sleep(1)

# --- Cleanup ---
cap.release()
cv2.destroyAllWindows()
end_time_total = time.time()
total_time = end_time_total - start_time_total
avg_fps = frame_count / total_time if total_time > 0 else 0
print("Script finished.")
print(f"Processed {frame_count} frames in {total_time:.2f} seconds (Avg FPS: {avg_fps:.2f}")


def decode_qr(frame):
    """
    Decode QR/barcodes in the given BGR frame and return a list of decoded strings.
    Re-usable by main.py / vision controller.
    """
    from pyzbar import pyzbar
    results = []
    try:
        barcodes = pyzbar.decode(frame)
        for barcode in barcodes:
            try:
                data = barcode.data.decode("utf-8")
                results.append(data)
            except Exception:
                continue
    except Exception:
        pass
    return results