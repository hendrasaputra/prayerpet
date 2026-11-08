"""Offline prayer-time calculation (PrayTimes.org algorithm, no dependencies).

All angles in degrees. Times returned as timezone-aware datetimes.
"""
import math
from datetime import date, datetime, timedelta, time as dtime

# fajr/isha: angle below horizon. isha_minutes: fixed minutes after maghrib instead of angle.
# offsets: minutes added after calculation (Kemenag "ihtiyat" safety margin).
METHODS = {
    "kemenag": dict(fajr=20.0, isha=18.0,
                    offsets=dict(imsak=-10, fajr=2, sunrise=-3, dhuha=2, dhuhr=3, asr=2, maghrib=3, isha=2),
                    rounding="up"),
    "jakim":   dict(fajr=20.0, isha=18.0, offsets=dict(fajr=2, dhuhr=2, asr=2, maghrib=2, isha=2), rounding="up"),
    "muis":    dict(fajr=20.0, isha=18.0, offsets=dict(fajr=2, dhuhr=2, asr=2, maghrib=2, isha=2), rounding="up"),
    "mwl":     dict(fajr=18.0, isha=17.0),
    "isna":    dict(fajr=15.0, isha=15.0),
    "egypt":   dict(fajr=19.5, isha=17.5),
    "makkah":  dict(fajr=18.5, isha_minutes=90),
    "karachi": dict(fajr=18.0, isha=18.0),
    "turkey":  dict(fajr=18.0, isha=17.0),
}

ORDER = ["imsak", "fajr", "sunrise", "dhuha", "dhuhr", "asr", "maghrib", "isha"]


def _sin(d): return math.sin(math.radians(d))
def _cos(d): return math.cos(math.radians(d))
def _tan(d): return math.tan(math.radians(d))
def _asin(x): return math.degrees(math.asin(x))
def _acos(x): return math.degrees(math.acos(x))
def _atan2(y, x): return math.degrees(math.atan2(y, x))
def _acot(x): return math.degrees(math.atan(1.0 / x))
def _fix(a, b): a = a - b * math.floor(a / b); return a + b if a < 0 else a


def _julian(y, m, d):
    if m <= 2:
        y -= 1
        m += 12
    a = math.floor(y / 100)
    b = 2 - a + math.floor(a / 4)
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d + b - 1524.5


def _sun(jd):
    D = jd - 2451545.0
    g = _fix(357.529 + 0.98560028 * D, 360)
    q = _fix(280.459 + 0.98564736 * D, 360)
    L = _fix(q + 1.915 * _sin(g) + 0.020 * _sin(2 * g), 360)
    e = 23.439 - 0.00000036 * D
    ra = _atan2(_cos(e) * _sin(L), _cos(L)) / 15.0
    eqt = q / 15.0 - _fix(ra, 24)
    decl = _asin(_sin(e) * _sin(L))
    return decl, eqt


class PrayerCalculator:
    def __init__(self, lat, lon, tz, method="kemenag", asr="shafi", elevation=0.0,
                 fajr_angle=None, isha_angle=None, isha_minutes=None,
                 dhuha_angle=4.5, offsets=None, rounding=None):
        self.lat, self.lon, self.tz = float(lat), float(lon), tz
        m = METHODS.get(method.lower())
        if m is None:
            raise ValueError(f"Unknown method '{method}'. Choose from: {', '.join(METHODS)}")
        self.fajr_angle = fajr_angle if fajr_angle is not None else m["fajr"]
        self.isha_angle = isha_angle if isha_angle is not None else m.get("isha")
        self.isha_minutes = isha_minutes if isha_minutes is not None else m.get("isha_minutes")
        if isha_angle is not None:
            self.isha_minutes = None
        self.asr_factor = 2 if str(asr).lower() == "hanafi" else 1
        self.dhuha_angle = dhuha_angle
        self.rise_angle = 0.833 + 0.0347 * math.sqrt(max(0.0, float(elevation)))
        base = dict(imsak=-10)  # imsak = 10 min before fajr unless method says otherwise
        base.update(m.get("offsets", {}))
        for k, v in (offsets or {}).items():  # user fine-tuning is added on top of the method's margins
            base[k] = base.get(k, 0) + float(v)
        self.offsets = base
        self.rounding = rounding or m.get("rounding", "nearest")

    # --- core astronomy -------------------------------------------------
    def _mid_day(self, jd, t):
        _, eqt = _sun(jd + t)
        return _fix(12 - eqt, 24)

    def _angle_time(self, jd, angle, t, ccw=False):
        decl, _ = _sun(jd + t)
        noon = self._mid_day(jd, t)
        x = (-_sin(angle) - _sin(decl) * _sin(self.lat)) / (_cos(decl) * _cos(self.lat))
        x = max(-1.0, min(1.0, x))
        T = _acos(x) / 15.0
        return noon + (-T if ccw else T)

    def _asr_time(self, jd, t):
        decl, _ = _sun(jd + t)
        angle = -_acot(self.asr_factor + _tan(abs(self.lat - decl)))
        return self._angle_time(jd, angle, t)

    def _raw_hours(self, d):
        """Local-solar hours for each event, before timezone shift."""
        jd = _julian(d.year, d.month, d.day) - self.lon / (15 * 24.0)
        t = dict(fajr=5, sunrise=6, dhuha=7, dhuhr=12, asr=13, sunset=18, isha=18)
        for _ in range(3):  # refine using the previous estimate
            p = {k: v / 24.0 for k, v in t.items()}
            t = dict(
                fajr=self._angle_time(jd, self.fajr_angle, p["fajr"], ccw=True),
                sunrise=self._angle_time(jd, self.rise_angle, p["sunrise"], ccw=True),
                dhuha=self._angle_time(jd, -self.dhuha_angle, p["dhuha"], ccw=True),
                dhuhr=self._mid_day(jd, p["dhuhr"]),
                asr=self._asr_time(jd, p["asr"]),
                sunset=self._angle_time(jd, self.rise_angle, p["sunset"]),
                isha=(self._angle_time(jd, self.isha_angle, p["isha"]) if self.isha_minutes is None else 0),
            )
        t["maghrib"] = t["sunset"]
        if self.isha_minutes is not None:
            t["isha"] = t["maghrib"] + self.isha_minutes / 60.0
        t["imsak"] = t["fajr"]
        return t

    # --- public ---------------------------------------------------------
    def times_for(self, d: date):
        """Return {name: aware datetime} for the given local date."""
        midnight = datetime.combine(d, dtime(0, 0), tzinfo=self.tz)
        utc_off_h = midnight.utcoffset().total_seconds() / 3600.0
        raw = self._raw_hours(d)
        out = {}
        for name in ORDER:
            if name == "imsak":
                continue  # derived from final fajr below
            hours = raw[name] + utc_off_h - self.lon / 15.0
            minutes = hours * 60.0 + self.offsets.get(name, 0)
            if self.rounding == "up" and name != "sunrise":
                minutes = math.ceil(minutes - 1e-6)
            elif self.rounding in ("up", "down") and name == "sunrise":
                minutes = math.floor(minutes)
            else:
                minutes = round(minutes)
            out[name] = midnight + timedelta(minutes=minutes)
        out["imsak"] = out["fajr"] + timedelta(minutes=self.offsets.get("imsak", -10))
        return {k: out[k] for k in ORDER}
