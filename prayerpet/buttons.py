"""The four PiTFT side buttons (GPIO 17, 22, 23, 27; pressed = pin pulled to ground)."""
import queue
import time

ACTIONS = ("page", "feed", "pat", "screen", "none")


class Buttons:
    """Puts ('press', pin) and ('hold', pin) events on .events. Short press fires on release,
    so holding the shutdown button never also triggers its short action."""

    def __init__(self, cfg):
        from gpiozero import Button  # python3-gpiozero (+ python3-lgpio on Bookworm)
        self.cfg = cfg
        self.events = queue.Queue()
        self.down_since = {}
        self.held = set()
        self.pins = [int(p) for p in cfg.get("order", [17, 22, 23, 27])]
        self.shutdown_pin = int(cfg.get("shutdown_pin", 0) or 0)
        self.hold_s = float(cfg.get("shutdown_hold_seconds", 5) or 0)
        self._buttons = []
        for pin in self.pins:
            b = Button(pin, pull_up=True, bounce_time=0.03)
            b.when_pressed = lambda pin=pin: self._down(pin)
            b.when_released = lambda pin=pin: self._up(pin)
            self._buttons.append(b)

    def action(self, pin):
        a = str(self.cfg.get(f"gpio{pin}", "none")).lower()
        return a if a in ACTIONS else "none"

    def describe(self):
        return ", ".join(f"GPIO{p}={self.action(p)}" for p in self.pins) + \
            (f" | hold GPIO{self.shutdown_pin} {self.hold_s:.0f}s = shut down" if self.hold_s and self.shutdown_pin else "")

    def _down(self, pin):
        self.down_since[pin] = time.time()
        self.events.put(("down", pin))

    def _up(self, pin):
        self.down_since.pop(pin, None)
        if pin in self.held:
            self.held.discard(pin)
            return
        self.events.put(("press", pin))

    def poll(self):
        """Call every frame. Returns list of events; also emits 'hold' when the shutdown button is held long enough."""
        if self.hold_s and self.shutdown_pin in self.down_since and self.shutdown_pin not in self.held:
            if time.time() - self.down_since[self.shutdown_pin] >= self.hold_s:
                self.held.add(self.shutdown_pin)
                self.events.put(("hold", self.shutdown_pin))
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out

    def hold_progress(self):
        """0..1 while the shutdown button is being held, else None."""
        if not self.hold_s or self.shutdown_pin not in self.down_since or self.shutdown_pin in self.held:
            return None
        held = time.time() - self.down_since[self.shutdown_pin]
        return min(1.0, held / self.hold_s) if held > 0.8 else None

    def close(self):
        for b in self._buttons:
            try:
                b.close()
            except Exception:
                pass
