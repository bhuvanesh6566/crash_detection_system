# ── Configuration ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "8412008977:AAHCCP5ZwJvLzC-GvyWk9yN4LzNRwoG3LIU"          # from @BotFather
TELEGRAM_CHAT_IDS  = ["7292255722", "<chat_id_2>"]  # family / ambulance

# Camera source: 0 = webcam, or path to video file
CAMERA_SOURCE = "accident_video.mp4"

# YOLOv8 model weights
MODEL_PATH = "yolov8n.pt"

# Detection thresholds
CONFIDENCE_THRESHOLD = 0.35
ACCIDENT_FRAME_TRIGGER = 4        # consecutive frames before alert fires

# GPS: set to None to use simulated coords (for testing)
GPS_PORT   = None                 # e.g. "COM3" on Windows
GPS_BAUD   = 9600

# Fallback / simulated GPS coordinates
FALLBACK_LAT = 13.0827
FALLBACK_LNG = 80.2707
