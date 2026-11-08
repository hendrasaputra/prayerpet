"""Telegram bot for the Pi with a fixed set of commands. Standard library only.

Secrets live in ~/.prayerpet-telegram.toml (mode 600):
    token = "123456:ABC..."          # from @BotFather
    allowed_ids = [123456789]        # your Telegram user ID (run: prayerpet --bot-whoami)
The bot ignores everyone else, and only answers in one-to-one chats.
It never runs shell commands; every command below is hard-coded.
"""
import io
import json
import os
import re
import stat
import sys
import time
import tomllib
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import inbox

SECRETS = os.path.expanduser("~/.prayerpet-telegram.toml")
USAGE = os.path.expanduser("~/.prayerpet-bot-usage.json")
WEATHER_CACHE = os.path.expanduser("~/.prayerpet-weather.json")
OBLIGATORY = ["fajr", "dhuhr", "asr", "maghrib", "isha"]

COMMANDS = [
    ("times", "Today's prayer times"),
    ("next", "Next prayer and countdown"),
    ("weather", "Weather and air quality"),
    ("status", "Pi health: CPU, memory, Wi-Fi, Tailscale"),
    ("screen", "Picture of the screen (add: weather or status)"),
    ("pet", "How the pet is doing"),
    ("feed", "Feed the pet"),
    ("pat", "Pat the pet"),
    ("say", "Show a message on the pet screen: /say hello"),
    ("ask", "Ask Gemini a short question (if set up)"),
    ("help", "List commands"),
]


def log(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------ Telegram API
class Telegram:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, method, http_timeout=35, **params):
        data = json.dumps(params).encode()
        req = urllib.request.Request(self.base + method, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=http_timeout) as r:
            res = json.loads(r.read().decode())
        if not res.get("ok"):
            raise RuntimeError(f"Telegram {method}: {res.get('description')}")
        return res["result"]

    def send(self, chat_id, text):
        for i in range(0, max(1, len(text)), 4000):  # Telegram limit is 4096 characters
            self.call("sendMessage", chat_id=chat_id, text=text[i:i + 4000], disable_web_page_preview=True)

    def send_photo(self, chat_id, png_bytes, caption=""):
        boundary = uuid.uuid4().hex
        body = io.BytesIO()

        def field(name, value):
            body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())

        field("chat_id", str(chat_id))
        if caption:
            field("caption", caption)
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"screen.png\"\r\n"
                   f"Content-Type: image/png\r\n\r\n".encode())
        body.write(png_bytes)
        body.write(f"\r\n--{boundary}--\r\n".encode())
        req = urllib.request.Request(self.base + "sendPhoto", data=body.getvalue(),
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            json.loads(r.read().decode())


# ------------------------------------------------------------------ helpers
def load_secrets():
    if not os.path.exists(SECRETS):
        return None
    mode = os.stat(SECRETS).st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        os.chmod(SECRETS, 0o600)
        log(f"Tightened permissions on {SECRETS} to 600")
    with open(SECRETS, "rb") as f:
        s = tomllib.load(f)
    s.setdefault("allowed_ids", [])
    s.setdefault("remind_before_minutes", 10)
    s.setdefault("remind_at_time", True)
    s.setdefault("gemini_api_key", "")
    s.setdefault("gemini_model", "gemini-3.5-flash-lite")
    s.setdefault("ask_daily_limit", 30)
    s["allowed_ids"] = {int(x) for x in s["allowed_ids"]}
    return s


class Context:
    """Everything the commands need, built from the same code the screen uses."""

    def __init__(self, cfg):
        from .app import Schedule, make_calculator
        from .ui import DAYS, MONTHS, NAMES, TEXT
        self.cfg = cfg
        self.tz = ZoneInfo(cfg["location"]["timezone"])
        self.calc = make_calculator(cfg, self.tz)
        self.sched = Schedule(cfg, self.calc)
        self.lang = cfg["prayer"].get("language", "id")
        if self.lang not in NAMES:
            self.lang = "en"
        self.names, self.days, self.months, self.text = NAMES[self.lang], DAYS[self.lang], MONTHS[self.lang], TEXT[self.lang]
        self.id = self.lang == "id"

    def now(self):
        return datetime.now(self.tz)

    def pname(self, key, when):
        if key == "dhuhr" and when.weekday() == 4:
            return self.names["jumuah"]
        return self.names[key]

    def date_str(self, d):
        return f"{self.days[d.weekday()]} {d.day} {self.months[d.month - 1]}"


def fmt_dur(sec, lang):
    from .ui import fmt_dur as f
    return f(sec, lang)


def sysinfo_now(cfg):
    from .sysinfo import SysInfo
    s = SysInfo.__new__(SysInfo)
    s.wifi_iface = cfg["network"]["wifi_interface"]
    s._prev_cpu = None
    d = {}
    s._cpu_percent()
    time.sleep(0.5)
    d.update(s._collect_fast())
    d.update(s._collect_slow())
    return d


def weather_now(cfg):
    try:
        with open(WEATHER_CACHE) as f:
            w = json.load(f)
        if time.time() - w.get("weather_at", 0) < 3600:
            return w
    except Exception:
        pass
    import threading
    from .weather import Weather
    w = Weather.__new__(Weather)
    w.lat, w.lon = float(cfg["location"]["latitude"]), float(cfg["location"]["longitude"])
    w._lock, w._data, w.cache = threading.Lock(), {}, WEATHER_CACHE
    w.fetch()
    return w.snapshot()


# ------------------------------------------------------------------ commands
def cmd_times(ctx, args):
    now = ctx.now()
    s = ctx.sched.compute(now)
    lines = [f"{ctx.cfg['location']['name']} · {ctx.date_str(now)}"]
    for key, when in s["today"]:
        mark = "▶ " if s["next"] == (key, when) else ("✓ " if when <= now else "   ")
        lines.append(f"{mark}{ctx.pname(key, when):8s} {when:%H:%M}")
    lines.append("")
    lines.append(cmd_next(ctx, ""))
    return "\n".join(lines)


def cmd_next(ctx, args):
    now = ctx.now()
    s = ctx.sched.compute(now)
    if s["state"] == "prayer":
        key, when = s["current"]
        return (f"Sekarang waktu {ctx.pname(key, when)} ({when:%H:%M})" if ctx.id
                else f"It's {ctx.pname(key, when)} time now ({when:%H:%M})")
    key, when = s["next"]
    left = fmt_dur((when - now).total_seconds(), ctx.lang)
    return (f"{ctx.pname(key, when)} {when:%H:%M} — {left} lagi" if ctx.id
            else f"{ctx.pname(key, when)} at {when:%H:%M} — in {left}")


def cmd_weather(ctx, args):
    from .weather import aqi_band, describe
    w = weather_now(ctx.cfg)
    if w.get("temp") is None:
        return ("Data cuaca belum tersedia. " if ctx.id else "No weather data yet. ") + (w.get("weather_error") or "")
    kind, en, idn = describe(w.get("code"))
    t = [f"{ctx.cfg['location']['name']}: {round(w['temp'])}°C, {idn if ctx.id else en}"]
    if w.get("feels") is not None:
        t.append((f"Terasa {round(w['feels'])}°C" if ctx.id else f"Feels like {round(w['feels'])}°C") +
                 f" · {'lembap' if ctx.id else 'humidity'} {w.get('humidity')}%")
    if w.get("hi") is not None:
        t.append(f"{'Hari ini' if ctx.id else 'Today'} {round(w['lo'])}–{round(w['hi'])}°C, "
                 f"{'hujan' if ctx.id else 'rain'} {w.get('rain_max')}%")
    if w.get("aqi") is not None:
        b, ben, bid = aqi_band(w["aqi"])
        t.append(f"AQI {round(w['aqi'])} · {bid if ctx.id else ben} · PM2.5 {w.get('pm25', 0):.0f}")
    hours = w.get("hours") or []
    if hours:
        t.append(" ".join(f"{h['time']}h {round(h['temp'])}° {h['rain']}%" for h in hours[:4]))
    return "\n".join(t)


def cmd_status(ctx, args):
    from .sysinfo import fmt_bytes, fmt_uptime, throttle_text
    d = sysinfo_now(ctx.cfg)
    ts = d.get("tailscale") or {}
    users = [u for u in d.get("users", []) if u["src"] != "local"]
    lines = [
        f"{d.get('hostname')} · {d.get('ip')}",
        f"CPU {d.get('cpu', 0):.0f}% · {d.get('temp') or 0:.0f}°C · load {d.get('load', 0):.2f}",
        f"RAM {fmt_bytes(d.get('ram_used', 0))}/{fmt_bytes(d.get('ram_total', 0))} · "
        f"Disk {fmt_bytes(d.get('disk_used', 0))}/{fmt_bytes(d.get('disk_total', 0))}",
        f"Wi-Fi {d.get('wifi_ssid') or 'off'}" + (f" {d.get('wifi_dbm')} dBm" if d.get("wifi_dbm") else ""),
        f"Tailscale {ts.get('ip') or ts.get('state') or 'not installed'}" +
        (f" · {ts.get('peers_online', 0)} online" if ts.get("state") == "Running" else ""),
        f"SSH {'on' if d.get('ssh_on') else 'off'} · {len(users)} session(s)",
        f"Up {fmt_uptime(d.get('uptime', 0))} · power {throttle_text(d.get('throttled'))}",
    ]
    return "\n".join(lines)


def cmd_pet(ctx, args):
    from .pet import PetState
    p = PetState(ctx.cfg["pet"]["state_file"], ctx.cfg["pet"]["name"])
    h, j = p["hunger"], p["happy"]
    mood = ("lapar" if ctx.id else "hungry") if h < 25 else ("sedih" if ctx.id else "sad") if j < 25 else \
        ("senang" if ctx.id else "happy")
    return (f"{p['name']}, {p.age_days()} {'hari' if ctx.id else 'days'} · {mood}\n"
            f"{'Makan' if ctx.id else 'Food'} {h:.0f}% · {'Senang' if ctx.id else 'Joy'} {j:.0f}%\n"
            f"{'Diberi makan' if ctx.id else 'Fed'} {p['feeds']}× · {'Dielus' if ctx.id else 'Patted'} {p['pats']}×")


def _asleep_reply(ctx):
    """The screen app ignores feed/pat while the pet sleeps; say so instead of pretending."""
    s = ctx.sched.compute(ctx.now())
    if s["state"] != "sleep":
        return None
    t = ctx.sched.day(ctx.now().date() + (timedelta(1) if ctx.now().hour >= 12 else timedelta(0)))["fajr"]
    wake = t - timedelta(minutes=int(ctx.cfg["pet"]["wake_before_fajr_minutes"]))
    name = ctx.cfg["pet"]["name"]
    return (f"{name} sedang tidur 💤 Bangun sekitar {wake:%H:%M}." if ctx.id
            else f"{name} is asleep 💤 Wakes up around {wake:%H:%M}.")


def cmd_feed(ctx, args):
    sleeping = _asleep_reply(ctx)
    if sleeping:
        return sleeping
    inbox.post("feed")
    return "Nyam! 🍚" if ctx.id else "Fed! 🍚"


def cmd_pat(ctx, args):
    sleeping = _asleep_reply(ctx)
    if sleeping:
        return sleeping
    inbox.post("pat")
    return "❤️"


def cmd_say(ctx, args):
    text = inbox.clean_text(args)
    if not text:
        return "Contoh: /say Makan malam jam 7" if ctx.id else "Example: /say Dinner at 7"
    inbox.post("say", text=text, minutes=30)
    return (f"Tampil di layar selama 30 menit: {text}" if ctx.id else f"On the screen for 30 minutes: {text}")


def cmd_screen(ctx, args):
    """Returns PNG bytes of the chosen page."""
    from .pet import PetAnimator, PetState
    from .ui import Renderer
    page = (args or "home").strip().lower()
    if page not in ("home", "weather", "status"):
        page = "home"
    r = Renderer(ctx.cfg)
    now = ctx.now()
    s = ctx.sched.compute(now)
    info = sysinfo_now(ctx.cfg)
    info["wx"] = weather_now(ctx.cfg)
    if page == "status":
        img = r.status(now, s, info)
    elif page == "weather":
        img = r.weather(now, s, info)
    else:
        from .app import pick_mood
        pet = PetState(ctx.cfg["pet"]["state_file"], ctx.cfg["pet"]["name"])
        img = r.home(now, s, info, pet, PetAnimator(r.pet_area, r.c), pick_mood(s, pet))
    from PIL import Image
    img = img.resize((img.width * 2, img.height * 2), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def ask_gemini(ctx, secrets, question):
    if not secrets.get("gemini_api_key"):
        return ("/ask belum diaktifkan. Tambahkan gemini_api_key di ~/.prayerpet-telegram.toml" if ctx.id
                else "/ask is not set up. Add gemini_api_key to ~/.prayerpet-telegram.toml")
    question = inbox.clean_text(question)[:500]
    if not question:
        return "Contoh: /ask perlu bawa payung hari ini?" if ctx.id else "Example: /ask do I need an umbrella today?"
    # daily limit, so a mistake can't burn through the quota
    today = ctx.now().date().isoformat()
    try:
        with open(USAGE) as f:
            usage = json.load(f)
    except Exception:
        usage = {}
    if usage.get("date") != today:
        usage = {"date": today, "count": 0}
    if usage["count"] >= int(secrets["ask_daily_limit"]):
        return "Batas /ask hari ini sudah habis." if ctx.id else "Today's /ask limit is used up."
    usage["count"] += 1
    with open(USAGE, "w") as f:
        json.dump(usage, f)

    # give the model today's context so it can answer "should I bring an umbrella"
    try:
        context = cmd_times(ctx, "") + "\n" + cmd_weather(ctx, "")
    except Exception:
        context = ""
    system = ("You answer inside a Telegram chat, sent from the user's Raspberry Pi. "
              "Reply in the user's language, in plain text without markdown, under 120 words. "
              f"Local time: {ctx.now():%A %d %B %Y %H:%M}. Context from the Pi:\n{context}")
    body = {"system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": question}]}],
            "generationConfig": {"maxOutputTokens": 400}}
    def call(model):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              "x-goog-api-key": secrets["gemini_api_key"]})
        with urllib.request.urlopen(req, timeout=40) as r:
            res = json.loads(r.read().decode())
        parts = res["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip() or "(no answer)"

    model = secrets["gemini_model"]
    try:
        return call(model)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")
        try:
            msg = json.loads(detail)["error"]["message"]
        except Exception:
            msg = detail[:200]
        # Google retires models and names the replacement, e.g. "...use models/gemini-3.5-flash-lite..."
        m = re.search(r"models/([a-z0-9.\-]+flash[a-z0-9.\-]*)", msg.split("use", 1)[-1]) if e.code == 404 else None
        if m and m.group(1) != model:
            try:
                answer = call(m.group(1))
                log(f"Model {model} retired; used {m.group(1)}. Update gemini_model in {SECRETS}")
                note = (f"\n\n(Model {model} sudah tidak tersedia; memakai {m.group(1)}. "
                        f"Ubah gemini_model di ~/.prayerpet-telegram.toml)" if ctx.id else
                        f"\n\n(Model {model} was retired; used {m.group(1)}. "
                        f"Set gemini_model in ~/.prayerpet-telegram.toml)")
                return answer + note
            except Exception as e2:
                return f"Gemini error: {e2}"
        return f"Gemini error {e.code}: {msg[:300]}"
    except Exception as e:
        return f"Gemini error: {e}"


def help_text(ctx):
    return "\n".join(f"/{c} — {d}" for c, d in COMMANDS)


HANDLERS = dict(times=cmd_times, next=cmd_next, weather=cmd_weather, status=cmd_status,
                pet=cmd_pet, feed=cmd_feed, pat=cmd_pat, say=cmd_say)


# ------------------------------------------------------------------ reminders
class Reminders:
    def __init__(self, ctx, secrets):
        self.ctx, self.s = ctx, secrets
        self.sent = set()

    def due(self):
        """Messages to send now (each one only once)."""
        before = int(self.s["remind_before_minutes"] or 0)
        at_time = bool(self.s["remind_at_time"])
        if not before and not at_time:
            return []
        now = self.ctx.now()
        times = self.ctx.sched.day(now.date())
        out = []
        for key in OBLIGATORY:
            when = times[key]
            name = self.ctx.pname(key, when)
            if before and when - timedelta(minutes=before) <= now < when:
                tag = (when.isoformat(), key, "before")
                if tag not in self.sent:
                    self.sent.add(tag)
                    mins = max(1, round((when - now).total_seconds() / 60))
                    out.append(f"🕌 {name} {when:%H:%M} — {mins} menit lagi" if self.ctx.id
                               else f"🕌 {name} at {when:%H:%M} — in {mins} min")
            if at_time and when <= now < when + timedelta(minutes=5):
                tag = (when.isoformat(), key, "now")
                if tag not in self.sent:
                    self.sent.add(tag)
                    out.append(f"🕌 Waktu {name} ({when:%H:%M})" if self.ctx.id else f"🕌 {name} time ({when:%H:%M})")
        return out


# ------------------------------------------------------------------ main loop
def show_whoami(tg):
    log("Recent messages to your bot (send it any message first, e.g. /start):\n")
    seen = set()
    for u in tg.call("getUpdates", http_timeout=15, limit=50):
        m = u.get("message") or {}
        frm, chat = m.get("from") or {}, m.get("chat") or {}
        key = frm.get("id")
        if key and key not in seen:
            seen.add(key)
            log(f"  user id {frm.get('id')}  name: {frm.get('first_name', '')} @{frm.get('username', '')}  "
                f"chat type: {chat.get('type')}  text: {m.get('text', '')[:30]!r}")
    if not seen:
        log("  (none yet) Open your bot in Telegram, send /start, then run this again.")
    log("\nPut your user id in allowed_ids in ~/.prayerpet-telegram.toml, then:"
        "\n  sudo systemctl enable --now prayerpet-bot")
    return 0


def main(cfg, whoami=False):
    secrets = load_secrets()
    if not secrets or not secrets.get("token"):
        log(f"Telegram bot is not configured. Put your bot token in {SECRETS} (see README).")
        return 0
    tg = Telegram(secrets["token"])
    if whoami:
        try:
            return show_whoami(tg)
        except Exception as e:
            log("Could not reach Telegram:", e)
            log("If the bot service is running, stop it first: sudo systemctl stop prayerpet-bot")
            return 1
    if not secrets["allowed_ids"]:
        log("allowed_ids is empty, so the bot would answer nobody. Run: prayerpet --bot-whoami")
        return 0

    ctx = Context(cfg)
    rem = Reminders(ctx, secrets)
    offset = None
    backoff = 5
    try:
        me = tg.call("getMe")
        tg.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in COMMANDS])
        log(f"Bot @{me.get('username')} running. Allowed user ids: {sorted(secrets['allowed_ids'])}")
    except Exception as e:
        log("Telegram not reachable at start:", e)

    warned = set()
    while True:
        try:
            for text in rem.due():
                for uid in secrets["allowed_ids"]:
                    tg.send(uid, text)

            params = dict(timeout=25, allowed_updates=["message"])
            if offset is not None:
                params["offset"] = offset
            updates = tg.call("getUpdates", http_timeout=40, **params)
            backoff = 5
            for u in updates:
                offset = u["update_id"] + 1
                m = u.get("message") or {}
                frm, chat = m.get("from") or {}, m.get("chat") or {}
                uid = frm.get("id")
                if uid not in secrets["allowed_ids"] or chat.get("type") != "private":
                    if uid not in warned:
                        warned.add(uid)
                        log(f"Ignored message from user id {uid} (@{frm.get('username', '')}), not in allowed_ids")
                    continue
                text = (m.get("text") or "").strip()
                if not text.startswith("/"):
                    tg.send(chat["id"], help_text(ctx))
                    continue
                cmd, _, args = text[1:].partition(" ")
                cmd = cmd.split("@")[0].lower()
                log(f"/{cmd} from {uid}")
                try:
                    if cmd == "screen":
                        tg.send_photo(chat["id"], cmd_screen(ctx, args))
                    elif cmd == "ask":
                        tg.send(chat["id"], ask_gemini(ctx, secrets, args))
                    elif cmd in HANDLERS:
                        tg.send(chat["id"], HANDLERS[cmd](ctx, args))
                    else:
                        tg.send(chat["id"], help_text(ctx))
                except Exception as e:
                    log(f"/{cmd} failed: {e}")
                    tg.send(chat["id"], f"Sorry, /{cmd} failed: {e}")
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            log(f"Telegram connection problem: {e}. Retrying in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
