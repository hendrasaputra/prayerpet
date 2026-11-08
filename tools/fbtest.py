#!/usr/bin/env python3
"""Screen test. Run with: sudo python3 fbtest.py   (stop prayerpet first)"""
import fcntl, os, struct, sys, time
DEV = sys.argv[1] if len(sys.argv) > 1 else "/dev/fb0"
name = open(f"/sys/class/graphics/{os.path.basename(DEV)}/name").read().strip()
w, h = map(int, open(f"/sys/class/graphics/{os.path.basename(DEV)}/virtual_size").read().split(","))
bpp = int(open(f"/sys/class/graphics/{os.path.basename(DEV)}/bits_per_pixel").read())
print(f"{DEV}: {name} {w}x{h} {bpp}bpp")
def color(r, g, b):
    px = struct.pack("<I", (r << 16) | (g << 8) | b) if bpp == 32 else struct.pack("<H", ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
    return px * (w * h)
f = open(DEV, "r+b", buffering=0)
def show(label, data):
    f.seek(0); f.write(data)
    print(f"  {label}"); time.sleep(4)

print("STEP 1: plain write. Screen should turn RED.")
show("red written", color(255, 0, 0))

print("STEP 2: switch display on, unblank, then write. Screen should turn GREEN.")
buf = bytearray(160)
try:
    fcntl.ioctl(f, 0x4600, buf)                    # FBIOGET_VSCREENINFO
    struct.pack_into("<I", buf, 84, 128)           # activate = FB_ACTIVATE_FORCE
    fcntl.ioctl(f, 0x4601, buf)                    # FBIOPUT_VSCREENINFO
    print("  mode set ok")
except OSError as e:
    print("  mode set failed:", e)
try:
    fcntl.ioctl(f, 0x4611, 0); print("  unblank ok")  # FBIOBLANK UNBLANK
except OSError as e:
    print("  unblank failed:", e)
show("green written", color(0, 200, 0))

print("STEP 3: stop the text console drawing, then write. Screen should turn BLUE.")
tty = os.open("/dev/tty1", os.O_WRONLY)
fcntl.ioctl(tty, 0x4B3A, 1)                        # KDSETMODE KD_GRAPHICS
show("blue written", color(0, 0, 255))
fcntl.ioctl(tty, 0x4B3A, 0)                        # back to text mode
os.close(tty)
print("Done. Which colours did you see: red, green, blue?")
