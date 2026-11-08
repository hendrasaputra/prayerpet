"""Output backends: Linux framebuffer (the PiTFT), PNG files (testing) and a desktop window (pygame)."""
import glob
import os

import numpy as np
from PIL import Image

W, H = 320, 240


def _sys(fb, attr):
    try:
        with open(f"/sys/class/graphics/{fb}/{attr}") as f:
            return f.read().strip()
    except Exception:
        return ""


def find_framebuffer(preferred="auto"):
    """Pick the TFT framebuffer. 'auto' = the one whose size is 320x240 or 240x320."""
    if preferred and preferred != "auto":
        return preferred
    candidates = sorted(glob.glob("/dev/fb[0-9]*"))
    for dev in candidates:
        fb = os.path.basename(dev)
        size = _sys(fb, "virtual_size").replace(" ", "")
        if size in ("320,240", "240,320"):
            return dev
    if "/dev/fb1" in candidates:
        return "/dev/fb1"
    return candidates[0] if candidates else None


class FramebufferDisplay:
    def __init__(self, device="auto", rotate=0):
        self.dev = find_framebuffer(device)
        if not self.dev or not os.path.exists(self.dev):
            raise RuntimeError("No framebuffer found. Is the PiTFT overlay loaded? Try: ls /dev/fb*")
        fb = os.path.basename(self.dev)
        size = _sys(fb, "virtual_size") or "320,240"
        self.fb_w, self.fb_h = (int(v) for v in size.split(","))
        self.bpp = int(_sys(fb, "bits_per_pixel") or 16)
        stride = _sys(fb, "stride")
        self.stride = int(stride) if stride else self.fb_w * self.bpp // 8
        # if the framebuffer is portrait but we draw landscape, turn the image
        self.rotate = int(rotate) % 360
        if self.rotate == 0 and self.fb_w < self.fb_h:
            self.rotate = 90
        self.f = open(self.dev, "r+b", buffering=0)
        self.name = _sys(fb, "name")
        self.notes = []
        self._tty = None
        self._console_off()
        self.wake()

    # The text console shares this screen. Put it in graphics mode so it stops drawing,
    # blinking its cursor and blanking the screen. Needs CAP_SYS_TTY_CONFIG (set in the service).
    def _console_off(self):
        import fcntl
        for tty in ("/dev/tty1", "/dev/tty0"):
            try:
                fd = os.open(tty, os.O_WRONLY | os.O_NOCTTY)
                fcntl.ioctl(fd, 0x4B3A, 1)  # KDSETMODE KD_GRAPHICS
                self._tty = fd
                self.notes.append(f"console on {tty} paused")
                return
            except OSError as e:
                self.notes.append(f"console pause on {tty} failed: {e.strerror}")

    def _console_on(self):
        import fcntl
        if self._tty is not None:
            try:
                fcntl.ioctl(self._tty, 0x4B3A, 0)  # KDSETMODE KD_TEXT
                os.close(self._tty)
            except OSError:
                pass
            self._tty = None

    def wake(self):
        """Make sure the display is switched on and showing this framebuffer."""
        import fcntl
        import struct
        try:
            buf = bytearray(160)
            fcntl.ioctl(self.f, 0x4600, buf)              # FBIOGET_VSCREENINFO
            struct.pack_into("<II", buf, 16, 0, 0)        # xoffset, yoffset = 0
            struct.pack_into("<I", buf, 84, 128)          # activate = FB_ACTIVATE_FORCE
            fcntl.ioctl(self.f, 0x4601, buf)              # FBIOPUT_VSCREENINFO
        except OSError as e:
            self.notes.append(f"mode set failed: {e.strerror}")
        try:
            fcntl.ioctl(self.f, 0x4611, 0)                # FBIOBLANK: unblank
        except OSError:
            pass

    def describe(self):
        return (f"{self.dev} ({self.name}) {self.fb_w}x{self.fb_h} {self.bpp}bpp stride={self.stride} "
                f"rotate={self.rotate} | " + "; ".join(self.notes))

    def show(self, img: Image.Image):
        if self.rotate:
            img = img.rotate(self.rotate, expand=True)
        if img.size != (self.fb_w, self.fb_h):
            img = img.resize((self.fb_w, self.fb_h))
        a = np.asarray(img.convert("RGB"), dtype=np.uint16)
        if self.bpp == 16:
            px = ((a[..., 0] >> 3) << 11) | ((a[..., 1] >> 2) << 5) | (a[..., 2] >> 3)
            row = px.astype("<u2")
        elif self.bpp == 32:
            a8 = a.astype(np.uint8)
            row = np.dstack([a8[..., 2], a8[..., 1], a8[..., 0], np.full(a8.shape[:2], 255, np.uint8)])
        else:
            raise RuntimeError(f"Unsupported framebuffer depth {self.bpp} bpp")
        data = row.tobytes()
        line = self.fb_w * self.bpp // 8
        if self.stride != line:
            pad = b"\x00" * (self.stride - line)
            data = b"".join(data[i:i + line] + pad for i in range(0, len(data), line))
        self.f.seek(0)
        self.f.write(data)

    def clear(self):
        self.show(Image.new("RGB", (W, H), (0, 0, 0)))

    def close(self):
        self._console_on()
        try:
            self.f.close()
        except Exception:
            pass


class PngDisplay:
    """Writes every frame (or only the latest) to PNG. For testing without a screen."""

    def __init__(self, path):
        self.path = path
        self.n = 0

    def describe(self):
        return f"PNG -> {self.path}"

    def show(self, img):
        if "{n}" in self.path:
            img.save(self.path.format(n=self.n))
        else:
            img.save(self.path)
        self.n += 1

    def clear(self):
        pass

    def close(self):
        pass


class WindowDisplay:
    """Desktop preview window (for developing on a Mac/PC). Needs: pip install pygame."""

    def __init__(self, scale=2):
        import pygame
        self.pg = pygame
        pygame.init()
        self.scale = scale
        self.screen = pygame.display.set_mode((W * scale, H * scale))
        pygame.display.set_caption("Prayer Pet")
        self.taps = []
        self.quit = False

    def describe(self):
        return "desktop window"

    def show(self, img):
        pg = self.pg
        for ev in pg.event.get():
            if ev.type == pg.QUIT:
                self.quit = True
            elif ev.type == pg.MOUSEBUTTONUP:
                self.taps.append((ev.pos[0] // self.scale, ev.pos[1] // self.scale))
        surf = pg.image.fromstring(img.convert("RGB").tobytes(), img.size, "RGB")
        if self.scale != 1:
            surf = pg.transform.scale(surf, (W * self.scale, H * self.scale))
        self.screen.blit(surf, (0, 0))
        pg.display.flip()

    def get_taps(self):
        t, self.taps = self.taps, []
        return t

    def clear(self):
        pass

    def close(self):
        self.pg.quit()
