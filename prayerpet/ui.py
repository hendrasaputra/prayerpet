"""Screen layouts: home (pet + prayer list) and status (system monitor). 320x240."""
import os

from PIL import Image, ImageDraw, ImageFont

from .sysinfo import fmt_bytes, fmt_uptime, throttle_text
from .weather import aqi_band, describe

W, H = 320, 240

COLORS = dict(
    bg=(14, 17, 22), panel=(26, 31, 39), line=(44, 51, 62), text=(232, 230, 227), dim=(122, 130, 142),
    gold=(242, 181, 68), gold_bg=(74, 56, 22), teal=(79, 209, 165), teal_bg=(20, 66, 54),
    red=(255, 107, 107), blue=(90, 169, 255),
    pet=(126, 214, 165), pet_hungry=(176, 196, 140), pet_sleep=(96, 150, 140), pet_outline=(24, 40, 36),
    leaf=(120, 200, 80), leaf_dark=(70, 130, 50), cheek=(255, 140, 150), shadow=(8, 10, 13),
    heart=(255, 99, 132), bowl=(205, 120, 70),
    sun=(255, 200, 70), cloud=(200, 208, 220), rain=(90, 169, 255), umbrella=(230, 80, 90),
    aqi=[(79, 209, 165), (242, 201, 76), (255, 150, 60), (255, 90, 90), (175, 110, 230), (170, 50, 70)],
)

NAMES = {
    "id": dict(imsak="Imsak", fajr="Subuh", sunrise="Terbit", dhuha="Dhuha", dhuhr="Dzuhur", jumuah="Jumat",
               asr="Ashar", maghrib="Maghrib", isha="Isya"),
    "en": dict(imsak="Imsak", fajr="Fajr", sunrise="Sunrise", dhuha="Duha", dhuhr="Dhuhr", jumuah="Jumu'ah",
               asr="Asr", maghrib="Maghrib", isha="Isha"),
}
DAYS = {"id": ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"], "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
MONTHS = {"id": ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
          "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]}
TEXT = {
    "id": dict(in_="dalam", soon="lagi", now="Waktu", sleeping="sedang tidur", day="hari", sessions="sesi",
               connected="terhubung", on="Aktif", off="Mati", none="tidak ada", unsynced="jam belum sinkron"),
    "en": dict(in_="in", soon="to go", now="Time for", sleeping="is asleep", day="days", sessions="sessions",
               connected="connected", on="On", off="Off", none="none", unsynced="clock not synced"),
}

PX = 5  # pixel-art cell size, the same as the pet (pet.S)

# Weather icons as pixel art. Y sun/moon, C cloud, c cloud shade, D dark cloud, d dark shade, R rain, W snow,
# B lightning. Big icons are 12x10 cells, small ones 5x4 cells.
_CLOUD = ["......CCC...", "..CCC.CCCCC.", ".CCCCCCCCCC.", "CCCCCCCCCCCC", "CCCCCCCCCCCC", ".cccccccccc."]
_DARK = [r.replace("C", "D").replace("c", "d") for r in _CLOUD]
ICONS_BIG = dict(
    clear=["....Y..Y....", ".Y........Y.", "....YYYY....", "...YYYYYY...", "YY.YYYYYY.YY",
           "...YYYYYY...", "....YYYY....", ".Y........Y.", "....Y..Y....", "............"],
    night=["....YYYY....", "...YYY......", "..YYY.......", "..YY........", "..YY........",
           "..YYY.......", "...YYY......", "....YYYY....", "............", "............"],
    partly=["......Y..Y..", "........YY..", ".......YYYY.", "....CCYYYYYY", "..CCCCCYYY..",
            ".CCCCCCCC...", "CCCCCCCCCCC.", "CCCCCCCCCCC.", ".ccccccccc..", "............"],
    cloud=["............", "............"] + _CLOUD + ["............", "............"],
    fog=_CLOUD + ["............", "CCCCCCCC....", "............", "...CCCCCCCCC"],
    drizzle=_DARK + ["............", "...R....R...", "............", "......R....."],
    rain=_DARK + ["............", "..R..R..R...", ".R..R..R....", "R..R..R....."],
    storm=_DARK + ["......BB....", ".....BB.....", "....BBBB....", "......B....."],
    snow=_CLOUD + ["............", "..W...W...W.", "............", "....W...W..."],
)
ICONS_SMALL = dict(
    clear=[".YYY.", "YYYYY", "YYYYY", ".YYY."],
    night=["..YY.", ".YY..", ".YY..", "..YY."],
    partly=["...YY", ".CCYY", "CCCCC", ".ccc."],
    cloud=["..CC.", ".CCCC", "CCCCC", ".ccc."],
    fog=["CCCC.", ".....", ".CCCC", "....."],
    drizzle=[".DD..", "DDDDD", ".....", "..R.."],
    rain=[".DD..", "DDDDD", ".....", "R.R.R"],
    storm=[".DD..", "DDDDD", "..B..", ".B..."],
    snow=[".CC..", "CCCCC", ".....", "W.W.W"],
)

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/Library/Fonts",
             "/System/Library/Fonts/Supplemental"]


def _font(size, bold=False):
    names = ["DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["DejaVuSans.ttf", "Arial.ttf"]
    for d in FONT_DIRS:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default()


class Fonts:
    def __init__(self):
        self.huge = _font(34, True)
        self.clock = _font(22, True)
        self.big = _font(18, True)
        self.row = _font(14)
        self.row_b = _font(14, True)
        self.small = _font(12)
        self.small_b = _font(12, True)
        self.tiny = _font(10)


def fmt_dur(seconds, lang):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m = (rem + 59) // 60 if seconds < 3600 else rem // 60
    if seconds < 60:
        return "<1m" if lang == "en" else "<1 mnt"
    unit_h, unit_m = ("h", "m") if lang == "en" else ("j", "m")
    return f"{h}{unit_h} {m:02d}{unit_m}" if h else f"{m} {('min' if lang == 'en' else 'mnt')}"


def fmt_time(dt, h24=True):
    return dt.strftime("%H:%M") if h24 else dt.strftime("%I:%M").lstrip("0")


class Renderer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.f = Fonts()
        self.c = COLORS
        self.lang = cfg["prayer"].get("language", "id")
        if self.lang not in NAMES:
            self.lang = "en"
        self.names = NAMES[self.lang]
        self.t = TEXT[self.lang]
        self.h24 = cfg["screen"].get("clock_24h", True)
        self.pet_area = (0, 32, 160, 164)

    def pname(self, key, when=None):
        if key == "dhuhr" and when is not None and when.weekday() == 4:
            return self.names["jumuah"]
        return self.names.get(key, key)

    # ---------------------------------------------------------- pieces
    def _top_bar(self, d, now, info, title=None):
        c, f = self.c, self.f
        d.rectangle([0, 0, W, 30], fill=c["panel"])
        if title:
            d.text((8, 6), title, font=f.big, fill=c["text"])
        else:
            clk = fmt_time(now, self.h24)
            d.text((8, 3), clk, font=f.clock, fill=c["text"])
            dx = 8 + d.textlength(clk, font=f.clock) + 8
            date_s = f"{DAYS[self.lang][now.weekday()]} {now.day} {MONTHS[self.lang][now.month - 1]}"
            d.text((dx, 11), date_s, font=f.small, fill=c["dim"])
            ex = dx + d.textlength(date_s, font=f.small) + 6
            if not info.get("time_synced", True):
                d.text((ex - 2, 9), "!", font=f.small_b, fill=c["red"])
                ex += 8
            wx = info.get("wx") or {}
            if wx.get("temp") is not None:
                tt = f"{round(wx['temp'])}°"
                d.text((ex + 2, 9), tt, font=f.small_b, fill=c["text"])
                ex += d.textlength(tt, font=f.small_b) + 6
            if wx.get("aqi") is not None:
                band = aqi_band(wx["aqi"])[0]
                at = f"{round(wx['aqi'])}"
                tw = d.textlength(at, font=f.tiny)
                d.rounded_rectangle([ex, 9, ex + tw + 10, 23], radius=7, fill=c["aqi"][band])
                d.text((ex + 5 + tw / 2, 16), at, font=f.tiny, fill=c["bg"], anchor="mm")
        # status icons (right)
        x = W - 8
        # SSH
        users = info.get("users", [])
        remote = [u for u in users if u["src"] != "local"]
        ssh_col = c["teal"] if remote else (c["dim"] if info.get("ssh_on") else c["red"])
        x -= 22
        d.text((x, 9), ">_", font=f.small_b, fill=ssh_col)
        if remote:
            d.text((x + 15, 3), str(len(remote)), font=f.tiny, fill=ssh_col)
        # Bluetooth rune
        x -= 16
        bt_col = c["blue"] if info.get("bt_connected") else (c["dim"] if info.get("bt_on") else c["line"])
        bx, by = x + 5, 8
        d.line([bx - 4, by + 4, bx + 4, by + 11, bx, by + 15, bx, by, bx + 4, by + 4, bx - 4, by + 11],
               fill=bt_col, width=2)
        # Wi-Fi bars
        x -= 24
        pct = info.get("wifi_pct")
        n = 0 if pct is None else (1 + (pct >= 35) + (pct >= 55) + (pct >= 75))
        for i in range(4):
            hgt = 4 + i * 3
            col = (c["teal"] if n >= 3 else c["gold"] if n == 2 else c["red"]) if i < n else c["line"]
            d.rectangle([x + i * 5, 22 - hgt, x + i * 5 + 3, 22], fill=col)
        if pct is None:
            d.line([x, 8, x + 18, 22], fill=c["red"], width=2)

    def _bar(self, d, x, y, w, h, frac, col):
        d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=self.c["line"])
        fw = max(0, min(w, int(w * frac)))
        if frac > 0.01:
            fw = max(fw, h)
            d.rounded_rectangle([x, y, x + fw, y + h], radius=h // 2, fill=col)

    def _setup_bar(self, d, ws, y0):
        """Shown instead of the prayer countdown while the Wi-Fi setup hotspot is on."""
        c, f = self.c, self.f
        import getpass
        d.rectangle([0, y0, W, H], fill=c["gold_bg"])
        if ws.get("state") == "switching":
            msg = f"Menyambung ke {ws.get('target', '')}..." if self.lang == "id" else f"Joining {ws.get('target', '')}..."
            d.text((10, y0 + (H - y0) // 2), msg[:40], font=f.row_b, fill=c["gold"], anchor="lm")
            return
        l1 = f"Wi-Fi: {ws.get('ssid', '')}   pw: {ws.get('pass', '')}"
        l2 = f"ssh {getpass.getuser()}@{ws.get('ip', '10.42.0.1')}  ·  sudo wifi-join"
        d.text((8, y0 + 3), l1, font=f.small_b, fill=c["gold"])
        d.text((8, H - 16), l2, font=f.small, fill=c["text"])

    def _bottom_bar(self, d, now, sched, y0=200):
        c, f, t = self.c, self.f, self.t
        ws = getattr(self, "_wifi_setup", {}) or {}
        if ws.get("state") in ("ap", "switching"):
            return self._setup_bar(d, ws, y0)
        nxt, prev = sched["next"], sched["prev"]
        state = sched["state"]
        bg = c["panel"]
        if state == "alert":
            bg = c["gold_bg"]
        elif state == "prayer":
            bg = c["teal_bg"]
        d.rectangle([0, y0, W, H], fill=bg)
        if state == "prayer":
            key, when = sched["current"]
            msg = f"{t['now']} {self.pname(key, when)}"
            d.text((10, y0 + 9), msg, font=f.big, fill=c["teal"])
            d.text((W - 10, y0 + 13), fmt_time(when, self.h24), font=f.row, fill=c["text"], anchor="ra")
            return
        key, when = nxt
        left = (when - now).total_seconds()
        name = self.pname(key, when)
        col = c["gold"] if state == "alert" else c["text"]
        d.text((10, y0 + 6), f"{name} {fmt_time(when, self.h24)}", font=f.big, fill=col)
        d.text((W - 10, y0 + 9), f"{t['in_']} {fmt_dur(left, self.lang)}" if self.lang == "en"
               else f"{fmt_dur(left, self.lang)} {t['soon']}", font=f.row_b, fill=col, anchor="ra")
        if prev:
            span = (when - prev[1]).total_seconds()
            frac = 1 - left / span if span > 0 else 0
            self._bar(d, 10, y0 + 31, W - 20, 4, frac, c["gold"] if state == "alert" else c["teal"])

    # ---------------------------------------------------------- pages
    def home(self, now, sched, info, pet_state, animator, mood):
        self._wifi_setup = info.get("wifi_setup") or {}
        c, f = self.c, self.f
        img = Image.new("RGB", (W, H), c["bg"])
        d = ImageDraw.Draw(img)
        self._top_bar(d, now, info)

        # pet area
        name = pet_state["name"]
        age = pet_state.age_days()
        d.text((8, 36), name, font=f.small_b, fill=c["text"])
        d.text((8 + d.textlength(name, font=f.small_b) + 5, 37), f"{age} {self.t['day']}", font=f.tiny, fill=c["dim"])
        wx = info.get("wx") or {}
        fresh = wx.get("weather_at") and (now.timestamp() - wx["weather_at"]) < 3 * 3600
        animator.draw(img, mood, rain=bool(fresh and wx.get("code") is not None and describe(wx["code"])[0]
                                           in ("drizzle", "rain", "storm")),
                      mask=bool(wx.get("aqi") is not None and wx["aqi"] > 150))
        d = ImageDraw.Draw(img)
        # meters
        y = 184
        x = 8
        for lbl, valv, col in ((("makan" if self.lang == "id" else "food"), pet_state["hunger"], c["bowl"]),
                               (("senang" if self.lang == "id" else "joy"), pet_state["happy"], c["heart"])):
            d.text((x, y + 4), lbl, font=f.tiny, fill=c["dim"], anchor="lm")
            x += int(d.textlength(lbl, font=f.tiny)) + 4
            self._bar(d, x, y + 1, 30, 6, valv / 100, col if valv > 25 else c["red"])
            x += 30 + 10

        # prayer list
        x0, x1, y = 166, W - 6, 36
        d.line([162, 34, 162, 196], fill=c["line"])
        rows = sched["today"]
        row_h = max(20, min(23, 160 // max(1, len(rows))))
        for key, when in rows:
            is_next = sched["next"] == (key, when)
            is_now = sched["state"] == "prayer" and sched["current"] == (key, when)
            past = when <= now and not is_now
            if is_next:
                d.rounded_rectangle([x0 - 2, y, x1, y + row_h - 2], radius=5, fill=c["gold_bg"])
            if is_now:
                d.rounded_rectangle([x0 - 2, y, x1, y + row_h - 2], radius=5, fill=c["teal_bg"])
            col = c["gold"] if is_next else c["teal"] if is_now else c["dim"] if past else c["text"]
            fnt = f.row_b if (is_next or is_now) else f.row
            ty = y + (row_h - 2) // 2
            d.text((x0 + 4, ty), self.pname(key, when), font=fnt, fill=col, anchor="lm")
            d.text((x1 - 5, ty), fmt_time(when, self.h24), font=fnt, fill=col, anchor="rm")
            y += row_h

        self._bottom_bar(d, now, sched)
        return img

    def status(self, now, sched, info):
        self._wifi_setup = info.get("wifi_setup") or {}
        c, f, t = self.c, self.f, self.t
        img = Image.new("RGB", (W, H), c["bg"])
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 30], fill=c["panel"])
        d.text((8, 6), info.get("hostname", "pi"), font=f.big, fill=c["text"])
        d.text((W - 8, 15), info.get("ip", "-"), font=f.row_b, fill=c["teal"], anchor="rm")

        y = 37
        LBL = 8
        VAL = 52
        rh = 20

        def label(txt):
            d.text((LBL, y + rh // 2), txt, font=f.small_b, fill=c["dim"], anchor="lm")

        def val(txt, x=VAL, col=None, fnt=None):
            d.text((x, y + rh // 2), txt, font=fnt or f.small, fill=col or c["text"], anchor="lm")

        def lvl(frac):
            return c["teal"] if frac < 0.6 else c["gold"] if frac < 0.85 else c["red"]

        # CPU + temp
        cpu = info.get("cpu", 0) / 100
        label("CPU")
        self._bar(d, VAL, y + 7, 120, 7, cpu, lvl(cpu))
        val(f"{info.get('cpu', 0):4.0f}%", x=VAL + 128)
        temp = info.get("temp")
        if temp is not None:
            tc = c["teal"] if temp < 60 else c["gold"] if temp < 75 else c["red"]
            d.text((W - 8, y + rh // 2), f"{temp:.0f}°C", font=f.small_b, fill=tc, anchor="rm")
        y += rh
        # RAM
        tot = info.get("ram_total") or 1
        fr = info.get("ram_used", 0) / tot
        label("RAM")
        self._bar(d, VAL, y + 7, 120, 7, fr, lvl(fr))
        val(f"{fmt_bytes(info.get('ram_used', 0))} / {fmt_bytes(tot)}", x=VAL + 128)
        y += rh
        # Disk
        tot = info.get("disk_total") or 1
        fr = info.get("disk_used", 0) / tot
        label("Disk")
        self._bar(d, VAL, y + 7, 120, 7, fr, lvl(fr))
        val(f"{fmt_bytes(info.get('disk_used', 0))} / {fmt_bytes(tot)}", x=VAL + 128)
        y += rh
        # Wi-Fi
        label("WiFi")
        ssid = info.get("wifi_ssid")
        if (info.get("wifi_setup") or {}).get("state") == "ap":
            val(("setup hotspot: " if self.lang == "en" else "hotspot setup: ") + info["wifi_setup"].get("ssid", ""),
                col=c["gold"], fnt=f.small_b)
        elif ssid:
            pct = info.get("wifi_pct") or 0
            val(ssid[:16], fnt=f.small_b)
            d.text((W - 8, y + rh // 2), f"{info.get('wifi_dbm')} dBm  {pct}%", font=f.small,
                   fill=lvl(1 - pct / 100), anchor="rm")
        else:
            val(t["off"] if self.lang == "en" else "tidak terhubung", col=c["red"])
        y += rh
        # Bluetooth
        label("BT")
        if info.get("bt_on"):
            val(f"{t['on']} · {info.get('bt_connected', 0)} {t['connected']}",
                col=c["blue"] if info.get("bt_connected") else c["text"])
        else:
            val(t["off"], col=c["dim"])
        y += rh
        # SSH + who is logged in
        label("SSH")
        remote = [u for u in info.get("users", []) if u["src"] != "local"]
        if not info.get("ssh_on"):
            val(t["off"], col=c["red"])
        elif remote:
            txt = f"{remote[0]['name']}@{remote[0]['src']}"
            if len(remote) > 1:
                txt += f" +{len(remote) - 1}"
            val(txt[:34], col=c["teal"])
        else:
            val(f"{t['on']} · {t['none']}" if self.lang == "en" else "Aktif · tidak ada sesi")
        y += rh
        # Tailscale
        label("Tail")
        ts = info.get("tailscale") or {}
        if not ts.get("installed"):
            val("not installed" if self.lang == "en" else "belum dipasang", col=c["dim"])
        elif ts.get("state") == "Running":
            val(ts.get("ip") or "-", col=c["teal"], fnt=f.small_b)
            d.text((W - 8, y + rh // 2), f"{ts.get('peers_online', 0)} online", font=f.small, fill=c["text"],
                   anchor="rm")
        elif ts.get("state") == "NeedsLogin":
            val("login needed: sudo tailscale up" if self.lang == "en" else "perlu login: sudo tailscale up",
                col=c["gold"])
        else:
            val(str(ts.get("state") or t["off"]), col=c["dim"])
        y += rh
        # Uptime / load / power
        label("Up")
        val(f"{fmt_uptime(info.get('uptime', 0))} · load {info.get('load', 0):.2f}")
        thr = info.get("throttled")
        ttxt = throttle_text(thr)
        d.text((W - 8, y + rh // 2), f"pwr {ttxt}",
               font=f.small_b, fill=c["teal"] if thr == 0 else c["red"] if thr else c["dim"], anchor="rm")
        y += rh

        self._bottom_bar(d, now, sched, y0=206)
        return img

    # ---------------------------------------------------------- speech bubble
    def _wrap(self, d, text, font, width):
        lines, cur = [], ""
        for word in text.split():
            trial = (cur + " " + word).strip()
            if d.textlength(trial, font=font) <= width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                while d.textlength(word, font=font) > width:  # very long word
                    cut = len(word)
                    while cut > 1 and d.textlength(word[:cut], font=font) > width:
                        cut -= 1
                    lines.append(word[:cut])
                    word = word[cut:]
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def speech(self, img, text, t, pet_x):
        """Speech bubble above the pet. Long messages flip through pages of 3 lines every 4 seconds."""
        c, f = self.c, self.f
        d = ImageDraw.Draw(img)
        x0, x1, y0 = 6, W - 6, 36
        lines = self._wrap(d, text, f.small_b, x1 - x0 - 34)
        pages = [lines[i:i + 3] for i in range(0, len(lines), 3)] or [[""]]
        page = pages[int(t // 4) % len(pages)]
        h = 10 + 16 * len(page)
        d.rounded_rectangle([x0, y0, x1, y0 + h], radius=10, fill=(245, 242, 232), outline=c["gold"], width=2)
        tx = max(x0 + 20, min(pet_x + 40, x1 - 40))
        d.polygon([(tx - 8, y0 + h - 1), (tx + 8, y0 + h - 1), (tx - 2, y0 + h + 12)], fill=(245, 242, 232))
        d.line([(tx - 8, y0 + h), (tx - 2, y0 + h + 12), (tx + 8, y0 + h)], fill=c["gold"], width=2)
        y = y0 + 5
        for ln in page:
            d.text((x0 + 10, y), ln, font=f.small_b, fill=(30, 30, 35))
            y += 16
        if len(pages) > 1:
            n = int(t // 4) % len(pages)
            d.text((x1 - 8, y0 + 5), f"{n + 1}/{len(pages)}", font=f.tiny, fill=(120, 120, 120), anchor="ra")
        return img

    # ---------------------------------------------------------- weather
    def weather_icon(self, d, x, y, kind, is_day=True, big=True):
        """Pixel-art weather icon on the pet's 5 px grid: big 12x10 cells, small 5x4 cells."""
        art = (ICONS_BIG if big else ICONS_SMALL)
        grid = art.get(kind if (kind != "clear" or is_day) else "night", art["cloud"])
        sun = self.c["sun"] if is_day else (230, 225, 200)
        cmap = {"Y": sun, "C": self.c["cloud"], "c": (150, 158, 172), "D": (150, 158, 172), "d": (110, 118, 132),
                "R": self.c["rain"], "W": (255, 255, 255), "B": self.c["sun"]}
        x, y = PX * round(x / PX), PX * round(y / PX)
        for gy, row in enumerate(grid):
            for gx, ch in enumerate(row):
                col = cmap.get(ch)
                if col:
                    d.rectangle([x + gx * PX, y + gy * PX, x + gx * PX + PX - 1, y + gy * PX + PX - 1], fill=col)

    def _ago(self, ts, now_ts):
        mins = int((now_ts - ts) // 60)
        if self.lang == "id":
            return "baru saja" if mins < 1 else f"{mins} mnt lalu" if mins < 120 else f"{mins // 60} jam lalu"
        return "just now" if mins < 1 else f"{mins} min ago" if mins < 120 else f"{mins // 60} h ago"

    def weather(self, now, sched, info):
        self._wifi_setup = info.get("wifi_setup") or {}
        c, f = self.c, self.f
        img = Image.new("RGB", (W, H), c["bg"])
        d = ImageDraw.Draw(img)
        self._top_bar(d, now, info)
        wx = info.get("wx") or {}
        id_ = self.lang == "id"
        now_ts = now.timestamp()

        if wx.get("temp") is None:
            msg = "Menunggu data cuaca..." if id_ else "Waiting for weather data..."
            d.text((W // 2, 105), msg, font=f.row_b, fill=c["text"], anchor="mm")
            err = wx.get("weather_error")
            if err:
                d.text((W // 2, 130), err[:48], font=f.tiny, fill=c["red"], anchor="mm")
            self._bottom_bar(d, now, sched)
            return img

        kind, en, idn = describe(wx.get("code"))
        self.weather_icon(d, 10, 40, kind, bool(wx.get("is_day", 1)))
        d.text((76, 34), f"{round(wx['temp'])}°", font=f.huge, fill=c["text"])
        d.text((76, 76), idn if id_ else en, font=f.row_b, fill=c["text"])
        if wx.get("feels") is not None:
            d.text((76, 96), (f"Terasa {round(wx['feels'])}°" if id_ else f"Feels {round(wx['feels'])}°"),
                   font=f.small, fill=c["dim"])
        line = []
        if wx.get("hi") is not None:
            line.append(f"{round(wx['hi'])}°/{round(wx['lo'])}°")
        if wx.get("rain_max") is not None:
            line.append((f"hujan {wx['rain_max']}%" if id_ else f"rain {wx['rain_max']}%"))
        d.text((8, 114), "  ".join(line), font=f.small, fill=c["text"])
        line2 = []
        if wx.get("humidity") is not None:
            line2.append((f"lembap {wx['humidity']}%" if id_ else f"humid {wx['humidity']}%"))
        if wx.get("wind") is not None:
            line2.append((f"angin {round(wx['wind'])} km/j" if id_ else f"wind {round(wx['wind'])} km/h"))
        d.text((8, 130), "  ".join(line2), font=f.small, fill=c["dim"])

        # air quality panel
        px0, px1 = 204, W - 6
        d.rounded_rectangle([px0, 36, px1, 146], radius=8, fill=c["panel"])
        mid = (px0 + px1) // 2
        d.text((mid, 46), "Kualitas udara" if id_ else "Air quality (AQI)", font=f.tiny, fill=c["dim"], anchor="mm")
        if wx.get("aqi") is not None:
            band, ben, bid = aqi_band(wx["aqi"])
            col = c["aqi"][band]
            d.text((mid, 74), f"{round(wx['aqi'])}", font=f.huge, fill=col, anchor="mm")
            d.text((mid, 100), bid if id_ else ben, font=f.tiny, fill=col, anchor="mm")
            if wx.get("pm25") is not None:
                d.text((mid, 116), f"PM2.5 {wx['pm25']:.0f}  PM10 {wx.get('pm10') or 0:.0f}", font=f.tiny,
                       fill=c["text"], anchor="mm")
        else:
            d.text((mid, 80), "-", font=f.huge, fill=c["dim"], anchor="mm")
        if wx.get("weather_at"):
            stale = now_ts - wx["weather_at"] > 2 * 3600
            d.text((mid, 134), self._ago(wx["weather_at"], now_ts), font=f.tiny,
                   fill=c["red"] if stale else c["dim"], anchor="mm")

        # next hours
        hours = wx.get("hours") or []
        if hours:
            d.line([6, 151, W - 6, 151], fill=c["line"])
            colw = (W - 8) / len(hours)
            for i, h in enumerate(hours):
                cx = 4 + colw * i + colw / 2
                d.text((cx, 158), f"{h['time']}:00", font=f.tiny, fill=c["dim"], anchor="mm")
                k = describe(h.get("code"))[0]
                self.weather_icon(d, cx - 12, 165, k, bool(h.get("is_day", 1)), big=False)
                d.text((cx, 192), f"{round(h['temp'])}°" if h.get("temp") is not None else "-", font=f.small_b,
                       fill=c["text"], anchor="rm")
                if h.get("rain") is not None:
                    d.text((cx + 3, 192), f"{h['rain']}%", font=f.tiny,
                           fill=c["rain"] if h["rain"] >= 30 else c["dim"], anchor="lm")

        self._bottom_bar(d, now, sched)
        return img

    # ---------------------------------------------------------- button overlays
    BUTTON_LABELS = {
        "id": dict(page="Halaman", feed="Makan", pat="Elus", screen="Layar", none="-"),
        "en": dict(page="Page", feed="Feed", pat="Pat", screen="Screen", none="-"),
    }

    def button_hints(self, img, edge, actions, pressed=None):
        """Draw one pill per button along the edge where the buttons sit, in physical order."""
        if edge == "none" or not actions:
            return img
        c, f = self.c, self.f
        d = ImageDraw.Draw(img)
        labels = self.BUTTON_LABELS.get(self.lang, self.BUTTON_LABELS["en"])
        n = len(actions)
        horizontal = edge in ("top", "bottom")
        # solid strip so labels stay readable over the page
        if edge == "bottom":
            d.rectangle([0, H - 30, W, H], fill=c["bg"])
        elif edge == "top":
            d.rectangle([0, 0, W, 30], fill=c["bg"])
        elif edge == "left":
            d.rectangle([0, 0, 82, H], fill=c["bg"])
        else:
            d.rectangle([W - 82, 0, W, H], fill=c["bg"])
        for i, (pin, act) in enumerate(actions):
            txt = labels.get(act, act)
            if horizontal:
                slot = W / n
                cx, cy = int(slot * i + slot / 2), (H - 15 if edge == "bottom" else 15)
                bw, bh = int(slot) - 10, 24
            else:
                slot = (H - 8) / n
                cx, cy = (W - 41 if edge == "right" else 41), int(4 + slot * i + slot / 2)
                bw, bh = 76, 28
            hot = pressed == pin
            d.rounded_rectangle([cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2], radius=11,
                                fill=c["gold"] if hot else c["panel"], outline=c["gold"], width=1)
            d.text((cx, cy), txt, font=f.small_b, fill=c["bg"] if hot else c["text"], anchor="mm")
        return img

    def hold_overlay(self, img, progress, seconds_left):
        c, f = self.c, self.f
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([30, 70, W - 30, 170], radius=12, fill=c["panel"], outline=c["red"], width=2)
        title = "Tahan untuk mematikan" if self.lang == "id" else "Keep holding to shut down"
        d.text((W // 2, 95), title, font=f.row_b, fill=c["text"], anchor="mm")
        d.text((W // 2, 125), f"{seconds_left:.0f}", font=f.clock, fill=c["red"], anchor="mm")
        self._bar(d, 50, 150, W - 100, 8, progress, c["red"])
        return img

    def message(self, line1, line2=""):
        c, f = self.c, self.f
        img = Image.new("RGB", (W, H), c["bg"])
        d = ImageDraw.Draw(img)
        d.text((W // 2, H // 2 - 14), line1, font=f.big, fill=c["text"], anchor="mm")
        if line2:
            d.text((W // 2, H // 2 + 16), line2, font=f.row, fill=c["dim"], anchor="mm")
        return img

    def dim(self, img, factor=0.4):
        return img.point(lambda v: int(v * factor))
