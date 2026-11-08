"""The creature: saved stats, mood, and pixel-art drawing."""
import json
import math
import os
import random
import time

from PIL import ImageDraw

# 16x14 body. X = outline, o = body, s = sprout leaf, t = sprout stem, f = feet
BODY = [
    "........ss......",
    ".......sst......",
    "........t.......",
    ".....XXXXXX.....",
    "...XXooooooXX...",
    "..XooooooooooX..",
    ".XooooooooooooX.",
    ".XooooooooooooX.",
    "XooooooooooooooX",
    "XooooooooooooooX",
    "XooooooooooooooX",
    "XooooooooooooooX",
    ".XooooooooooooX.",
    "..XXooooooooXX..",
    "...ff......ff...",
]
GRID_W, GRID_H = 16, len(BODY)

HEART = [".X.X.", "XXXXX", "XXXXX", ".XXX.", "..X.."]
BOWL = ["..X.X..", ".X.X.X.", "WWWWWWW", "BBBBBBB", ".BBBBB.", "..BBB.."]


class PetState:
    def __init__(self, path, name="Nomi"):
        self.path = os.path.expanduser(path)
        now = time.time()
        self.data = dict(name=name, born=now, last=now, hunger=80.0, happy=80.0, feeds=0, pats=0)
        try:
            with open(self.path) as f:
                self.data.update(json.load(f))
        except Exception:
            pass
        self.data["name"] = name or self.data.get("name", "Nomi")
        self._last_save = 0

    def __getitem__(self, k):
        return self.data[k]

    def tick(self, sleeping):
        """Lower hunger/happiness according to elapsed time (also covers time while switched off)."""
        now = time.time()
        dt_h = max(0.0, (now - self.data["last"]) / 3600.0)
        dt_h = min(dt_h, 48.0)
        rate = 0.4 if sleeping else 1.0
        self.data["hunger"] = max(0.0, self.data["hunger"] - 12.0 * dt_h * rate)   # empty in ~8 h awake
        self.data["happy"] = max(0.0, self.data["happy"] - 8.0 * dt_h * rate)      # bored in ~12 h awake
        self.data["last"] = now
        if now - self._last_save > 60:
            self.save()

    def feed(self):
        self.data["hunger"] = min(100.0, self.data["hunger"] + 35)
        self.data["happy"] = min(100.0, self.data["happy"] + 5)
        self.data["feeds"] += 1
        self.save()

    def pat(self):
        self.data["happy"] = min(100.0, self.data["happy"] + 15)
        self.data["pats"] += 1
        self.save()

    def age_days(self):
        return int((time.time() - self.data["born"]) // 86400)

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.data, f)
            os.replace(tmp, self.path)
            self._last_save = time.time()
        except Exception:
            pass


class PetAnimator:
    """Keeps short-lived animation state: position, blinking, reactions."""

    def __init__(self, area, colors):
        self.ax, self.ay, self.aw, self.ah = area
        self.top = self.ay + 36  # sprite top (leaves room for Zz / ! above)
        self.c = colors
        self.scale = 5
        self.x = self.ax + (self.aw - GRID_W * self.scale) // 2
        self.target_x = self.x
        self.next_blink = time.time() + 3
        self.blink_until = 0
        self.reaction = None  # ("heart"|"food", until)
        self.next_wander = time.time() + 4
        self.facing = 0  # -1 left, 0 centre, 1 right

    def react(self, kind, seconds=2.0):
        self.reaction = (kind, time.time() + seconds)

    def hit(self, x, y):
        s = self.scale
        top = self.top
        return self.x - 10 <= x <= self.x + GRID_W * s + 10 and top - 10 <= y <= top + GRID_H * s + 10

    def draw(self, img, mood, t=None, rain=False, mask=False):
        t = t or time.time()
        d = ImageDraw.Draw(img)
        s = self.scale
        sprite_w = GRID_W * s

        # wander when awake and idle
        if mood in ("idle", "hungry", "sad") and t > self.next_wander:
            lo, hi = self.ax + 4, self.ax + self.aw - sprite_w - 4
            self.target_x = random.randint(lo, max(lo, hi))
            self.next_wander = t + random.uniform(4, 9)
        if mood in ("sleep", "alert", "prayer"):
            self.target_x = self.ax + (self.aw - sprite_w) // 2
        dx = self.target_x - self.x
        if abs(dx) > 1:
            step = 3 if mood != "hungry" else 1
            self.x += max(-step, min(step, dx))
            self.facing = 1 if dx > 0 else -1
        else:
            self.facing = 0

        # vertical motion
        reacting = self.reaction and t < self.reaction[1]
        if mood == "sleep":
            bob = int(round(math.sin(t * 1.2)))           # slow breathing
        elif mood == "alert" or (reacting and self.reaction[0] == "heart"):
            bob = -int(abs(math.sin(t * 6)) * 3)          # hopping
        elif self.facing:
            bob = -int(abs(math.sin(t * 8)) * 1.5)        # walking
        else:
            bob = int(round(math.sin(t * 2.5)))           # idle bob
        ox, oy = self.x, self.top + bob * 2

        # falling rain in the background
        if rain:
            for i in range(14):
                rx = self.ax + 6 + (i * 37) % (self.aw - 12)
                ry = self.ay + 18 + int((t * 90 + i * 53) % (self.ah - 48))
                d.line([rx, ry, rx - 2, ry + 6], fill=self.c.get("rain", (90, 169, 255)), width=1)

        # shadow
        sh_w = sprite_w - 20 + (bob * 3)
        cx = ox + sprite_w // 2
        gy = self.top + GRID_H * s + 4
        d.ellipse([cx - sh_w // 2, gy - 3, cx + sh_w // 2, gy + 3], fill=self.c["shadow"])

        body = self.c["pet_sleep"] if mood == "sleep" else (self.c["pet_hungry"] if mood == "hungry" else self.c["pet"])
        palette = {"X": self.c["pet_outline"], "o": body, "s": self.c["leaf"], "t": self.c["leaf_dark"],
                   "f": self.c["pet_outline"]}
        # leaf droops when hungry or sad
        rows = list(BODY)
        if mood in ("hungry", "sad"):
            rows[0] = "................"
            rows[1] = "........tss....."
        for gy_, row in enumerate(rows):
            for gx_, ch in enumerate(row):
                col = palette.get(ch)
                if col:
                    # feet shuffle while walking
                    fx = 0
                    if ch == "f" and self.facing and int(t * 8) % 2:
                        fx = s // 2 * (1 if gx_ < 8 else -1)
                    d.rectangle([ox + gx_ * s + fx, oy + gy_ * s, ox + gx_ * s + fx + s - 1, oy + gy_ * s + s - 1],
                                fill=col)

        self._face(d, ox, oy, mood, t)
        if mask and mood != "sleep":
            self._mask(d, ox, oy)
        self._extras(d, ox, oy, mood, t)
        if rain:
            self._umbrella(d, ox, oy)

    # ------------------------------------------------------------------
    def _px(self, d, ox, oy, gx, gy, col, w=1, h=1):
        s = self.scale
        d.rectangle([ox + gx * s, oy + gy * s, ox + (gx + w) * s - 1, oy + (gy + h) * s - 1], fill=col)

    def _face(self, d, ox, oy, mood, t):
        ink, white, cheek = self.c["pet_outline"], (255, 255, 255), self.c["cheek"]
        look = self.facing  # eyes shift 1 px-cell toward walking direction
        lx, rx, ey = 4 + look, 10 + look, 7
        blinking = t < self.blink_until
        if t > self.next_blink:
            self.blink_until = t + 0.15
            self.next_blink = t + random.uniform(2.5, 6)
        reacting = self.reaction and t < self.reaction[1]

        if mood == "sleep" or mood == "prayer":
            for x in (lx, rx):
                self._px(d, ox, oy, x, ey + 1, ink, 2, 1)
        elif mood == "happy" or (reacting and self.reaction[0] in ("heart", "food")):
            for x in (lx, rx):           # ^ ^
                self._px(d, ox, oy, x, ey + 1, ink)
                self._px(d, ox, oy, x + 1, ey, ink)
                self._px(d, ox, oy, x + 2, ey + 1, ink)
        elif blinking:
            for x in (lx, rx):
                self._px(d, ox, oy, x, ey + 1, ink, 2, 1)
        elif mood == "alert":
            for x in (lx, rx):           # wide eyes
                self._px(d, ox, oy, x, ey - 1, ink, 2, 3)
                self._px(d, ox, oy, x, ey - 1, white)
        else:
            for x in (lx, rx):
                self._px(d, ox, oy, x, ey, ink, 2, 2)
                self._px(d, ox, oy, x, ey, white)
            if mood in ("hungry", "sad"):  # worried brows
                self._px(d, ox, oy, lx + 1, ey - 2, ink)
                self._px(d, ox, oy, lx, ey - 1, ink)
                self._px(d, ox, oy, rx, ey - 2, ink)
                self._px(d, ox, oy, rx + 1, ey - 1, ink)

        # cheeks
        if mood not in ("hungry", "sad"):
            self._px(d, ox, oy, 2 + look, 9, cheek, 2, 1)
            self._px(d, ox, oy, 12 + look, 9, cheek, 2, 1)

        # mouth
        mx = 7 + look
        if mood == "alert":
            self._px(d, ox, oy, mx, 10, ink, 2, 2)
        elif mood in ("hungry", "sad"):
            self._px(d, ox, oy, mx, 10, ink, 2, 1)
            self._px(d, ox, oy, mx - 1, 11, ink)
            self._px(d, ox, oy, mx + 2, 11, ink)
        elif mood == "sleep":
            self._px(d, ox, oy, mx, 10, ink, 2, 1)
        elif reacting and self.reaction[0] == "food" and int(t * 6) % 2:
            self._px(d, ox, oy, mx, 10, ink, 2, 2)   # chewing
        else:
            self._px(d, ox, oy, mx - 1, 10, ink)
            self._px(d, ox, oy, mx, 11, ink, 2, 1)
            self._px(d, ox, oy, mx + 2, 10, ink)

    def _mask(self, d, ox, oy):
        """Face mask when the air is unhealthy (AQI > 150)."""
        white, strap = (235, 240, 245), (180, 190, 200)
        self._px(d, ox, oy, 4, 9, white, 8, 3)
        self._px(d, ox, oy, 4, 10, strap, 8, 1)
        self._px(d, ox, oy, 2, 8, strap, 2, 1)
        self._px(d, ox, oy, 12, 8, strap, 2, 1)

    def _umbrella(self, d, ox, oy):
        """Umbrella held over the head when it rains."""
        s = self.scale
        col = self.c.get("umbrella", (230, 80, 90))
        w = GRID_W * s + 24
        x0, y0 = ox - 12, oy - 22
        d.pieslice([x0, y0, x0 + w, y0 + 44], 180, 360, fill=col)
        for k in range(4):  # scalloped edge
            cx = x0 + w * (k + 0.5) / 4
            d.ellipse([cx - w / 8, y0 + 16, cx + w / 8, y0 + 28], fill=self.c["bg"])
        d.line([x0 + w / 2, y0, x0 + w / 2, y0 - 4], fill=col, width=2)
        hx = ox + GRID_W * s + 3          # handle beside the body, held at the right side
        d.line([x0 + w / 2, y0 + 20, hx, y0 + 26], fill=(200, 200, 200), width=2)
        d.line([hx, y0 + 26, hx, oy + 10 * s], fill=(200, 200, 200), width=2)
        d.arc([hx - 8, oy + 10 * s - 5, hx, oy + 10 * s + 5], 0, 180, fill=(200, 200, 200), width=2)

    def _icon(self, d, x, y, grid, colmap, s=3):
        for gy, row in enumerate(grid):
            for gx, ch in enumerate(row):
                col = colmap.get(ch)
                if col:
                    d.rectangle([x + gx * s, y + gy * s, x + gx * s + s - 1, y + gy * s + s - 1], fill=col)

    def _extras(self, d, ox, oy, mood, t):
        s = self.scale
        top_right = (ox + GRID_W * s - 6, oy + 6)
        reacting = self.reaction and t < self.reaction[1]
        if mood == "sleep":
            for i, (dx, dy, sz) in enumerate([(0, 0, 3), (12, -14, 4), (26, -30, 5)]):
                phase = (t * 0.8 + i * 0.33) % 1.0
                if phase < 0.75:
                    x, y = top_right[0] + dx, top_right[1] + dy - int(phase * 8)
                    self._z(d, x, y, sz, self.c["dim"])
        elif mood == "alert":
            if int(t * 3) % 2 == 0:
                x, y = top_right[0] + 6, oy - 12
                d.rectangle([x, y, x + 5, y + 18], fill=self.c["gold"])
                d.rectangle([x, y + 23, x + 5, y + 28], fill=self.c["gold"])
        elif mood == "hungry" and not reacting:
            bx, by = top_right[0] - 2, oy - 6
            d.ellipse([bx - 4, by + 26, bx + 2, by + 32], outline=self.c["dim"], fill=self.c["bg"])
            d.rounded_rectangle([bx, by - 4, bx + 32, by + 24], radius=6, outline=self.c["dim"], fill=self.c["bg"])
            self._icon(d, bx + 6, by + 1, BOWL, {"X": self.c["dim"], "W": (240, 240, 230), "B": self.c["bowl"]}, s=3)
        if reacting:
            kind, until = self.reaction
            left = until - t
            rise = int((2.0 - left) * 14)
            if kind == "heart":
                for i, dx in enumerate((-18, 10, 34)):
                    self._icon(d, ox + 20 + dx, oy - 4 - rise - i * 6, HEART, {"X": self.c["heart"]}, s=3)
            elif kind == "food":
                self._icon(d, ox + GRID_W * s // 2 - 10, oy + GRID_H * s - 30, BOWL,
                           {"X": self.c["dim"], "W": (240, 240, 230), "B": self.c["bowl"]}, s=3)

    def _z(self, d, x, y, sz, col):
        w = sz * 2
        d.line([x, y, x + w, y], fill=col, width=2)
        d.line([x + w, y, x, y + w], fill=col, width=2)
        d.line([x, y + w, x + w, y + w], fill=col, width=2)
