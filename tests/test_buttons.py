"""Buttons with gpiozero's mock pins: short press fires on release; hold-to-shutdown fires once."""
import time
import unittest

from tests.helpers import ROOT  # noqa: F401

try:
    from gpiozero import Device
    from gpiozero.pins.mock import MockFactory
    HAVE_GPIOZERO = True
except ImportError:
    HAVE_GPIOZERO = False


@unittest.skipUnless(HAVE_GPIOZERO, "needs gpiozero (pip install gpiozero)")
class TestButtons(unittest.TestCase):
    def setUp(self):
        Device.pin_factory = MockFactory()
        from prayerpet.buttons import Buttons
        self.b = Buttons(dict(order=[17, 22, 23, 27], gpio17="page", gpio22="feed", gpio23="pat",
                              gpio27="screen", shutdown_pin=27, shutdown_hold_seconds=1))
        self.pins = {p: Device.pin_factory.pin(p) for p in self.b.pins}

    def tearDown(self):
        self.b.close()

    def test_short_press(self):
        self.pins[22].drive_low()
        time.sleep(0.1)
        self.pins[22].drive_high()
        time.sleep(0.1)
        presses = [e for e in self.b.poll() if e[0] != "down"]
        self.assertEqual(presses, [("press", 22)])
        self.assertEqual(self.b.action(22), "feed")

    def test_hold_shutdown_fires_once_and_no_press(self):
        self.pins[27].drive_low()
        events = []
        end = time.time() + 1.5
        while time.time() < end:
            events += self.b.poll()
            time.sleep(0.05)
        self.pins[27].drive_high()
        time.sleep(0.1)
        events += self.b.poll()
        self.assertEqual([e for e in events if e[0] == "hold"], [("hold", 27)])
        self.assertNotIn(("press", 27), events)


if __name__ == "__main__":
    unittest.main()
