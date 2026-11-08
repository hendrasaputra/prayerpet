"""Load ~/prayerpet.toml and fill in defaults for anything missing."""
import copy
import os
import tomllib

DEFAULTS = {
    "location": {"name": "Jakarta", "latitude": -6.2088, "longitude": 106.8456,
                 "timezone": "Asia/Jakarta", "elevation": 0},
    "prayer": {"method": "kemenag", "asr": "shafi", "language": "id",
               "show": ["imsak", "fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"],
               "remind_minutes_before": 10, "highlight_minutes_after": 15, "offsets": {}},
    "pet": {"name": "Nomi", "sleep_after_isha_minutes": 60, "wake_before_fajr_minutes": 20,
            "state_file": "~/.prayerpet-state.json"},
    "screen": {"fps": 4, "framebuffer": "auto", "rotate": 0, "night_dim": True, "clock_24h": True,
               "auto_switch_seconds": 0, "start_page": "home"},
    "buttons": {"enabled": True, "gpio17": "page", "gpio22": "feed", "gpio23": "pat", "gpio27": "screen",
                "order": [17, 22, 23, 27], "hint_edge": "bottom", "hint_seconds": 3,
                "shutdown_pin": 27, "shutdown_hold_seconds": 5},
    "weather": {"enabled": True, "refresh_minutes": 15},
    "network": {"wifi_interface": "wlan0"},
    "touch": {"enabled": True, "device": "auto", "swap_xy": True, "invert_x": False, "invert_y": True,
              "raw_x_min": 240, "raw_x_max": 3850, "raw_y_min": 280, "raw_y_max": 3740},
}


def _merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load(path="~/prayerpet.toml"):
    cfg = copy.deepcopy(DEFAULTS)
    p = os.path.expanduser(path)
    if os.path.exists(p):
        with open(p, "rb") as f:
            _merge(cfg, tomllib.load(f))
    return cfg
