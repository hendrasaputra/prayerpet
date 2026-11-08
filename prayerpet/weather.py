"""Weather and air quality from Open-Meteo (free, no account). Fetched in the background and cached."""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


def _get(url, params, timeout=15):
    q = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(q, headers={"User-Agent": "prayerpet/1.3 (Raspberry Pi)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# WMO weather codes -> (kind, english, indonesian)
def describe(code):
    code = int(code) if code is not None else -1
    if code == 0:
        return "clear", "Clear", "Cerah"
    if code == 1:
        return "clear", "Mainly clear", "Cerah"
    if code == 2:
        return "partly", "Partly cloudy", "Cerah berawan"
    if code == 3:
        return "cloud", "Overcast", "Mendung"
    if code in (45, 48):
        return "fog", "Fog", "Berkabut"
    if 51 <= code <= 57:
        return "drizzle", "Drizzle", "Gerimis"
    if code in (61, 80):
        return "rain", "Light rain", "Hujan ringan"
    if code in (63, 66, 81):
        return "rain", "Rain", "Hujan"
    if code in (65, 67, 82):
        return "rain", "Heavy rain", "Hujan lebat"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow", "Snow", "Salju"
    if 95 <= code <= 99:
        return "storm", "Thunderstorm", "Badai petir"
    return "cloud", "-", "-"


def is_wet(code):
    return describe(code)[0] in ("drizzle", "rain", "storm")


AQI_BANDS = [  # US AQI
    (50, "Good", "Baik"),
    (100, "Moderate", "Sedang"),
    (150, "Unhealthy (sensitive)", "Tdk sehat (sensitif)"),
    (200, "Unhealthy", "Tidak sehat"),
    (300, "Very unhealthy", "Sangat tdk sehat"),
    (10 ** 6, "Hazardous", "Berbahaya"),
]


def aqi_band(aqi):
    """Return (index 0..5, english, indonesian)."""
    for i, (hi, en, idn) in enumerate(AQI_BANDS):
        if aqi <= hi:
            return i, en, idn
    return 5, AQI_BANDS[-1][1], AQI_BANDS[-1][2]


class Weather:
    def __init__(self, lat, lon, refresh_minutes=15, cache="~/.prayerpet-weather.json"):
        self.lat, self.lon = float(lat), float(lon)
        self.refresh = max(5, float(refresh_minutes)) * 60
        self.cache = os.path.expanduser(cache)
        self._lock = threading.Lock()
        self._data = {}
        try:
            with open(self.cache) as f:
                d = json.load(f)
            # ignore a cache from another location
            if abs(d.get("lat", 999) - self.lat) < 0.05 and abs(d.get("lon", 999) - self.lon) < 0.05:
                self._data = d
        except Exception:
            pass
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def snapshot(self):
        with self._lock:
            return dict(self._data)

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            ok = self.fetch()
            self._stop.wait(self.refresh if ok else 120)

    def fetch(self):
        new = dict(lat=self.lat, lon=self.lon)
        ok = True
        try:
            w = _get(FORECAST_URL, dict(
                latitude=self.lat, longitude=self.lon, timezone="auto", forecast_days=1, forecast_hours=7,
                current="temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,is_day",
                hourly="temperature_2m,precipitation_probability,weather_code,is_day",
                daily="temperature_2m_max,temperature_2m_min,precipitation_probability_max"))
            cur, hr, dy = w.get("current", {}), w.get("hourly", {}), w.get("daily", {})
            new.update(
                temp=cur.get("temperature_2m"), feels=cur.get("apparent_temperature"),
                humidity=cur.get("relative_humidity_2m"), wind=cur.get("wind_speed_10m"),
                code=cur.get("weather_code"), is_day=cur.get("is_day", 1),
                hi=(dy.get("temperature_2m_max") or [None])[0], lo=(dy.get("temperature_2m_min") or [None])[0],
                rain_max=(dy.get("precipitation_probability_max") or [None])[0],
                hours=[dict(time=t[-5:-3], temp=tp, rain=rp, code=cd, is_day=dd) for t, tp, rp, cd, dd in zip(
                    hr.get("time", []), hr.get("temperature_2m", []), hr.get("precipitation_probability", []),
                    hr.get("weather_code", []), hr.get("is_day", [1] * 99))][1:7],
                weather_at=time.time(), weather_error=None)
        except Exception as e:
            ok = False
            new["weather_error"] = str(e)[:80]
        try:
            a = _get(AIR_URL, dict(latitude=self.lat, longitude=self.lon, timezone="auto",
                                   current="us_aqi,pm2_5,pm10"))
            cur = a.get("current", {})
            new.update(aqi=cur.get("us_aqi"), pm25=cur.get("pm2_5"), pm10=cur.get("pm10"),
                       air_at=time.time(), air_error=None)
        except Exception as e:
            ok = False
            new["air_error"] = str(e)[:80]
        with self._lock:
            merged = dict(self._data)
            merged.update({k: v for k, v in new.items() if v is not None or k.endswith("_error")})
            self._data = merged
        try:
            tmp = self.cache + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._data, f)
            os.replace(tmp, self.cache)
        except Exception:
            pass
        return ok
