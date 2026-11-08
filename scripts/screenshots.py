"""Render the screens in docs/img from code, with neutral sample data (no network, no real device data).

    python3 scripts/screenshots.py [OUT_DIR]      # default docs/img; also writes overview.png

Each image is the 320x240 screen scaled 2x with nearest-neighbour, so pixel art stays sharp.
"""
import os
import sys
import tempfile
import time
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["HOME"] = tempfile.mkdtemp(prefix="prayerpet-shots-")  # never read the owner's settings
os.environ["USER"] = os.environ["LOGNAME"] = "user"                # the hotspot banner shows the login name

from PIL import Image  # noqa: E402

from prayerpet import config  # noqa: E402
from prayerpet.app import Schedule, make_calculator  # noqa: E402
from prayerpet.pet import PetAnimator, PetState  # noqa: E402
from prayerpet.ui import Renderer  # noqa: E402

cfg = config.load(os.path.join(ROOT, "prayerpet.toml"))
cfg["prayer"]["language"] = "id"
tz = ZoneInfo(cfg["location"]["timezone"])
sched_calc = Schedule(cfg, make_calculator(cfg, tz))
R = Renderer(cfg)

HOURS = [dict(time=16 + i, code=c, temp=31 - i, rain=r, is_day=1)
         for i, (c, r) in enumerate([(2, 20), (3, 40), (61, 70), (95, 85), (80, 60), (3, 30)])]


def info(code=3, aqi=118, wifi_setup=None, at=None):
    wx = dict(temp=31, feels=37, hi=33, lo=25, code=code, is_day=1, rain_max=85, humidity=74, wind=11,
              aqi=aqi, pm25=44, pm10=60, weather_at=at.timestamp(), hours=HOURS)
    return dict(hostname="raspberrypi", ip="192.0.2.50", cpu=12, temp=48, ram_used=300e6, ram_total=906e6,
                disk_used=3.7e9, disk_total=27e9, wifi_ssid="HomeWiFi", wifi_dbm=-55, wifi_pct=80,
                bt_on=False, bt_connected=0, ssh_on=True, time_synced=True,
                users=[dict(name="user", tty="pts/0", src="192.0.2.23")],
                tailscale=dict(installed=True, state="Running", ip="100.64.0.10", peers_online=2),
                uptime=7260, load=0.3, throttled=0, wx=wx, wifi_setup=wifi_setup or {})


def home(at, code=3, aqi=118, hunger=70.0, mood=None, say=None, react=None, t=1000.0, wifi_setup=None):
    now = datetime.strptime(at, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    sched = sched_calc.compute(now)
    pet = PetState(os.path.join(os.environ["HOME"], f"pet-{time.time_ns()}.json"), "Nomi")
    pet.data.update(born=t - 3 * 86400, hunger=hunger, happy=70.0)
    anim = PetAnimator(R.pet_area, R.c)
    anim.next_blink = anim.next_wander = 1e12  # no random blink/wander in screenshots
    if react:
        anim.reaction = (react, t + 1.2)
    if mood is None:
        mood = {"alert": "alert", "prayer": "prayer", "sleep": "sleep"}.get(sched["state"], "idle")
        if mood == "idle" and hunger < 25:
            mood = "hungry"
        if mood == "idle" and say:
            mood = "happy"
    anim.place(bubble=bool(say))
    real_time = time.time
    time.time = lambda: t  # freeze animation time
    try:
        img = R.home(now, sched, info(code, aqi, wifi_setup, now), pet, anim, mood)
        if say:
            img = R.speech(img, say, t, anim.x)
    finally:
        time.time = real_time
    if sched["state"] == "sleep":
        img = R.dim(img, 0.4)
    return img


def page(name, at="2026-10-31 14:20"):
    now = datetime.strptime(at, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    return getattr(R, name)(now, sched_calc.compute(now), info(61, 118, None, now))


SHOTS = {
    "home": lambda: home("2026-10-31 14:20"),
    "alert": lambda: home("2026-10-31 14:47"),
    "prayer": lambda: home("2026-10-31 14:58"),
    "sleep": lambda: home("2026-10-31 22:30"),
    "rain-and-smog": lambda: home("2026-10-31 14:20", code=63, aqi=172),
    "hungry": lambda: home("2026-10-31 14:20", hunger=10),
    "speech": lambda: home("2026-10-31 14:20", say="Dinner at 7. Don't forget to wash your hands!"),
    "sleep-rain": lambda: home("2026-10-31 22:30", code=63),
    "speech-rain": lambda: home("2026-10-31 14:20", code=63, say="Bring an umbrella today!"),
    "hearts": lambda: home("2026-10-31 14:20", react="heart"),
    "feeding": lambda: home("2026-10-31 14:20", hunger=40, react="food"),
    "hotspot": lambda: home("2026-10-31 14:20", wifi_setup=dict(state="ap", ssid="raspberrypi-setup",
                                                                 **{"pass": "examplepw1"})),
    "buttons": lambda: R.button_hints(home("2026-10-31 14:20"), "bottom",
                                      [(17, "page"), (22, "feed"), (23, "pat"), (27, "screen")], 22),
    "shutdown": lambda: R.hold_overlay(home("2026-10-31 14:20"), 0.4, 3),
    "weather": lambda: page("weather"),
    "status": lambda: page("status"),
}
OVERVIEW = ["home", "alert", "prayer", "sleep", "rain-and-smog", "hungry", "weather", "status",
            "speech", "sleep-rain", "speech-rain", "hotspot"]


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "img")
    os.makedirs(out, exist_ok=True)
    big = {}
    for name, make in SHOTS.items():
        big[name] = make().resize((640, 480), Image.NEAREST)
        big[name].save(os.path.join(out, f"{name}.png"))
    sheet = Image.new("RGB", (4 * 660 - 20, 3 * 500 - 20), (255, 255, 255))
    for i, name in enumerate(OVERVIEW):
        sheet.paste(big[name], ((i % 4) * 660, (i // 4) * 500))
    sheet.save(os.path.join(out, "overview.png"))
    print("wrote", len(big) + 1, "images to", out)


if __name__ == "__main__":
    main()
