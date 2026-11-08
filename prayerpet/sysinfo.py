"""System status collection. Runs in a background thread so drawing never waits."""
import os
import re
import shutil
import socket
import subprocess
import threading
import time


def _run(cmd, timeout=3):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def _read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return default


class SysInfo:
    """Call .snapshot() any time; values refresh in the background."""

    def __init__(self, wifi_iface="wlan0", fast_every=2.0, slow_every=10.0):
        self.wifi_iface = wifi_iface
        self.fast_every, self.slow_every = fast_every, slow_every
        self._data = dict(cpu=0.0, temp=None, ram_used=0, ram_total=0, disk_used=0, disk_total=0,
                          load=0.0, uptime=0, ip="-", hostname=socket.gethostname(),
                          wifi_ssid=None, wifi_dbm=None, wifi_pct=None,
                          bt_on=False, bt_connected=0, ssh_on=False, users=[], throttled=None, tailscale={},
                          time_synced=False)
        self._lock = threading.Lock()
        self._prev_cpu = None
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def snapshot(self):
        with self._lock:
            return dict(self._data)

    def stop(self):
        self._stop.set()

    # ------------------------------------------------------------------
    def _loop(self):
        last_slow = 0.0
        while not self._stop.is_set():
            fast = self._collect_fast()
            with self._lock:
                self._data.update(fast)
            if time.monotonic() - last_slow >= self.slow_every:
                slow = self._collect_slow()
                with self._lock:
                    self._data.update(slow)
                last_slow = time.monotonic()
            self._stop.wait(self.fast_every)

    def _cpu_percent(self):
        parts = _read("/proc/stat").splitlines()[0].split()[1:]
        vals = list(map(int, parts))
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        total = sum(vals)
        pct = 0.0
        if self._prev_cpu:
            dt, di = total - self._prev_cpu[0], idle - self._prev_cpu[1]
            pct = 100.0 * (dt - di) / dt if dt > 0 else 0.0
        self._prev_cpu = (total, idle)
        return pct

    def _collect_fast(self):
        d = {}
        try:
            d["cpu"] = self._cpu_percent()
        except Exception:
            pass
        t = _read("/sys/class/thermal/thermal_zone0/temp")
        d["temp"] = int(t) / 1000.0 if t.isdigit() else None
        mem = {}
        for line in _read("/proc/meminfo").splitlines():
            k, _, v = line.partition(":")
            mem[k] = int(v.split()[0]) * 1024 if v.split() else 0
        d["ram_total"] = mem.get("MemTotal", 0)
        d["ram_used"] = mem.get("MemTotal", 0) - mem.get("MemAvailable", 0)
        try:
            du = shutil.disk_usage("/")
            d["disk_used"], d["disk_total"] = du.used, du.total
        except Exception:
            pass
        # setup hotspot state written by wifi-fallback (tools/wifi-fallback)
        ws = {}
        for line in _read("/run/wifi-fallback/state").splitlines():
            k, _, v = line.partition("=")
            ws[k] = v
        d["wifi_setup"] = ws
        la = _read("/proc/loadavg").split()
        d["load"] = float(la[0]) if la else 0.0
        up = _read("/proc/uptime").split()
        d["uptime"] = int(float(up[0])) if up else 0
        # wifi signal from /proc/net/wireless (cheap)
        for line in _read("/proc/net/wireless").splitlines()[2:]:
            if line.strip().startswith(self.wifi_iface):
                f = line.split()
                try:
                    dbm = float(f[3].rstrip("."))
                    d["wifi_dbm"] = int(dbm)
                    d["wifi_pct"] = max(0, min(100, int(2 * (dbm + 100))))
                except Exception:
                    pass
        return d

    def _collect_slow(self):
        d = {}
        # IP address: first non-loopback IPv4
        ips = _run(["hostname", "-I"]).split()
        v4 = [i for i in ips if "." in i]
        d["ip"] = v4[0] if v4 else "no network"
        d["hostname"] = socket.gethostname()

        # Wi-Fi SSID and signal
        link = _run(["iw", "dev", self.wifi_iface, "link"])
        m = re.search(r"SSID:\s*(.+)", link)
        d["wifi_ssid"] = m.group(1).strip() if m else None
        m = re.search(r"signal:\s*(-?\d+)", link)
        if m:
            dbm = int(m.group(1))
            d["wifi_dbm"] = dbm
            d["wifi_pct"] = max(0, min(100, 2 * (dbm + 100)))
        if not d["wifi_ssid"]:
            d["wifi_dbm"] = d["wifi_pct"] = None

        # Bluetooth: service running and radio not blocked
        bt_active = _run(["systemctl", "is-active", "bluetooth"]) == "active"
        blocked = False
        base = "/sys/class/rfkill"
        if os.path.isdir(base):
            for r in os.listdir(base):
                if _read(f"{base}/{r}/type") == "bluetooth":
                    blocked = _read(f"{base}/{r}/soft") == "1" or _read(f"{base}/{r}/hard") == "1"
        d["bt_on"] = bt_active and not blocked and os.path.isdir("/sys/class/bluetooth/hci0")
        if d["bt_on"]:
            out = _run(["bluetoothctl", "devices", "Connected"], timeout=3)
            d["bt_connected"] = len([l for l in out.splitlines() if l.startswith("Device ")])
        else:
            d["bt_connected"] = 0

        # SSH service and logged-in users
        d["ssh_on"] = _run(["systemctl", "is-active", "ssh"]) == "active"
        users = []
        for line in _run(["who"]).splitlines():
            f = line.split()
            if not f:
                continue
            m = re.search(r"\(([^)]+)\)", line)
            users.append(dict(name=f[0], tty=f[1] if len(f) > 1 else "",
                              src=m.group(1) if m else "local"))
        d["users"] = users

        # Power/thermal throttling (Pi only). 0x0 = all good.
        thr = _run(["vcgencmd", "get_throttled"])
        m = re.search(r"0x([0-9a-fA-F]+)", thr)
        d["throttled"] = int(m.group(1), 16) if m else None

        d["time_synced"] = _run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"]) == "yes"

        # Tailscale: state, this Pi's tailnet address, peers online
        ts = dict(installed=bool(shutil.which("tailscale")), state=None, ip=None, peers_online=0, name=None)
        if ts["installed"]:
            raw = _run(["tailscale", "status", "--json"], timeout=4)
            try:
                import json
                j = json.loads(raw)
                ts["state"] = j.get("BackendState")
                me = j.get("Self") or {}
                ips = [i for i in (me.get("TailscaleIPs") or []) if "." in i]
                ts["ip"] = ips[0] if ips else None
                ts["name"] = (me.get("DNSName") or "").split(".")[0] or None
                ts["peers_online"] = sum(1 for p in (j.get("Peer") or {}).values() if p.get("Online"))
            except Exception:
                ts["state"] = "unknown"
        d["tailscale"] = ts
        return d


def fmt_bytes(n):
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit in ("B", "K") else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}P"


def fmt_uptime(s):
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    return f"{d}d {h}h" if d else f"{h}h {m}m"


def throttle_text(v):
    if v is None:
        return "n/a"
    if v == 0:
        return "OK"
    now = []
    if v & 0x1: now.append("LOW VOLT")
    if v & 0x2: now.append("FREQ CAP")
    if v & 0x4: now.append("THROTTLED")
    if v & 0x8: now.append("TEMP LIMIT")
    if now:
        return " ".join(now)
    return "past issue"  # bits 16+ = happened since boot
