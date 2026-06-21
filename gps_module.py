import config

def get_coordinates() -> tuple[float, float]:
    """
    Returns (lat, lng).
    Uses real GPS via serial port if GPS_PORT is set, otherwise returns fallback coords.
    """
    if config.GPS_PORT is None:
        return config.FALLBACK_LAT, config.FALLBACK_LNG

    try:
        import serial
        import pynmea2

        with serial.Serial(config.GPS_PORT, config.GPS_BAUD, timeout=5) as gps:
            for _ in range(50):                   # try up to 50 NMEA sentences
                line = gps.readline().decode("ascii", errors="replace").strip()
                if line.startswith("$GPRMC") or line.startswith("$GPGGA"):
                    msg = pynmea2.parse(line)
                    if hasattr(msg, "latitude") and msg.latitude:
                        return float(msg.latitude), float(msg.longitude)

    except Exception as e:
        print(f"[GPS] Error: {e} — using fallback coordinates")

    return config.FALLBACK_LAT, config.FALLBACK_LNG
