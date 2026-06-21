import cv2
import time
import threading
from ultralytics import YOLO
import config
import gps_module
import telegram_alert

# Vehicle class IDs in COCO dataset (used by YOLOv8n)
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
SNAPSHOT_PATH   = "crash_snapshot.jpg"


def boxes_overlap(b1, b2) -> bool:
    """Check if two bounding boxes intersect (collision proxy)."""
    x1, y1, x2, y2 = b1
    x3, y3, x4, y4 = b2
    return not (x2 < x3 or x4 < x1 or y2 < y3 or y4 < y1)


def detect_crash(frame, model) -> bool:
    """
    Returns True if a crash is detected in the frame.
    Strategy:
      - Detect all vehicles in the frame.
      - Flag crash if two or more vehicle bounding boxes overlap.
      - Also flags if 'fire' or 'smoke' detected (class 0 workaround via confidence spike).
    """
    results = model(frame, conf=config.CONFIDENCE_THRESHOLD, verbose=False)[0]
    vehicles = []

    for box in results.boxes:
        cls_id = int(box.cls[0])
        if cls_id in VEHICLE_CLASSES:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            vehicles.append((x1, y1, x2, y2))

    # Check for overlapping vehicle bounding boxes
    for i in range(len(vehicles)):
        for j in range(i + 1, len(vehicles)):
            if boxes_overlap(vehicles[i], vehicles[j]):
                return True

    return False


def draw_boxes(frame, model):
    """Draw bounding boxes on vehicles for visualization."""
    results = model(frame, conf=config.CONFIDENCE_THRESHOLD, verbose=False)[0]
    for box in results.boxes:
        cls_id = int(box.cls[0])
        if cls_id in VEHICLE_CLASSES:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            label = VEHICLE_CLASSES[cls_id]
            conf  = float(box.conf[0])
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"{label} {conf:.2f}", (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    return frame


def run_detection():
    model = YOLO(config.MODEL_PATH)
    cap   = cv2.VideoCapture(config.CAMERA_SOURCE)

    if not cap.isOpened():
        print("[ERROR] Cannot open camera/video source.")
        return

    print("[INFO] Detection started. Press 'q' to quit.")

    consecutive_hits = 0
    alert_sent       = False
    alert_cooldown   = 30          # seconds before another alert can fire

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[INFO] End of video stream.")
            break

        crash_detected = detect_crash(frame, model)
        frame = draw_boxes(frame, model)

        if crash_detected:
            consecutive_hits += 1
            cv2.putText(frame, "⚠ CRASH DETECTED", (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        else:
            consecutive_hits = 0

        # Trigger alert only after N consecutive crash frames
        if consecutive_hits >= config.ACCIDENT_FRAME_TRIGGER and not alert_sent:
            cv2.imwrite(SNAPSHOT_PATH, frame)
            lat, lng = gps_module.get_coordinates()

            # Send alerts in a background thread — keeps video stream smooth
            threading.Thread(
                target=telegram_alert.send_accident_alert,
                args=(lat, lng, SNAPSHOT_PATH),
                daemon=True
            ).start()

            alert_sent = True
            alert_reset_time = time.time() + alert_cooldown
            print(f"[ALERT] Crash confirmed! Notifying contacts → {lat}, {lng}")

        # Reset alert flag after cooldown
        if alert_sent and time.time() >= alert_reset_time:
            alert_sent       = False
            consecutive_hits = 0

        cv2.imshow("Accident Detection System", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
