"""Whole-app smoke tests: schedule states, and rendering every page to PNG."""
import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from tests.helpers import IsolatedHome

try:
    import numpy  # noqa: F401
    from PIL import Image  # noqa: F401
    HAVE_DEPS = True
except ImportError:
    HAVE_DEPS = False


class TestSchedule(IsolatedHome):
    def test_states_through_the_day(self):
        from prayerpet import config
        from prayerpet.app import Schedule, make_calculator
        cfg = config.load("~/prayerpet.toml")  # default: Jakarta, Kemenag; Ashar 14:54, Isya 19:00
        tz = ZoneInfo(cfg["location"]["timezone"])
        s = Schedule(cfg, make_calculator(cfg, tz))
        self.assertEqual(s.compute(datetime(2026, 10, 31, 14, 47, tzinfo=tz))["state"], "alert")
        self.assertEqual(s.compute(datetime(2026, 10, 31, 14, 58, tzinfo=tz))["state"], "prayer")
        self.assertEqual(s.compute(datetime(2026, 10, 31, 22, 30, tzinfo=tz))["state"], "sleep")
        self.assertEqual(s.compute(datetime(2026, 10, 31, 10, 0, tzinfo=tz))["state"], "awake")


@unittest.skipUnless(HAVE_DEPS, "needs Pillow and numpy")
class TestRender(IsolatedHome):
    def test_png_frames_all_pages(self):
        from prayerpet import app, config, inbox
        from prayerpet.display import PngDisplay
        cfg = config.load("~/prayerpet.toml")
        cfg["weather"]["enabled"] = False  # no network in tests
        inbox.post("say", text="Test message on the screen", minutes=1)
        for page in ("home", "weather", "status"):
            out = os.path.join(self.home, f"{page}.png")
            app.run(cfg, PngDisplay(out), at="2026-10-31 14:20", frames=3, page=page)
            self.assertGreater(os.path.getsize(out), 1000)


if __name__ == "__main__":
    unittest.main()
