"""Resistive touchscreen input via evdev. Reports taps as screen (x, y) in 320x240 space."""
import threading

W, H = 320, 240


def find_touch_device(path="auto"):
    import evdev
    if path and path != "auto":
        return evdev.InputDevice(path)
    try:
        return evdev.InputDevice("/dev/input/touchscreen")
    except Exception:
        pass
    for p in evdev.list_devices():
        d = evdev.InputDevice(p)
        caps = d.capabilities()
        abs_caps = [c[0] if isinstance(c, tuple) else c for c in caps.get(evdev.ecodes.EV_ABS, [])]
        if ("stmpe" in d.name.lower() or "touch" in d.name.lower()) and evdev.ecodes.ABS_X in abs_caps:
            return d
    return None


class Touch:
    """Background reader. Call .get_taps() each frame."""

    def __init__(self, cfg):
        import evdev
        self.ec = evdev.ecodes
        self.cfg = cfg
        self.dev = find_touch_device(cfg.get("device", "auto"))
        if self.dev is None:
            raise RuntimeError("No touchscreen found")
        self.raw = [0, 0]
        self.down = False
        self.taps = []
        self.lock = threading.Lock()
        self.debug = False
        threading.Thread(target=self._loop, daemon=True).start()

    def describe(self):
        return f"{self.dev.path} ({self.dev.name})"

    def map(self, rx, ry):
        c = self.cfg
        nx = (rx - c["raw_x_min"]) / float(c["raw_x_max"] - c["raw_x_min"])
        ny = (ry - c["raw_y_min"]) / float(c["raw_y_max"] - c["raw_y_min"])
        if c.get("swap_xy"):
            nx, ny = ny, nx
        if c.get("invert_x"):
            nx = 1 - nx
        if c.get("invert_y"):
            ny = 1 - ny
        return (max(0, min(W - 1, int(nx * W))), max(0, min(H - 1, int(ny * H))))

    def _release(self):
        self.down = False
        pos = self.map(*self.raw)
        if self.debug:
            print(f"TOUCH  raw x={self.raw[0]:5d} y={self.raw[1]:5d}  ->  screen x={pos[0]:3d} y={pos[1]:3d}",
                  flush=True)
        with self.lock:
            self.taps.append(pos)

    def _loop(self):
        ec = self.ec
        seen_btn = False
        try:
            for ev in self.dev.read_loop():
                if ev.type == ec.EV_ABS:
                    if ev.code == ec.ABS_X:
                        self.raw[0] = ev.value
                    elif ev.code == ec.ABS_Y:
                        self.raw[1] = ev.value
                    elif ev.code == ec.ABS_PRESSURE and not seen_btn:
                        # some drivers only report pressure, not BTN_TOUCH
                        if ev.value > 0 and not self.down:
                            self.down = True
                        elif ev.value == 0 and self.down:
                            self._release()
                elif ev.type == ec.EV_KEY and ev.code == ec.BTN_TOUCH:
                    seen_btn = True
                    if ev.value == 1:
                        self.down = True
                    elif ev.value == 0 and self.down:
                        self._release()
        except Exception as e:
            print(f"touch reader stopped: {e}", flush=True)

    def get_taps(self):
        with self.lock:
            t, self.taps = self.taps, []
        return t
