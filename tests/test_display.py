"""Framebuffer pixel packing: RGB565 and 32-bit BGRX, row stride padding, portrait rotation."""
import os
import tempfile
import unittest

from tests.helpers import ROOT  # noqa: F401

try:
    import numpy as np
    from PIL import Image
    HAVE_DEPS = True
except ImportError:  # dev machine without Pillow/numpy
    HAVE_DEPS = False


@unittest.skipUnless(HAVE_DEPS, "needs Pillow and numpy")
class TestFramebuffer(unittest.TestCase):
    def make(self, fw, fh, bpp, stride, rot):
        from prayerpet.display import FramebufferDisplay
        fd, path = tempfile.mkstemp()
        os.write(fd, b"\0" * stride * fh)
        os.close(fd)
        d = FramebufferDisplay.__new__(FramebufferDisplay)  # skip device detection
        d.fb_w, d.fb_h, d.bpp, d.stride, d.rotate = fw, fh, bpp, stride, rot
        d.f = open(path, "r+b", buffering=0)
        d.notes, d._tty = [], None
        self.addCleanup(os.remove, path)
        self.addCleanup(d.f.close)
        return d, path

    def frame(self):
        img = Image.new("RGB", (320, 240), (255, 0, 0))
        img.putpixel((0, 0), (0, 255, 0))
        return img

    def test_rgb565(self):
        d, path = self.make(320, 240, 16, 640, 0)
        d.show(self.frame())
        px = np.frombuffer(open(path, "rb").read(), "<u2").reshape(240, 320)
        self.assertEqual(px[120, 160], 0xF800)  # red
        self.assertEqual(px[0, 0], 0x07E0)      # green

    def test_stride_padding(self):
        d, path = self.make(320, 240, 16, 768, 0)
        d.show(self.frame())
        self.assertEqual(len(open(path, "rb").read()), 768 * 240)

    def test_32bpp_bgrx(self):
        d, path = self.make(320, 240, 32, 1280, 0)
        d.show(self.frame())
        data = open(path, "rb").read()
        off = 120 * 1280 + 160 * 4
        self.assertEqual(tuple(data[off:off + 3]), (0, 0, 255))  # B, G, R of red

    def test_portrait_framebuffer_rotates(self):
        d, path = self.make(240, 320, 16, 480, 90)
        d.show(self.frame())
        self.assertEqual(len(open(path, "rb").read()), 480 * 320)


if __name__ == "__main__":
    unittest.main()
