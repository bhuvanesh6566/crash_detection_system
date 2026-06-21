import requests
import config

TELEGRAM_API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


def _post(endpoint: str, **kwargs) -> dict:
    resp = requests.post(f"{TELEGRAM_API}/{endpoint}", timeout=10, **kwargs)
    return resp.json()


def send_text(message: str):
    """Send a text alert to all configured chat IDs."""
    for chat_id in config.TELEGRAM_CHAT_IDS:
        _post("sendMessage", data={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        })


def send_location(lat: float, lng: float):
    """Send a Telegram live-location pin to all chat IDs."""
    for chat_id in config.TELEGRAM_CHAT_IDS:
        _post("sendLocation", data={
            "chat_id": chat_id,
            "latitude": lat,
            "longitude": lng
        })


def send_photo(image_path: str, caption: str = ""):
    """Send a crash frame screenshot to all chat IDs."""
    for chat_id in config.TELEGRAM_CHAT_IDS:
        with open(image_path, "rb") as photo:
            _post("sendPhoto", data={
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML"
            }, files={"photo": photo})


def send_accident_alert(lat: float, lng: float, snapshot_path: str = None):
    """
    Full accident alert sequence:
      1. Text message with Google Maps link
      2. Telegram location pin
      3. Crash frame photo (if available)
    """
    maps_link = f"https://maps.google.com/?q={lat},{lng}"
    message = (
        "🚨 <b>ACCIDENT DETECTED!</b>\n\n"
        f"📍 <b>Location:</b> <a href='{maps_link}'>{maps_link}</a>\n"
        "⚠️ Please respond immediately!\n"
        "🏥 Contact emergency services if needed."
    )
    send_text(message)
    send_location(lat, lng)

    if snapshot_path:
        send_photo(snapshot_path, caption="📸 Crash frame captured by AI system")

    print(f"[TELEGRAM] Alerts sent → {lat}, {lng}")
