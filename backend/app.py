import os, sys, re, json, time, threading, subprocess
import cv2
import numpy as np
import yt_dlp
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config, gps_module, telegram_alert
from ultralytics import YOLO

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv"}
VEHICLE_CLASSES    = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
SNAPSHOT_PATH      = os.path.join(os.path.dirname(__file__), "crash_snapshot.jpg")

# ── Shared state ─────────────────────────────────────────────────
state = {
    "running": False, "progress": 0, "total_frames": 0,
    "crash_detected": False, "crash_frame": 0,
    "alert_sent": False, "status": "idle",
    "vehicles_detected": 0, "current_frame": 0,
    "lat": config.FALLBACK_LAT, "lng": config.FALLBACK_LNG,
}
latest_frame_jpg: bytes | None = None
frame_lock  = threading.Lock()
stop_event  = threading.Event()   # set this to kill any running detection thread


# ── Helpers ───────────────────────────────────────────────────────
def compute_iou(b1, b2) -> float:
    x1 = max(b1[0], b2[0]); y1 = max(b1[1], b2[1])
    x2 = min(b1[2], b2[2]); y2 = min(b1[3], b2[3])
    inter = max(0, x2-x1) * max(0, y2-y1)
    if inter == 0: return 0.0
    return inter / ((b1[2]-b1[0])*(b1[3]-b1[1]) + (b2[2]-b2[0])*(b2[3]-b2[1]) - inter)

def centroid(box):
    return ((box[0]+box[2])//2, (box[1]+box[3])//2)

def bbox_area(box):
    return max(0, box[2]-box[0]) * max(0, box[3]-box[1])

def crash_score(vehicles, prev_vehicles, prev_cents, frame, prev_frame) -> float:
    """
    Multi-signal crash score (0-1):
      S1 - IoU overlap between any two vehicles
      S2 - Sudden bbox area change (deformation on impact)
      S3 - Frame pixel difference spike (explosion/smoke/impact flash)
      S4 - Velocity direction reversal (vehicle stops abruptly)
    """
    s1 = s2 = s3 = s4 = 0.0

    # S1: IoU overlap
    if len(vehicles) >= 2:
        s1 = max(
            compute_iou(vehicles[i], vehicles[j])
            for i in range(len(vehicles))
            for j in range(i+1, len(vehicles))
        )

    # S2: sudden bbox area change (any vehicle grows/shrinks >40%)
    if prev_vehicles and vehicles:
        for idx, box in enumerate(vehicles):
            if idx < len(prev_vehicles):
                a_now  = bbox_area(box)
                a_prev = bbox_area(prev_vehicles[idx])
                if a_prev > 0:
                    ratio = abs(a_now - a_prev) / a_prev
                    s2 = max(s2, min(ratio / 0.6, 1.0))  # 60% change = 1.0

    # S3: frame pixel difference spike (motion/explosion)
    if prev_frame is not None:
        gray_now  = cv2.cvtColor(frame,      cv2.COLOR_BGR2GRAY)
        gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        diff      = cv2.absdiff(gray_now, gray_prev)
        # Focus on vehicle regions only
        mask = np.zeros(diff.shape, dtype=np.uint8)
        for box in vehicles:
            x1,y1,x2,y2 = box
            mask[max(0,y1-10):y2+10, max(0,x1-10):x2+10] = 1
        region_diff = diff * mask
        mean_diff   = float(np.mean(region_diff)) if mask.sum() > 0 else 0.0
        s3 = min(mean_diff / 25.0, 1.0)   # 25 mean pixel diff = 1.0

    # S4: abrupt velocity stop / direction flip
    if prev_cents and vehicles:
        for idx, box in enumerate(vehicles):
            if idx < len(prev_cents):
                c   = centroid(box)
                vel = ((c[0]-prev_cents[idx][0])**2 + (c[1]-prev_cents[idx][1])**2)**0.5
                # sudden stop: was moving, now near-zero
                s4 = max(s4, min(vel / 30.0, 1.0))

    # Weighted combination — S3 (pixel diff) carries most weight for real crashes
    score = s1*0.25 + s2*0.25 + s3*0.35 + s4*0.15
    return min(score, 1.0)

def _reset_state():
    """Reset detection state and signal any running thread to stop."""
    global latest_frame_jpg
    stop_event.set()          # tell old thread to exit
    time.sleep(0.3)           # give it a moment
    stop_event.clear()        # ready for new thread
    state.update({
        "running": False, "progress": 0, "total_frames": 0,
        "crash_detected": False, "crash_frame": 0,
        "alert_sent": False, "status": "idle",
        "vehicles_detected": 0, "current_frame": 0,
        "lat": config.FALLBACK_LAT, "lng": config.FALLBACK_LNG,
    })
    with frame_lock:
        latest_frame_jpg = None


# ── Shared detection logic ────────────────────────────────────────
def _detect_loop(model, frame_iter, my_stop: threading.Event):
    global latest_frame_jpg
    consecutive          = 0
    alert_cooldown_until = 0
    prev_cents           = []
    prev_vehicles        = []
    prev_frame           = None
    CRASH_THRESHOLD      = 0.45   # tuned for 4-signal scoring
    ALERT_COOLDOWN       = 60

    for frame_num, total, frame in frame_iter:
        if my_stop.is_set():
            break

        state["current_frame"] = frame_num
        state["progress"] = int((frame_num / total) * 100) if total else 0

        results  = model(frame, conf=0.35, verbose=False)[0]
        vehicles = [tuple(map(int, b.xyxy[0])) for b in results.boxes if int(b.cls[0]) in VEHICLE_CLASSES]
        state["vehicles_detected"] = len(vehicles)

        score = crash_score(vehicles, prev_vehicles, prev_cents, frame, prev_frame)
        hit   = score >= CRASH_THRESHOLD
        consecutive   = consecutive + 1 if hit else 0
        prev_cents    = [centroid(v) for v in vehicles]
        prev_vehicles = vehicles
        prev_frame    = frame.copy()

        annotated = frame.copy()
        for box in results.boxes:
            cls_id = int(box.cls[0])
            if cls_id in VEHICLE_CLASSES:
                x1,y1,x2,y2 = map(int, box.xyxy[0])
                color = (0, 100, 255) if hit else (0, 165, 255)
                cv2.rectangle(annotated, (x1,y1), (x2,y2), color, 2)
                cv2.putText(annotated, f"{VEHICLE_CLASSES[cls_id]} {box.conf[0]:.2f}",
                            (x1, y1-6), cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 2)

        # Score overlay for tuning
        cv2.putText(annotated, f"Score:{score:.2f}  Frame:{frame_num}",
                    (12, annotated.shape[0]-14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (180,180,180), 1)

        now = time.time()
        if consecutive >= config.ACCIDENT_FRAME_TRIGGER and now >= alert_cooldown_until:
            state.update({"crash_detected": True, "crash_frame": frame_num, "status": "crash_detected"})
            cv2.putText(annotated, "!! CRASH DETECTED !!", (20, 44),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0,0,255), 3)
            cv2.imwrite(SNAPSHOT_PATH, annotated)
            lat, lng = gps_module.get_coordinates()
            state["lat"] = lat; state["lng"] = lng
            threading.Thread(target=telegram_alert.send_accident_alert,
                             args=(lat, lng, SNAPSHOT_PATH), daemon=True).start()
            state["alert_sent"] = True
            alert_cooldown_until = now + ALERT_COOLDOWN
            consecutive = 0

        _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
        with frame_lock:
            latest_frame_jpg = buf.tobytes()


# ── Frame iterators ───────────────────────────────────────────────
def _cv2_iter(video_source):
    cap   = cv2.VideoCapture(video_source)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    state["total_frames"] = total
    n = 0
    while True:
        ret, frame = cap.read()
        if not ret: break
        n += 1
        yield n, total, frame
    cap.release()

def _pipe_iter(stream_url, width, height):
    import imageio_ffmpeg
    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg_bin, "-loglevel", "quiet", "-i", stream_url,
           "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-vf", f"scale={width}:{height}", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, bufsize=10**8)
    fsize = width * height * 3
    n = 0
    try:
        while True:
            raw = proc.stdout.read(fsize)
            if len(raw) < fsize: break
            n += 1
            yield n, 0, np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3)).copy()
    finally:
        proc.kill()


# ── Thread entry points ───────────────────────────────────────────
def _run(frame_iter, my_stop):
    state.update({"running": True, "status": "processing"})
    _detect_loop(YOLO(config.MODEL_PATH), frame_iter, my_stop)
    state["running"] = False
    if state["status"] == "processing":
        state["status"] = "completed_no_crash"

def _start(source):
    _reset_state()
    my_stop = stop_event
    state["status"] = "starting"
    threading.Thread(target=_run, args=(_cv2_iter(source), my_stop), daemon=True).start()

def _start_pipe(stream_url, width, height):
    _reset_state()
    my_stop = stop_event
    state["status"] = "starting"
    threading.Thread(target=_run, args=(_pipe_iter(stream_url, width, height), my_stop), daemon=True).start()


# ── Routes ────────────────────────────────────────────────────────
def allowed_file(f):
    return "." in f and f.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/api/upload", methods=["POST"])
def upload_video():
    f = request.files.get("video")
    if not f or not allowed_file(f.filename):
        return jsonify({"error": "Invalid file"}), 400
    path = os.path.join(UPLOAD_FOLDER, secure_filename(f.filename))
    f.save(path)
    _start(path)
    return jsonify({"message": "Detection started."})

@app.route("/api/youtube", methods=["POST"])
def analyse_youtube():
    url = (request.get_json() or {}).get("url", "").strip()
    if not re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url):
        return jsonify({"error": "Invalid YouTube URL"}), 400
    try:
        with yt_dlp.YoutubeDL({"format": "best[ext=mp4][height<=720]/best[ext=mp4]/best", "quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info["url"]
            width  = info.get("width",  1280)
            height = info.get("height",  720)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    _start_pipe(stream_url, width, height)
    return jsonify({"message": "YouTube stream analysis started."})

@app.route("/api/stream")
def stream_status():
    def gen():
        while state["running"] or state["status"] in ("starting", "processing"):
            yield f"data: {json.dumps(state)}\n\n"
            time.sleep(0.4)
        yield f"data: {json.dumps(state)}\n\n"
    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/frame")
def live_frame():
    with frame_lock:
        jpg = latest_frame_jpg
    if jpg is None:
        return Response(status=204)
    return Response(jpg, mimetype="image/jpeg", headers={"Cache-Control": "no-cache"})

@app.route("/api/status")
def get_status():
    return jsonify(state)

@app.route("/api/reset", methods=["POST"])
def reset():
    _reset_state()
    return jsonify({"message": "Reset"})

if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
