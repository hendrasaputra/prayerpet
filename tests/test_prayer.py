"""Prayer-time engine checks.

Reference: official Kemenag schedule for Kota Jakarta (api.myquran.com, which serves Kemenag data),
fetched 2026-10-31, coordinates -6.2088, 106.8456. Expected: exact match except Maghrib on
2027-01-15, which comes out 1 minute late (known; the safe direction).
"""
import unittest
from datetime import date
from zoneinfo import ZoneInfo

from tests.helpers import ROOT  # noqa: F401  (puts the project on sys.path)
from prayerpet.prayer import ORDER, PrayerCalculator

TZ = ZoneInfo("Asia/Jakarta")
KEMENAG_JAKARTA = {
    date(2026, 10, 31): "03:59 04:09 05:23 05:51 11:40 14:54 17:49 19:00",
    date(2026, 6, 21): "04:30 04:40 05:58 06:27 11:58 15:19 17:51 19:05",
    date(2027, 1, 15): "04:17 04:27 05:45 06:14 12:05 15:29 18:18 19:33",
}


def minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


class TestKemenag(unittest.TestCase):
    def test_matches_official_schedule(self):
        calc = PrayerCalculator(-6.2088, 106.8456, TZ, "kemenag")
        exact = 0
        for d, ref in KEMENAG_JAKARTA.items():
            got = calc.times_for(d)
            for key, want in zip(ORDER, ref.split()):
                diff = minutes(got[key].strftime("%H:%M")) - minutes(want)
                self.assertLessEqual(abs(diff), 1, f"{d} {key}: got {got[key]:%H:%M}, Kemenag {want}")
                exact += diff == 0
        self.assertGreaterEqual(exact, 23, "expected at least 23 of 24 exact matches")

    def test_imsak_is_ten_minutes_before_fajr(self):
        t = PrayerCalculator(-6.2088, 106.8456, TZ, "kemenag").times_for(date(2026, 10, 31))
        self.assertEqual((t["fajr"] - t["imsak"]).total_seconds(), 600)

    def test_user_offsets_add_to_method_margins(self):
        d = date(2026, 10, 31)
        base = PrayerCalculator(-6.2088, 106.8456, TZ, "kemenag").times_for(d)
        moved = PrayerCalculator(-6.2088, 106.8456, TZ, "kemenag", offsets={"isha": 2}).times_for(d)
        self.assertEqual((moved["isha"] - base["isha"]).total_seconds(), 120)


class TestOtherMethods(unittest.TestCase):
    def test_yangon_karachi_hanafi(self):
        # cross-checked against the Aladhan API (method=1, school=1) for 2026-10-31
        t = PrayerCalculator(16.8409, 96.1735, ZoneInfo("Asia/Yangon"), "karachi",
                             asr="hanafi").times_for(date(2026, 10, 31))
        got = {k: t[k].strftime("%H:%M") for k in ("fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha")}
        self.assertEqual(got, dict(fajr="04:49", sunrise="06:03", dhuhr="11:49",
                                   asr="15:59", maghrib="17:35", isha="18:48"))

    def test_hanafi_asr_is_later_than_shafi(self):
        tz = ZoneInfo("Asia/Yangon")
        d = date(2026, 10, 31)
        s = PrayerCalculator(16.8409, 96.1735, tz, "karachi", asr="shafi").times_for(d)
        h = PrayerCalculator(16.8409, 96.1735, tz, "karachi", asr="hanafi").times_for(d)
        self.assertGreater(h["asr"], s["asr"])

    def test_unknown_method_raises(self):
        with self.assertRaises(ValueError):
            PrayerCalculator(0, 0, TZ, "nope")


if __name__ == "__main__":
    unittest.main()
