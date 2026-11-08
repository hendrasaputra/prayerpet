"""Main loop and command-line entry point.

  prayerpet                 run on the TFT (what the service does)
  prayerpet --times         print today's prayer times and exit
  prayerpet --info          show which screen/touch devices were found
  prayerpet --touch-test    print tap coordinates, for calibration
  prayerpet --png out.png --at "2026-10-31 14:46" [--page status]   render one frame to a file
  prayerpet --window        preview in a desktop window (needs pygame)
"""
import argparse
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config as config_mod
from .pet import PetAnimator, PetState
from .prayer import ORDER, PrayerCalculator
from .sysinfo import SysInfo
from . import inbox
from .ui import Renderer

OBLIGATORY = ["fajr", "dhuhr", "asr", "maghrib", "isha"]


class Clock:
    """Real time, optionally shifted so previews can show any moment."""

    def __init__(self, tz, at=None):
        self.tz = tz
        self.shift = timedelta(0)
        if at:
            target = datetime.fromisoformat(at).replace(tzinfo=tz)
            self.shift = target - datetime.now(tz)

    def now(self):
        return datetime.now(self.tz) + self.shift


def make_calculator(cfg, tz):
    loc, pr = cfg["location"], cfg["prayer"]
    return PrayerCalculator(loc["latitude"], loc["longitude"], tz, method=pr["method"], asr=pr["asr"],
                            elevation=loc.get("elevation", 0), offsets=pr.get("offsets") or {})


class Schedule:
    def __init__(self, cfg, calc):
        self.cfg, self.calc = cfg, calc
        self.show = [k for k in ORDER if k in cfg["prayer"]["show"]] or OBLIGATORY
        self._cache = {}

    def day(self, d):
        if d not in self._cache:
            self._cache = {k: v for k, v in self._cache.items() if abs((k - d).days) <= 2}
            self._cache[d] = self.calc.times_for(d)
        return self._cache[d]

    def compute(self, now):
        pr, pet = self.cfg["prayer"], self.cfg["pet"]
        today = now.date()
        t_today, t_tom, t_yest = self.day(today), self.day(today + timedelta(1)), self.day(today - timedelta(1))
        shown = [(k, t_today[k]) for k in self.show]
        events = [(k, t_yest[k]) for k in self.show] + shown + [(k, t_tom[k]) for k in self.show]
        nxt = next(e for e in events if e[1] > now)
        prev = [e for e in events if e[1] <= now]
        prev = prev[-1] if prev else None

        # state: alert (prayer soon) > prayer (just started) > sleep > awake
        ob = [(k, t[k]) for t in (t_yest, t_today, t_tom) for k in OBLIGATORY]
        next_ob = next(e for e in ob if e[1] > now)
        last_ob = [e for e in ob if e[1] <= now][-1]
        state, current = "awake", None
        if (next_ob[1] - now).total_seconds() <= pr["remind_minutes_before"] * 60:
            state = "alert"
            nxt = next_ob
        elif (now - last_ob[1]).total_seconds() <= pr["highlight_minutes_after"] * 60:
            state, current = "prayer", last_ob
        else:
            sleep_start = t_today["isha"] + timedelta(minutes=pet["sleep_after_isha_minutes"])
            wake = t_today["fajr"] - timedelta(minutes=pet["wake_before_fajr_minutes"])
            if now >= sleep_start or now < wake:
                state = "sleep"
        return dict(today=shown, next=nxt, prev=prev, state=state, current=current)


def pick_mood(sched, pet):
    s = sched["state"]
    if s == "alert":
        return "alert"
    if s == "prayer":
        return "prayer"
    if s == "sleep":
        return "sleep"
    if pet["hunger"] < 25:
        return "hungry"
    if pet["happy"] < 25:
        return "sad"
    return "idle"


def shutdown_pi(display, renderer):
    lang = renderer.lang
    if lang == "id":
        display.show(renderer.message("Mematikan Pi...", "Cabut listrik setelah lampu hijau mati"))
    else:
        display.show(renderer.message("Shutting down...", "Unplug after the green light stops"))
    r = subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "poweroff"], capture_output=True, text=True)
    if r.returncode != 0:
        print("shutdown failed:", r.stderr.strip(), flush=True)
        display.show(renderer.message("Shutdown not allowed", "Re-run install.sh to fix"))
        time.sleep(3)
        return False
    return True


def run(cfg, display, touch=None, at=None, frames=None, page=None, verbose=False, buttons=None):
    tz = ZoneInfo(cfg["location"]["timezone"])
    clock = Clock(tz, at)
    sched_calc = Schedule(cfg, make_calculator(cfg, tz))
    info_src = SysInfo(cfg["network"]["wifi_interface"])
    wx_src = None
    wcfg = cfg.get("weather", {})
    if wcfg.get("enabled", True) and not frames:
        from .weather import Weather
        wx_src = Weather(cfg["location"]["latitude"], cfg["location"]["longitude"],
                         wcfg.get("refresh_minutes", 15))
    pages = ["home", "weather", "status"] if wcfg.get("enabled", True) else ["home", "status"]

    def next_page(p):
        return pages[(pages.index(p) + 1) % len(pages)] if p in pages else pages[0]
    renderer = Renderer(cfg)
    pet = PetState(cfg["pet"]["state_file"], cfg["pet"]["name"])
    anim = PetAnimator(renderer.pet_area, renderer.c)
    page = page or cfg["screen"].get("start_page", "home")
    fps = max(1, min(10, float(cfg["screen"]["fps"])))
    auto_switch = float(cfg["screen"].get("auto_switch_seconds", 0) or 0)
    last_switch = time.time()
    wake_until = 0.0
    manual_dim = False
    hint_until = 0.0
    bcfg = cfg.get("buttons", {})
    hint_edge = str(bcfg.get("hint_edge", "bottom")).lower()
    hint_secs = float(bcfg.get("hint_seconds", 3))
    shutting_down = False
    message = None          # dict(text, until) shown in the speech bubble
    last_inbox = 0.0
    running = [True]

    def stop(*_):
        running[0] = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    if frames:  # give the background collector a moment for PNG previews
        time.sleep(0.3)
    n = 0
    try:
        while running[0]:
            t0 = time.time()
            now = clock.now()
            sched = sched_calc.compute(now)
            info = info_src.snapshot()
            if wx_src is not None:
                info["wx"] = wx_src.snapshot()
            elif "wx" in cfg:  # test hook
                info["wx"] = cfg["wx"]
            mood = pick_mood(sched, pet)
            pet.tick(sleeping=(mood == "sleep"))

            night_dim = cfg["screen"].get("night_dim", True) and sched["state"] == "sleep"
            dimmed = manual_dim or (night_dim and time.time() > wake_until)

            def do(action):
                nonlocal page, last_switch, manual_dim
                if action == "page":
                    page = next_page(page)
                    last_switch = time.time()
                elif action in ("feed", "pat"):
                    page = "home"
                    if mood == "sleep":
                        return  # let it sleep
                    if action == "feed":
                        pet.feed()
                        anim.react("food", 2.0)
                    else:
                        pet.pat()
                        anim.react("heart", 2.0)
                elif action == "screen":
                    manual_dim = True

            # requests from the Telegram bot / AI assistant / shell (prayerpet --say ...)
            if time.time() - last_inbox >= 1.0:
                last_inbox = time.time()
                for req in inbox.drain():
                    if verbose:
                        print("inbox", req, flush=True)
                    wake_until = time.time() + 30
                    manual_dim = False
                    if req["kind"] == "say" and req.get("text"):
                        mins = max(1, min(24 * 60, float(req.get("minutes", 30) or 30)))
                        message = dict(text=req["text"], until=time.time() + mins * 60)
                        page = "home"
                    elif req["kind"] in ("feed", "pat"):
                        do(req["kind"])
            if message and time.time() > message["until"]:
                message = None
            if message and mood == "idle":
                mood = "happy"

            # buttons
            if buttons is not None:
                for kind, pin in buttons.poll():
                    if verbose:
                        print("button", kind, pin, flush=True)
                    if kind == "down":
                        hint_until = time.time() + hint_secs
                    elif kind == "hold":
                        if shutdown_pi(display, renderer):
                            shutting_down = True
                            running[0] = False
                    elif kind == "press":
                        if dimmed:  # first press only brightens the screen
                            manual_dim = False
                            wake_until = time.time() + 30
                            continue
                        wake_until = time.time() + 30
                        do(buttons.action(pin))
                if shutting_down:
                    break

            # touch
            taps = []
            if touch is not None:
                taps += touch.get_taps()
            if hasattr(display, "get_taps"):
                taps += display.get_taps()
            for (x, y) in taps:
                if verbose:
                    print("tap", x, y, flush=True)
                if dimmed:
                    manual_dim = False
                    wake_until = time.time() + 30
                    continue
                wake_until = time.time() + 30
                if page == "home" and anim.hit(x, y):
                    do("feed" if pet["hunger"] < 60 else "pat")
                else:
                    do("page")

            if sched["state"] in ("alert", "prayer"):
                page = "home"
            elif auto_switch and time.time() - last_switch > auto_switch:
                page = next_page(page)
                last_switch = time.time()

            if page == "status":
                img = renderer.status(now, sched, info)
            elif page == "weather":
                img = renderer.weather(now, sched, info)
            else:
                anim.top = anim.ay + (64 if message else 36)  # make room for the speech bubble
                img = renderer.home(now, sched, info, pet, anim, mood)
                if message:
                    img = renderer.speech(img, message["text"], time.time(), anim.x)
            if buttons is not None:
                prog = buttons.hold_progress()
                if prog is not None:
                    img = renderer.hold_overlay(img, prog, buttons.hold_s * (1 - prog) + 0.99)
                elif time.time() < hint_until:
                    pressed = next(iter(buttons.down_since), None)
                    img = renderer.button_hints(img, hint_edge, [(p, buttons.action(p)) for p in buttons.pins],
                                                pressed)
            if manual_dim or (night_dim and time.time() > wake_until):
                img = renderer.dim(img, 0.15 if manual_dim else 0.4)
            display.show(img)
            if hasattr(display, "wake") and n % int(fps * 60) == 0 and n:
                display.wake()  # re-assert once a minute in case something blanked the screen

            if getattr(display, "quit", False):
                break
            n += 1
            if frames and n >= frames:
                break
            time.sleep(max(0.0, 1.0 / fps - (time.time() - t0)))
    finally:
        pet.save()
        info_src.stop()
        if wx_src is not None:
            wx_src.stop()
        if buttons is not None:
            buttons.close()
        if not shutting_down:
            display.clear()
        display.close()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="prayerpet", description="Prayer times + status monitor + pet for a 320x240 TFT")
    from . import __version__
    ap.add_argument("--version", action="version", version=f"prayerpet {__version__}")
    ap.add_argument("--config", default="~/prayerpet.toml")
    ap.add_argument("--times", nargs="?", const="today", metavar="YYYY-MM-DD", help="print prayer times and exit")
    ap.add_argument("--info", action="store_true", help="show detected screen and touch devices")
    ap.add_argument("--touch-test", "--input-test", dest="touch_test", action="store_true",
                    help="print touch taps and button presses (stop the service first)")
    ap.add_argument("--png", metavar="FILE", help="render to a PNG instead of the screen")
    ap.add_argument("--frames", type=int, default=None, help="stop after N frames")
    ap.add_argument("--at", metavar="'YYYY-MM-DD HH:MM'", help="pretend it is this time (for previews)")
    ap.add_argument("--page", choices=["home", "weather", "status"])
    ap.add_argument("--weather", action="store_true", help="fetch weather + air quality once and print it")
    ap.add_argument("--window", action="store_true", help="desktop preview window (pip install pygame)")
    ap.add_argument("--say", metavar="TEXT", help="show TEXT in the pet's speech bubble")
    ap.add_argument("--minutes", type=float, default=30, help="how long --say stays on screen (default 30)")
    ap.add_argument("--feed", action="store_true", help="feed the pet")
    ap.add_argument("--pat", action="store_true", help="pat the pet")
    ap.add_argument("--bot", action="store_true", help="run the Telegram bot (used by prayerpet-bot.service)")
    ap.add_argument("--bot-whoami", action="store_true", help="show chat IDs that messaged the bot, for setup")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    cfg = config_mod.load(a.config)
    tz = ZoneInfo(cfg["location"]["timezone"])

    if a.say or a.feed or a.pat:
        if a.say:
            inbox.post("say", text=a.say, minutes=a.minutes)
            print(f"Sent to the pet screen for {a.minutes:g} min: {inbox.clean_text(a.say)}")
        if a.feed:
            inbox.post("feed"); print("Fed the pet.")
        if a.pat:
            inbox.post("pat"); print("Patted the pet.")
        return 0

    if a.bot or a.bot_whoami:
        from . import bot
        return bot.main(cfg, whoami=a.bot_whoami)

    if a.times:
        from .ui import NAMES
        d = datetime.now(tz).date() if a.times == "today" else datetime.fromisoformat(a.times).date()
        names = NAMES.get(cfg["prayer"].get("language", "id"), NAMES["en"])
        loc = cfg["location"]
        print(f"{loc['name']} ({loc['latitude']}, {loc['longitude']}) {d}  method={cfg['prayer']['method']}")
        for k, v in make_calculator(cfg, tz).times_for(d).items():
            print(f"  {names[k]:8s} {v.strftime('%H:%M')}")
        return 0

    if a.weather:
        from .weather import Weather, aqi_band, describe
        w = Weather.__new__(Weather)
        w.lat, w.lon = float(cfg["location"]["latitude"]), float(cfg["location"]["longitude"])
        import threading, os
        w._lock, w._data, w.cache = threading.Lock(), {}, os.path.expanduser("~/.prayerpet-weather.json")
        w.fetch()
        d = w.snapshot()
        print(f"{cfg['location']['name']}: {d.get('temp')}°C, feels {d.get('feels')}°C, "
              f"{describe(d.get('code'))[1]}, humidity {d.get('humidity')}%, wind {d.get('wind')} km/h")
        print(f"  today {d.get('lo')}..{d.get('hi')}°C, rain chance {d.get('rain_max')}%")
        if d.get("aqi") is not None:
            print(f"  US AQI {d['aqi']} ({aqi_band(d['aqi'])[1]}), PM2.5 {d.get('pm25')}, PM10 {d.get('pm10')}")
        for k in ("weather_error", "air_error"):
            if d.get(k):
                print(f"  {k}: {d[k]}")
        return 0

    if a.info:
        from . import __version__
        print(f"prayerpet {__version__}")
        running = subprocess.run(["systemctl", "is-active", "prayerpet"], capture_output=True, text=True).stdout.strip()
        print(f"service: {running}")
        from .display import FramebufferDisplay
        try:
            disp = FramebufferDisplay(cfg["screen"]["framebuffer"], cfg["screen"]["rotate"])
            print("screen:", disp.describe())
            if any("console pause" in n and "failed" in n for n in disp.notes):
                print("        (pausing the console only works inside the service; this is normal here)")
            disp._console_on()
            disp.close()
        except Exception as e:
            print("screen: NOT FOUND -", e)
        try:
            from .touch import Touch
            print("touch: ", Touch(cfg["touch"]).describe())
        except Exception as e:
            print("touch:  NOT FOUND -", e)
        try:
            from .buttons import Buttons
            print("buttons:", Buttons(cfg.get("buttons", {})).describe())
        except Exception as e:
            if "busy" in str(e).lower() and running == "active":
                print("buttons: in use by the running app (normal). Stop it first to test: sudo systemctl stop prayerpet")
            else:
                print("buttons: NOT AVAILABLE -", e)
        from .bot import SECRETS, load_secrets
        try:
            sec = load_secrets()
            bot_state = subprocess.run(["systemctl", "is-active", "prayerpet-bot"], capture_output=True, text=True).stdout.strip()
            if not sec or not sec.get("token"):
                print("telegram: not configured (add token to ~/.prayerpet-telegram.toml)")
            elif not sec.get("allowed_ids"):
                print("telegram: token set, allowed_ids empty (run: prayerpet --bot-whoami)")
            else:
                print(f"telegram: configured for user ids {sorted(sec['allowed_ids'])}, service {bot_state}")
        except Exception as e:
            print("telegram: settings file problem -", e)
        return 0

    if a.touch_test:
        print("Input test. Tap the screen corners and press each button. Ctrl+C to stop.")
        print("Top-left of the screen should map near (0,0), bottom-right near (319,239).\n")
        tch = btn = None
        try:
            from .touch import Touch
            tch = Touch(cfg["touch"])
            tch.debug = True
            print("touch:  ", tch.describe())
        except Exception as e:
            print("touch:   NOT AVAILABLE -", e)
        try:
            from .buttons import Buttons
            btn = Buttons(cfg.get("buttons", {}))
            print("buttons:", btn.describe())
        except Exception as e:
            print("buttons: NOT AVAILABLE -", e)
        print()
        try:
            while True:
                time.sleep(0.05)
                if tch:
                    tch.get_taps()
                if btn:
                    for kind, pin in btn.poll():
                        if kind != "down":
                            print(f"BUTTON GPIO{pin} {kind:5s} -> action '{btn.action(pin)}'", flush=True)
        except KeyboardInterrupt:
            return 0

    if a.png:
        from .display import PngDisplay
        return run(cfg, PngDisplay(a.png), at=a.at, frames=a.frames or 1, page=a.page, verbose=a.verbose) or 0

    if a.window:
        from .display import WindowDisplay
        return run(cfg, WindowDisplay(), at=a.at, frames=a.frames, page=a.page, verbose=a.verbose) or 0

    from .display import FramebufferDisplay
    disp = FramebufferDisplay(cfg["screen"]["framebuffer"], cfg["screen"]["rotate"])
    print("screen:", disp.describe(), flush=True)
    touch = None
    if cfg["touch"].get("enabled", True):
        try:
            from .touch import Touch
            touch = Touch(cfg["touch"])
            print("touch:", touch.describe(), flush=True)
        except Exception as e:
            print("touch disabled:", e, flush=True)
    buttons = None
    if cfg.get("buttons", {}).get("enabled", True):
        try:
            from .buttons import Buttons
            buttons = Buttons(cfg["buttons"])
            print("buttons:", buttons.describe(), flush=True)
        except Exception as e:
            print("buttons disabled:", e, flush=True)
    return run(cfg, disp, touch, at=a.at, frames=a.frames, page=a.page, verbose=a.verbose, buttons=buttons) or 0


if __name__ == "__main__":
    sys.exit(main())
