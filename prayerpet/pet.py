"""The creature: saved stats, mood, and pixel-art drawing."""
import json
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

S = 5  # one pixel-art cell = 5 screen pixels, for the pet AND everything drawn around it

# Art around the pet, in cells. Letters map to colours in PetAnimator.
HEART = ["X.X", "XXX", ".X."]
BOWL = [".X.X.", "WWWWW", "BBBBB", ".BBB."]            # inside the thought bubble
BOWL_FED = [".X..X.", "WWWWWW", "BBBBBB", ".BBBB."]    # in front of the pet while it eats
THOUGHT = [".DDDDD.", "D.....D", "D.....D", "D.....D", "D.....D", ".DDDDD."]
Z_SMALL = ["XXX", "..X", ".X.", "XXX"]
Z_BIG = ["XXXX", "..X.", ".X..", "XXXX"]
BANG = ["X", "X", "X", ".", "X"]
# open umbrella: columns -1..16 (two cells wider than the pet), rows -6..-1 above the sprite
UMBRELLA = [
    "........HH........",
    "....UUUUUUUUUU....",
    "..UULUUUUUUUUDUU..",
    ".UULUUUUUUUUUUDUU.",
    "UUUUUUUUUUUUUUUUUU",
    "UU..UU..UU..UU..UU",
]
# folded umbrella standing beside the pet (used while the speech bubble needs the space above)
UMBRELLA_SHUT = [".H", ".U", ".U", ".U", ".D", ".U", ".H", ".H", ".H", ".H", "HH"]


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
    """Keeps short-lived animation state: position, blinking, reactions.

    Everything is drawn in cells of S x S screen pixels on one grid that starts at the pet area's corner,
    so the pet, its umbrella, rain, hearts and Zz always share the same pixel size and line up.
    """

    def __init__(self, area, colors):
        self.ax, self.ay, self.aw, self.ah = area
        self.cols = self.aw // S                 # area width in cells (32)
        self.c = colors
        self.scale = S
        self.place(bubble=False)
        self.x = self.ax + (self.cols - GRID_W) // 2 * S
        self.target_x = self.x
        self.next_blink = time.time() + 3
        self.blink_until = 0
        self.reaction = None  # ("heart"|"food", until)
        self.next_wander = time.time() + 4
        self.facing = 0  # -1 left, 0 centre, 1 right
        self.rain = False

    def place(self, bubble=False, rain=False):
        """Sprite top row: room above for Zz / "!" / the umbrella, or lower under a speech bubble."""
        self.top = self.ay + S * (13 if bubble else 10 if rain else 7)
        self.bubble = bubble

    def react(self, kind, seconds=2.0):
        self.reaction = (kind, time.time() + seconds)

    def hit(self, x, y):
        return (self.x - 10 <= x <= self.x + GRID_W * S + 10
                and self.top - 10 <= y <= self.top + GRID_H * S + 10)

    def draw(self, img, mood, t=None, rain=False, mask=False):
        t = t or time.time()
        d = ImageDraw.Draw(img)
        if rain != self.rain:
            self.rain = rain
            self.place(self.bubble, rain)

        # wander when awake and idle (whole cells; keep one cell clear of the area edges for the umbrella)
        lo, hi = self.ax + S, self.ax + (self.cols - GRID_W - 2) * S
        if mood in ("idle", "hungry", "sad") and t > self.next_wander:
            self.target_x = self.ax + random.randint(1, self.cols - GRID_W - 2) * S
            self.next_wander = t + random.uniform(4, 9)
        if mood in ("sleep", "alert", "prayer"):
            self.target_x = self.ax + (self.cols - GRID_W) // 2 * S
        self.target_x = max(lo, min(hi, self.target_x))
        dx = self.target_x - self.x
        if abs(dx) > 1:
            step = 3 if mood != "hungry" else 1
            self.x += max(-step, min(step, dx))
            self.facing = 1 if dx > 0 else -1
        else:
            self.facing = 0

        # vertical motion, in whole cells
        frame = int(t * 4)
        reacting = self.reaction and t < self.reaction[1]
        if mood == "alert" or (reacting and self.reaction[0] == "heart"):
            hop = -1 if frame % 2 else 0
        elif self.facing:
            hop = -1 if frame % 4 == 0 else 0
        else:
            hop = 0
        ox = self.ax + int(round((self.x - self.ax) / S)) * S
        oy = self.top + hop * S
        ground = (self.top - self.ay) // S + GRID_H   # cell row just under the feet

        if rain:
            self._rain(d, ox, ground, t)
        # shadow on the ground, narrower while in the air
        sw = 10 if hop == 0 else 8
        self._px(d, ox, self.top, (GRID_W - sw) // 2, GRID_H, self.c["shadow"], sw, 1)

        body = self.c["pet_sleep"] if mood == "sleep" else (self.c["pet_hungry"] if mood == "hungry" else self.c["pet"])
        palette = {"X": self.c["pet_outline"], "o": body, "s": self.c["leaf"], "t": self.c["leaf_dark"],
                   "f": self.c["pet_outline"]}
        rows = list(BODY)
        if mood in ("hungry", "sad"):  # leaf droops
            rows[0] = "................"
            rows[1] = "........tss....."
        shuffle = self.facing and frame % 2
        for gy, row in enumerate(rows):
            for gx, ch in enumerate(row):
                col = palette.get(ch)
                if col:
                    fx = (1 if gx < 8 else -1) if (ch == "f" and shuffle) else 0   # feet step inward
                    self._px(d, ox, oy, gx + fx, gy, col)

        self._face(d, ox, oy, mood, t)
        if mask and mood != "sleep":
            self._mask(d, ox, oy)
        self._extras(d, ox, oy, mood, t, rain)
        if rain:
            self._umbrella(d, ox, oy)
        self._reaction(d, ox, oy, t)

    # ------------------------------------------------------------------
    def _px(self, d, ox, oy, gx, gy, col, w=1, h=1):
        d.rectangle([ox + gx * S, oy + gy * S, ox + (gx + w) * S - 1, oy + (gy + h) * S - 1], fill=col)

    def _art(self, d, ox, oy, gx, gy, grid, colmap):
        for ry, row in enumerate(grid):
            for rx, ch in enumerate(row):
                col = colmap.get(ch)
                if col:
                    self._px(d, ox, oy, gx + rx, gy + ry, col)

    def _face(self, d, ox, oy, mood, t):
        ink, white, cheek = self.c["pet_outline"], (255, 255, 255), self.c["cheek"]
        look = self.facing  # eyes shift 1 cell toward walking direction
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

    def _rain(self, d, ox, ground, t):
        """Falling drops, 1x2 cells, on the area grid. None over the pet (it is under its umbrella)."""
        col = self.c.get("rain", (90, 169, 255))
        frame = int(t * 4)
        span = ground - 3
        pet_col = (ox - self.ax) // S
        for i in range(9):
            cx = (i * 7 + 2) % self.cols
            cy = 3 + (i * 5 + frame * 2) % span
            if pet_col - 1 <= cx <= pet_col + GRID_W + 1:
                continue
            self._px(d, self.ax, self.ay, cx, cy, col, 1, 2)

    def _umbrella(self, d, ox, oy):
        """Open umbrella over the head when it rains; folded beside the pet under a speech bubble."""
        col = self.c.get("umbrella", (230, 80, 90))
        cmap = {"U": col, "L": tuple(min(255, v + 45) for v in col), "D": tuple(v * 3 // 4 for v in col),
                "H": (150, 156, 168)}
        if self.bubble:
            self._art(d, ox, oy, GRID_W, 3, UMBRELLA_SHUT, cmap)
            return
        self._art(d, ox, oy, -1, -6, UMBRELLA, cmap)
        self._px(d, ox, oy, GRID_W, 0, cmap["H"], 1, 12)   # shaft down the right side
        self._px(d, ox, oy, GRID_W - 1, 12, cmap["H"])     # hook

    def _extras(self, d, ox, oy, mood, t, rain):
        reacting = self.reaction and t < self.reaction[1]
        frame = int(t * 4)
        if mood == "sleep":
            # Zz up and to the right; to the left when the umbrella covers the space above
            step = (frame // 3) % 3
            small, big = ((-3, 2), (-7, -1)) if rain else ((GRID_W - 3, 0), (GRID_W, -4))
            ink = {"X": self.c["dim"]}
            if step in (0, 1):
                self._art(d, ox, oy, small[0], small[1], Z_SMALL, ink)
            if step in (1, 2):
                self._art(d, ox, oy, big[0], big[1] - (step == 2), Z_BIG, ink)
        elif mood == "alert" and frame % 2 == 0:
            self._art(d, ox, oy, GRID_W + (1 if rain else 0), -4 if not rain else 1, BANG, {"X": self.c["gold"]})
        elif mood == "hungry" and not reacting:
            # thought bubble with a bowl, on whichever side has room
            right = ox + (GRID_W + 8) * S <= self.ax + self.aw
            bx = GRID_W + 1 if right else -8
            by = 2 if rain else -4
            self._art(d, ox, oy, bx, by, THOUGHT, {"D": self.c["dim"]})
            self._px(d, ox, oy, bx + 1, by + 1, self.c["bg"], 5, 4)
            self._art(d, ox, oy, bx + 1, by + 1, BOWL,
                      {"X": self.c["dim"], "W": (240, 240, 230), "B": self.c["bowl"]})
            self._px(d, ox, oy, GRID_W if right else -1, by + 6, self.c["dim"])

    def _reaction(self, d, ox, oy, t):
        if not (self.reaction and t < self.reaction[1]):
            return
        kind, until = self.reaction
        rise = int((2.0 - (until - t)) * 2)     # cells risen so far
        if kind == "heart":   # float up beside the head (above it is the name label)
            self._art(d, ox, oy, -4, 4 - rise, HEART, {"X": self.c["heart"]})
            self._art(d, ox, oy, GRID_W + 1, 5 - rise, HEART, {"X": self.c["heart"]})
        elif kind == "food":
            self._art(d, ox, oy, 5, 12, BOWL_FED, {"X": self.c["dim"], "W": (240, 240, 230), "B": self.c["bowl"]})
