# Prayer Pet — Product Requirements Document

| | |
|---|---|
| Product | Prayer Pet: prayer times, a pixel pet, weather/air quality and a system monitor on a Raspberry Pi with a 2.8" touchscreen |
| Current version | 1.7 (deployed) |
| Document date | 2026-11-08 |
| Owner | `<owner>` (placeholder — owner's details are kept out of the repo on purpose) |
| Status | In daily use on one device; maintained through Claude Code |

---

## 1. Summary

Prayer Pet turns a Raspberry Pi 3 Model B+ with an Adafruit PiTFT 2.8" (320×240, resistive touch, 4 side buttons) into an always-on desk device that:

- shows the day's prayer times and counts down to the next one, calculated offline and matched to the official Indonesian (Kemenag) schedule;
- keeps a small pixel-art pet ("Nomi") that reacts to the prayer schedule, the weather and air quality, and to taps, buttons and remote messages;
- shows weather, air quality (US AQI) and the next 6 hours;
- shows the Pi's own health: CPU, temperature, memory, disk, Wi-Fi, Bluetooth, SSH sessions, Tailscale, uptime, power warnings;
- can be reached remotely through a locked-down Telegram bot and an AI assistant (Antigravity CLI) that both talk to the screen through a safe "inbox" folder;
- recovers on its own when moved to a new place (setup Wi-Fi hotspot) and shuts down safely from a button.

## 2. Background & context

- Started 2026-10-31 from a pre-installed Raspberry Pi OS (Bookworm, 64-bit, image 2024-11-19) on which the Adafruit PiTFT helper had already been run.
- The device moves between places in different countries, so location, calculation method and language must be easy to change, and the device must cope with new Wi-Fi networks.
- The owner works on the device over SSH from a Mac and wants to continue development with Claude Code. Explanations and user-facing text must be plain enough for someone outside the field to act on (see AGENTS.md → Writing style).

## 3. Goals and non-goals

### Goals
1. Correct prayer times without internet, matching the authority the owner follows (Kemenag in Indonesia; configurable elsewhere).
2. A glanceable, friendly screen that anyone in the room can read in one second.
3. Starts by itself at boot and recovers from crashes, power cuts and network changes without a keyboard.
4. Remote awareness and light control from a phone, with no way for a stranger or a crafted message to run commands.
5. Kind to the SD card and the weak hardware (Pi 3B+, 1 GB RAM, currently capped at 800 MHz).

### Non-goals
- No desktop environment, browser or heavy apps on this device.
- No local LLM on the Pi 3B+ (too slow; see decision D-27).
- No general-purpose agent with shell access driven by chat messages (OpenClaw-style; see D-30).
- No Hijri calendar yet (moon-sighting decisions differ by country; see backlog).

## 4. Users & use cases

| User | Use case |
|---|---|
| Owner at desk | Glance at next prayer and countdown; see if it's raining / air is bad; pat or feed the pet |
| Owner away | Ask the bot `/next`, `/weather`, `/status`, `/screen`; get reminders 10 min before each prayer; send a message to the screen for people at home |
| Others at home | Read the screen; see the speech-bubble message; press buttons to switch pages |
| Owner travelling | Power the Pi at a new place; join its setup hotspot; add the new Wi-Fi with one command |
| Owner maintaining | SSH in (LAN or Tailscale); use Antigravity CLI with the on-device guide; update via `install.sh` |

## 5. Hardware & platform

| Item | Detail |
|---|---|
| Board | Raspberry Pi 3 Model B+ (1 GB RAM, 4× Cortex-A53, 2.4/5 GHz Wi-Fi, BT) |
| Screen | Adafruit PiTFT Plus 2.8" resistive (ILI9341 display over SPI, STMPE610 touch). Overlay `pitft28-resistive,rotate=270,speed=64000000,fps=30,drm` |
| Framebuffer | DRM driver `ili9341drmfb`, 320×240, **32 bpp**, stride 1280. Appears as `/dev/fb0` when no HDMI display is detected, otherwise `/dev/fb1` — auto-detected by size |
| Touch | `/dev/input/touchscreen` (stmpe-ts) |
| Buttons | GPIO 17, 22, 23, 27; active-low with internal pull-ups (Adafruit guide) |
| OS | Raspberry Pi OS Bookworm 64-bit, console boot (no desktop), NetworkManager, Python 3.11 |
| Python deps | apt only: `python3-pil python3-numpy python3-evdev python3-gpiozero python3-lgpio`, `fonts-dejavu-core`, `iw`, `dnsmasq-base` |
| Power | Must pass `vcgencmd get_throttled` = `0x0` under load. Current setup: 5 V/3 A USB-A charger + short cable + `arm_freq=800` (D-37) |

## 6. Features (as of v1.7)

Each feature lists the requirement and how it is checked.

### F1. Prayer times (offline)
- Calculates Imsak, Fajr/Subuh, Sunrise/Terbit, Dhuha, Dhuhr/Dzuhur (Jumat on Fridays), Asr/Ashar, Maghrib, Isha/Isya from latitude, longitude and time zone. No network needed.
- Methods: `kemenag` (Fajr 20°, Isha 18°, Kemenag safety margins, round up), `jakim`, `muis`, `karachi`, `mwl`, `isna`, `egypt`, `makkah` (Isha = Maghrib + 90 min), `turkey`. Asr: `shafi` or `hanafi`.
- Per-prayer offsets in minutes are **added on top of** the method's margins.
- Imsak = final Fajr − 10 minutes.
- Check: `tests/test_prayer.py` — 23 of 24 times exact vs official Kemenag Jakarta schedule on 3 dates; the one miss is Maghrib 2027-01-15, 1 minute late (safe direction). Yangon (Karachi, Hanafi) matches the Aladhan API for 2026-10-31.

### F2. Pet ("Nomi")
- 16×15 pixel sprite drawn at 5× (sprout on head). States: idle (bob, blink, wanders), happy (^^ eyes; while a message is shown or after a pat), alert (wide eyes, "!", hops; within `remind_minutes_before` of a prayer), prayer (calm, closed eyes; within `highlight_minutes_after`), sleep (from Isha + 60 min until Fajr − 20 min; Zz; screen dims), hungry (<25 food: drooping sprout, worried face, food-bowl thought bubble), sad (<25 joy).
- Stats: food drops ~12/h awake, joy ~8/h awake; ×0.4 while asleep; capped catch-up of 48 h after power-off. Saved to `~/.prayerpet-state.json` every minute and on feed/pat/exit.
- Weather reactions: holds an umbrella and rain falls when the current weather is drizzle/rain/storm (and data is under 3 h old); wears a mask when US AQI > 150.
- Interactions: tap pet → feed if food < 60 else pat; Feed/Pat buttons; `/feed` `/pat` from Telegram; `prayerpet --feed/--pat`. Feeding/patting is ignored while asleep (and the bot says so, v1.7).

### F3. Pages and layout (320×240)
- **Pet page**: top bar (clock, date, temp, AQI badge, Wi-Fi bars, Bluetooth, SSH indicator with remote-session count); left: pet, name, age, food/joy bars; right: prayer list (past dimmed, next in gold, current in green); bottom bar: next prayer + countdown + progress bar.
- **Weather page**: icon, temperature, description, feels-like, high/low, rain chance, humidity, wind; AQI panel (value, category, PM2.5/PM10, data age); next 6 hours (time, icon, temp, rain %).
- **Status page**: hostname + IP; CPU % + temp; RAM; disk; Wi-Fi SSID + dBm/%; Bluetooth; SSH (first remote user@host); Tailscale IP + peers online; uptime + load; power (`pwr OK` / `LOW VOLT` / `past issue`).
- Bottom bar states: normal (panel), alert (gold), prayer (green), Wi-Fi setup hotspot (gold, shows SSID/password/SSH command), "Joining <ssid>…".
- Page order: pet → weather → status (tap anywhere except the pet, or the Page button). Forced to the pet page during alert/prayer windows and when a message arrives. Optional auto-cycle (`auto_switch_seconds`).
- Night dimming to 40% while the pet sleeps; any tap/button brightens for 30 s. Manual dim (Screen button) to 15%.
- Languages: `id` (Subuh, Dzuhur, Ashar…; "mnt lagi") and `en`.

### F4. Weather & air quality
- Open-Meteo forecast + air-quality APIs (free, no key). Refresh every 15 min (retry 2 min on failure). Cached in `~/.prayerpet-weather.json` (ignored if location changed) so the screen shows last data with its age after a reboot without internet; age turns red after 2 h.
- US AQI bands: 0–50 Good, 51–100 Moderate, 101–150 Unhealthy for sensitive groups, 151–200 Unhealthy, 201–300 Very unhealthy, 301+ Hazardous.
- `prayerpet --weather` prints a one-off check.

### F5. Touch
- evdev reader thread; tap = touch release; supports drivers that only report pressure. Calibration in `[touch]` (swap/invert/raw ranges; defaults derived from Adafruit's pointercal for rotate=90, adapted to 270). Only three coarse zones matter (pet / elsewhere / any on status).
- `prayerpet --input-test` prints raw and mapped coordinates.

### F6. Buttons (GPIO 17/22/23/27)
- Defaults: 17 Page, 22 Feed, 23 Pat, 27 Screen (dim). Configurable per pin (`page|feed|pat|screen|none`), physical `order`, `hint_edge`.
- Short press acts on release; first press on a dimmed screen only brightens.
- Labels appear along the configured edge for 3 s after any press (pressed one highlighted).
- **Hold GPIO 27 for 5 s → safe shutdown** with an on-screen countdown; releasing cancels; after shutdown the release does not trigger the short action. Uses a sudoers rule limited to `systemctl poweroff`.

### F7. Runs by itself
- `prayerpet.service` (systemd): runs as the owner's user with groups `video input bluetooth tty gpio` and `CAP_SYS_TTY_CONFIG`; waits up to 20 s for a framebuffer; `Restart=always`.
- Takes the screen from the text console: `KDSETMODE KD_GRAPHICS` on tty1 while running, restores text mode on exit; forces the display mode on and unblanks at start and once a minute.
- Installer removes `fbcon=map:10` from `cmdline.txt` (backup kept), disables HDMI-mirroring helpers (fbcp*), offers console boot if the desktop is enabled.

### F8. Messages on the screen (inbox + speech bubble)
- Any process running as the owner can drop a JSON request into `~/.prayerpet-inbox/`; the app reads and deletes them about once a second. Kinds: `say` (text, minutes), `feed`, `pat`. Unknown kinds are discarded. Text is collapsed to one line, printable characters only, max 280 chars.
- `say` shows a speech bubble above the pet (pet moves down to make room, smiles); long text pages through 3-line pages every 4 s; default 30 min.
- CLI: `prayerpet --say "TEXT" --minutes N`, `--feed`, `--pat`.

### F9. Telegram bot (`prayerpet-bot.service`)
- Standard-library only. Secrets in `~/.prayerpet-telegram.toml` (forced to mode 600).
- Answers only `allowed_ids`, only in one-to-one chats; logs and ignores everyone else. Never runs shell commands; every command is hard-coded.
- Commands: `/times /next /weather /status /screen [home|weather|status] /pet /feed /pat /say /ask /help`.
- Reminders: N minutes before each obligatory prayer (default 10) and at prayer time; each sent once.
- `/ask` (optional): Gemini API (key in the secrets file, separate from any consumer subscription). Today's prayer times and weather are sent as context; plain text, under 120 words; daily cap (default 30). If Google retires the model and names a replacement in the 404, the bot retries once with it and tells the owner to update `gemini_model` (v1.7). Default model `gemini-3.5-flash-lite`.
- Setup helper: `prayerpet --bot-whoami` lists user IDs that messaged the bot. Respects `HTTPS_PROXY` (for networks where Telegram is blocked).

### F10. AI assistant on the device (Antigravity CLI)
- Installer places `tools/GEMINI.md` at `~/.gemini/GEMINI.md`: what runs on the Pi, safe commands (`prayerpet --say` etc.), and rules (ask before sudo/restarts, back up boot files, never reboot unasked, never print secrets, memory is tight).

### F11. Wi-Fi at a new place (`wifi-fallback.service`)
- If no network is connected ~90 s after boot, starts a WPA2 hotspot `<hostname>-setup` at 10.42.0.1 (NetworkManager `ipv4.method shared`, 2.4 GHz ch 6, PMF off for brcmfmac). Password generated at install, stored in `/etc/wifi-fallback.conf`, shown on the TFT while active.
- `wifi-join --list` (nearby networks, scanned before the hotspot started) and `sudo wifi-join "SSID" "PASSWORD"` save a network and drop the hotspot; the service tries every saved network that is visible; if none connects, the hotspot returns.
- While nobody is on the hotspot it re-checks known networks every 10 minutes (handles the router booting after the Pi following a power cut).

### F12. Installer & CLI
- `install.sh` (run as the normal user; idempotent): checks DNS + clock, waits for apt locks (ignoring the always-running `unattended-upgrade-shutdown`), installs apt packages, copies the app to `~/prayerpet-app`, creates `/usr/local/bin/prayerpet`, services, sudoers rule, hotspot profile, Telegram secrets template, `~/.gemini/GEMINI.md`; keeps existing `~/prayerpet.toml` and secrets; prints the version first. ERR trap prints the failing line to **stderr**.
- CLI: `--times [DATE]`, `--info` (version, service state, screen, touch, buttons, Telegram config — with explanations for normal "busy/permission" cases), `--input-test`, `--weather`, `--png FILE [--page] [--at] [--frames]`, `--window` (pygame preview on a desktop), `--say/--minutes/--feed/--pat`, `--bot`, `--bot-whoami`, `--version`.

## 7. Design

### 7.1 Architecture

```
            ┌───────────────────────── prayerpet.service (user, CAP_SYS_TTY_CONFIG) ─────────────────────────┐
            │  app.run loop (fps 4)                                                                          │
 touch.py ─▶│  taps ─┐                     ┌─ prayer.py (PrayerCalculator) ◀─ config.py ◀─ ~/prayerpet.toml   │
buttons.py ▶│  btns ─┼─▶ actions ─▶ pet.py │  app.Schedule (state: awake/alert/prayer/sleep)                 │
 inbox.py ─▶│  reqs ─┘   (PetState,        ├─ sysinfo.py (thread: /proc, iw, systemctl, who, vcgencmd,       │
            │            PetAnimator)      │                tailscale, /run/wifi-fallback/state)             │
            │                              ├─ weather.py  (thread: Open-Meteo → ~/.prayerpet-weather.json)   │
            │  ui.Renderer → PIL image ─▶ display.py (FramebufferDisplay → /dev/fbN; Png; Window)            │
            └────────────────────────────────────────────────────────────────────────────────────────────────┘
 prayerpet-bot.service ── bot.py ── Telegram API (long poll) ── inbox.post() ──▶ ~/.prayerpet-inbox/
 Antigravity CLI / shell ── prayerpet --say/--feed/--pat ── inbox.post() ──▶ ~/.prayerpet-inbox/
 wifi-fallback.service ── tools/wifi-fallback (root, nmcli) ── /run/wifi-fallback/state ──▶ sysinfo → ui
```

### 7.2 Modules
| File | Role |
|---|---|
| `prayer.py` | PrayTimes.org-style astronomy (3 refinement passes), method table, offsets, rounding |
| `app.py` | CLI, main loop, `Schedule` (states, next/prev event), input handling, shutdown |
| `ui.py` | All drawing: pages, top/bottom bars, weather icons, speech bubble, button hints, overlays, palette, fonts, strings (id/en) |
| `pet.py` | `PetState` (stats, persistence), `PetAnimator` (sprite, faces, wander, effects, umbrella, mask) |
| `display.py` | Framebuffer detection and writing (RGB565/BGRX, stride, rotation), console graphics mode, wake/unblank; PNG and pygame backends |
| `touch.py`, `buttons.py` | Input threads (evdev; gpiozero/lgpio) |
| `sysinfo.py` | Background system stats |
| `weather.py` | Background Open-Meteo fetch + cache, WMO code and AQI band mapping |
| `inbox.py` | Cross-process request folder |
| `bot.py` | Telegram bot, reminders, Gemini `/ask` |
| `config.py` | Defaults + TOML merge |
| `tools/` | `wifi-fallback`, `wifi-join`, `fbtest.py`, `GEMINI.md` |

### 7.3 Files on the device
| Path | Content | Private? |
|---|---|---|
| `~/prayerpet.toml` | Settings | no |
| `~/.prayerpet-state.json` | Pet stats | no |
| `~/.prayerpet-weather.json` | Weather cache | no |
| `~/.prayerpet-telegram.toml` (600) | Bot token, allowed IDs, Gemini key | **yes** |
| `~/.prayerpet-bot-usage.json` | `/ask` daily count | no |
| `~/.prayerpet-inbox/` | Pending requests | no |
| `~/.gemini/GEMINI.md` | Assistant guide | no |
| `/etc/wifi-fallback.conf` (644) | Hotspot SSID/password | low (shown on screen anyway) |
| `/etc/sudoers.d/prayerpet` | `systemctl poweroff` only | — |
| `/run/wifi-fallback/state`, `scan.txt` | Hotspot state for the UI | no |

### 7.4 Visual design
- Dark theme: bg `#0E1116`, panel `#1A1F27`, text `#E8E6E3`, dim `#7A828E`, gold `#F2B544` (next/alert), teal `#4FD1A5` (now/OK), red `#FF6B6B`, blue `#5AA9FF`. AQI colours green/yellow/orange/red/purple/maroon.
- Fonts: DejaVu Sans / Bold at 10–34 px (antialiased; see backlog B-12 for the pixel-font question).
- Pet: mint body `#7ED6A5`, dark outline, pink cheeks, green sprout; hungry = olive body, sleep = dark teal.
- Screenshots: `docs/img/` (generated from code with neutral sample data; `overview.png` shows all states).

## 8. Decision log

| # | Date | Decision | Why | Alternatives rejected |
|---|---|---|---|---|
| D-01 | 10-31 | Enable SSH with an empty `ssh` file; Wi-Fi via a one-time `firstrun.sh` that writes a NetworkManager profile | Bookworm ignores `wpa_supplicant.conf` on the boot partition; image had already booted so Imager's first-run had passed | Editing rootfs from macOS (can't mount ext4) |
| D-02 | 10-31 | Python + Pillow drawing straight to the framebuffer | Lightest path on a Pi 3; no window system; pygame 2 dropped fbcon | pygame/SDL, Qt, a browser kiosk |
| D-03 | 10-31 | Own prayer-time engine (no pip deps) | Pi OS blocks system pip; full control of Kemenag margins | `adhanpy` (used only as a cross-check) |
| D-04 | 10-31 | Kemenag margins fitted to the official schedule: Fajr +2, Sunrise −3, Dhuha +2, Dhuhr +3, Asr +2, Maghrib +3, Isha +2, round up; Imsak = Fajr − 10 | 23/24 exact on 3 dates | Elevation correction (fit was worse) |
| D-05 | 10-31 | Outside Indonesia, pick the method the local mosques use (e.g. Karachi + Hanafi Asr in much of South Asia); verify against a printed local timetable for a few days | Where no official national timetable exists, methods differ by minutes (Isha) to ~50 min (Asr school) | Assuming one global method |
| D-06 | 10-31 | Config in `~/prayerpet.toml` (TOML, stdlib `tomllib`) with defaults in code | Human-editable, survives reinstall | JSON, env vars |
| D-07 | 10-31 | systemd service, `Restart=always` | Auto-start + crash recovery | cron @reboot, rc.local |
| D-08 | 10-31 | Explain the PiTFT cannot be hot-plugged; start at boot instead of "when connected" | HAT has no presence signal; hot-plugging GPIO is unsafe | udev detection |
| D-09 | 10-31 | Installer verbose; ERR trap names the failing line | v1.0 hid apt output and looked frozen | — |
| D-10 | 10-31 | Take the console: KD_GRAPHICS + FBIOPUT_VSCREENINFO + unblank; service gets `CAP_SYS_TTY_CONFIG` | Writes to the DRM fbdev did not show while the console owned the display | Removing fbcon entirely |
| D-11 | 10-31 | Auto-detect the framebuffer by 320×240 size | TFT moved from fb1 to fb0 when HDMI was absent | Hard-coded `/dev/fb1` |
| D-12 | 10-31 | Buttons via gpiozero (lgpio backend), `LG_WD=/tmp` | Works on Bookworm and Pi 5; lgpio writes notify files in the working dir | RPi.GPIO (not on Pi 5) |
| D-13 | 10-31 | Short press fires on release; hold-5 s shutdown on GPIO 27 with sudoers rule for poweroff only | Lets one button do two things without accidental actions; protects the SD card | Separate shutdown button; polkit |
| D-14 | 10-31 | Button labels drawn along a configurable edge, in physical order | Buttons' position depends on rotation; labels must line up | Fixed legend |
| D-15 | 10-31 | Touch made robust to pressure-only drivers; `--input-test` for calibration | Touch did not respond at first | — |
| D-16 | 10-31 | Weather from Open-Meteo, cached on disk | Free, no account, has AQI; works after reboot offline | Paid APIs |
| D-17 | 10-31 | Pet umbrella (rain) and mask (AQI > 150) | Makes data glanceable and fun | Text-only alerts |
| D-18 | 10-31 | Tailscale for remote access; status row shows IP and peers | No port forwarding; works across countries | Port forwarding, ngrok |
| D-19 | 10-31 | Security: keep Debian 12 updated (LTS since 2026-07-12, to 2028-06-30); `full-upgrade` for Pi kernels; unattended-upgrades incl. Raspberry Pi origin; SSH keys only; plan Trixie reinstall before mid-2028 | CVE-2026-98432 (TCP, 9.8) and CVE-2026-46300 (local root, in CISA KEV) in Oct 2026 | — |
| D-20 | 10-31 | log2ram with journald capped at 30 MB, log2ram SIZE 128M, MAIL=false | Reduce SD writes; log2ram failed because the journal was 232 MB | Read-only overlay (loses pet state) |
| D-21 | 10-31 | Setup hotspot via NetworkManager when no known network after 90 s; `wifi-join` helper; retry known networks every 10 min while unused | Pi 3B+ micro-USB is power-only (no USB gadget mode), so no "plug into laptop" option | USB gadget (unsupported on 3B+), editing SD on the Mac |
| D-22 | 10-31 | Show hotspot password on the TFT | Physical presence needed; SSH still needs the owner's key | Hide it |
| D-23 | 10-31 | Installer prints its version; release files named `prayerpet-<version>.tar.gz` | Owner installed a stale `prayerpet.tar.gz` (browser saved the new one as "(1)") | Same file name each time |
| D-24 | 10-31 | ERR trap writes to stderr; `|| true` inside `$(...)` with grep | With `set -E` the trap text leaked into a command substitution and was treated as unit names to disable | — |
| D-25 | 10-31 | `--info` explains "GPIO busy" and console "permission denied" as normal when the service is running | They looked like failures | — |
| D-26 | 10-31 | Inbox folder for cross-process requests instead of sockets | Simple, works for any process as the same user, nothing listening on the network | Unix socket, HTTP API |
| D-27 | 10-31 | No local LLM on the Pi 3B+; use cloud models | Est. 3–5 tokens/s for 270M–0.6B models (Pi 5 does ~10–23); 1 GB RAM | Ollama/llama.cpp |
| D-28 | 10-31 | AI on device = **Antigravity CLI (`agy`)**, not Gemini CLI | Gemini CLI stopped serving Google AI Pro/Ultra individual accounts on 2026-06-18; Antigravity CLI has arm64 Linux builds and SSH sign-in | Gemini CLI |
| D-29 | 10-31 | `/ask` uses a separate free Gemini API key, not the subscription | Subscriptions don't include API access; free tier covers Flash/Flash-Lite; may be used to improve Google products → no private data | Subscription OAuth in scripts |
| D-30 | 10-31 | No OpenClaw on this device | 543 CVEs by Sep 2026, exposed instances, ~12% malicious skills (Feb 2026), prompt-injection risk with shell access; "works but sluggish" on 3B+ | OpenClaw with hardening |
| D-31 | 10-31 | Fixed-command Telegram bot, allow-listed user IDs, private chats only, stdlib only, no shell | Small attack surface; no extra packages to patch | python-telegram-bot, free-form agent |
| D-32 | 10-31 | Bot `HTTP timeout` named `http_timeout` | Test caught a crash: Telegram's `timeout` param clashed with the HTTP timeout argument | — |
| D-33 | 11-01 | Bot follows `HTTPS_PROXY` | Telegram is blocked or throttled on some national networks | — |
| D-34 | 11-01 | `/feed` `/pat` refuse politely while the pet sleeps | Bot said "Fed!" but the app ignored it | Waking the pet |
| D-35 | 11-01 | `/ask` auto-retries with the replacement model Google names in a 404 | `gemini-2.5-flash-lite` retired for new users; default now `gemini-3.5-flash-lite` | Hard fail |
| D-36 | 11-01 | Diagnose power with `vcgencmd get_throttled` + 5-min 4-core load test | Undervoltage `0x50005`; charger (5 V/3 A) was fine, the cable lost too much voltage | USB meter (can't see cable loss) |
| D-37 | 11-01 | Run at `arm_freq=800` with `dtoverlay=disable-bt` on the current cable | Passes the load test (`0x0`); official 5.1 V supply hard to find locally; owner chose to stay at 800 | Higher clocks (not tested) |
| D-38 | 11-01 | Pi 2 v1.1 cannot boot the 64-bit card; TL-WN725N is 2.4 GHz only and AP mode landed in Linux only in Mar 2026 → use Pi 2 as a wired helper (Pi-hole / exit node), not for the pet | Hardware limits | Moving the pet to the Pi 2 |
| D-39 | 11-08 | Repo docs: PRD/AGENTS/HANDSOFF; private details as placeholders | Owner rule: no private info in files without approval | — |
| D-40 | 11-08 | CI on GitHub Actions: Python 3.11 + 3.13, pip `pillow numpy` (CI only; the Pi still uses apt), same two test commands as AGENTS.md | GitHub's starter template failed: no Pillow, and tested 3.9/3.10, which lack `tomllib` | Starter template with pytest + flake8 |

## 9. Release history

| Version | Date | Changes |
|---|---|---|
| 1.0 | 10-31 | Prayer engine (Kemenag fit), pet, status page, framebuffer/PNG/window backends, touch, config, systemd service, installer |
| 1.1 | 10-31 | Console takeover (KD_GRAPHICS, mode set, unblank), `tools/fbtest.py`, installer shows progress and failing line |
| 1.2 | 10-31 | Buttons (17/22/23/27), labels on edge, hold-to-shutdown, `--input-test`, touch pressure fallback |
| 1.3 | 10-31 | Weather page, AQI badge, umbrella/mask, Tailscale row, SSH row merged with users |
| 1.4 | 10-31 | Wi-Fi setup hotspot, `wifi-join`, hotspot banner on all pages |
| 1.5 | 10-31 | Inbox + speech bubble, `--say/--feed/--pat`, Telegram bot, reminders, `/ask`, `GEMINI.md` for the assistant |
| 1.6 | 10-31 | Fixed ERR-trap leak (bogus "Disabled …" lines), false "update running", `--info` explanations, versioned tarball names, `--version` |
| 1.7 | 11-01 | `/feed` `/pat` aware of sleep; `/ask` model fallback; default model `gemini-3.5-flash-lite` |
| repo | 11-08 | Project moved to a repository with tests, packaging script and docs (no app changes) |
| repo | 11-08 | README: "What you need" hardware section (Pi 3B+, PiTFT 2.8" resistive, power, OS; screen driver set up first with Adafruit's installer); scripts marked executable in git (no app changes) |
| repo | 11-08 | GitHub Actions runs the unit tests and the hotspot script test on Python 3.11 and 3.13 (D-40) |

## 10. Security & privacy

- **Threat model:** stranger on Telegram; crafted message text; people on the same Wi-Fi/LAN; lost SD card; secrets leaking into backups or the repo.
- Bot: allow-list + private chats only; no shell; text sanitised; `/ask` sends only times/weather + the question; daily cap.
- Inbox accepts only three kinds; it lives in the owner's home (same-user trust boundary).
- Sudo: one rule, `systemctl poweroff`, for the owner's user.
- Secrets: `~/.prayerpet-telegram.toml` mode 600, never printed (assistant guide forbids it); `.gitignore` excludes it; `scripts/package.sh` refuses to build if a real token or Google key appears.
- Network: nothing listens except SSH (and Tailscale); bot is outbound long-polling. Hotspot is WPA2 with a random password.
- Remote flaw CVE-2026-98432 needs a reachable listening TCP port — device is behind NAT + Tailscale; fixed kernels: 6.12.113 / 6.6.159 (check `uname -r`).
- Privacy in the repo: owner's name, username, hostname, SSIDs, IPs and IDs are placeholders (`<owner>`, `<user>`, `<hostname>`, `<home-wifi>`).

## 11. Operations

- **Deploy:** `bash scripts/package.sh` → `scp dist/prayerpet-<v>.tar.gz <user>@<pi-host>:~` → on the Pi `tar xzf … && cd prayerpet && bash install.sh` → check `installer v<v>` line and `prayerpet --info`.
- **Power check:** `vcgencmd get_throttled` must stay `0x0` during `for i in 1 2 3 4; do timeout 300 sh -c 'while :; do :; done' & done`.
- **Backups:** config backup over SSH (command in HANDSOFF.md); full card image with `dd` when the card is out; store encrypted.
- **SD health:** `sudo dmesg | grep -iE "mmc0|ext4.*error|I/O error"`; `sudo tune2fs -l /dev/mmcblk0p2 | grep -iE "state|errors"`.

## 12. Known issues & limitations

| # | Issue | Impact | Note |
|---|---|---|---|
| K-1 | Touch calibration not yet confirmed on the device after the v1.2 fix | Taps may land in the wrong zone | `prayerpet --input-test` |
| K-2 | Button physical order / edge not yet confirmed | Labels may not line up | `order`, `hint_edge` |
| K-3 | In sleep + rain, umbrella overlaps the "Zz"; umbrella crowds the speech-bubble tail | Cosmetic | see `docs/img/` |
| K-4 | UI mixes pixel scales (pet 5×, hearts/bowl 3×), smooth shapes (umbrella, weather icons) and antialiased fonts | Not "pixel-perfect" per owner's standard | Backlog B-12 |
| K-5 | Maghrib can be 1 min later than Kemenag on some dates | Safe direction | |
| K-6 | Night window uses today's Isha/Fajr; after midnight edge cases rely on `now < wake` | Fine in the tropics; untested at high latitudes | |
| K-7 | `gemini-3.5-flash-lite` free-tier status not confirmed | `/ask` may hit quota/billing | |
| K-8 | Antigravity CLI RAM use on 1 GB unknown; whether it reads `~/.gemini/GEMINI.md` unconfirmed | Assistant may be slow or ignore the guide | |
| K-9 | Telegram may be blocked on some networks | Bot offline there | `HTTPS_PROXY` |
| K-10 | Processor capped at 800 MHz (power) | Slower installs/agy | Remove `arm_freq` with a proper supply |
| K-11 | Raspberry Pi kernel fix for CVE-2026-98432 not confirmed as of 11-01 | Exposure on LAN/tailnet | re-check `uname -r` |

## 13. Backlog / ideas (rough priority)

| # | Idea | Notes |
|---|---|---|
| B-1 | Adhan / chime at prayer time (headphone jack or buzzer on a free GPIO) | Reminder logic exists |
| B-2 | Ramadan mode: Imsak and iftar countdowns, Hijri date with manual day offset | Country moon-sighting differs |
| B-3 | Qibla direction on the status page | Offline, from lat/lon |
| B-4 | Weekly config backup sent through the bot or pulled by the Pi 2 | |
| B-5 | Website + internet-quality monitor (latency, outages) with bot alerts | Could run on the Pi 2 |
| B-6 | Daily AI line from the pet (morning, from weather/AQI/prayer) via `/ask` key | 1–2 requests/day |
| B-7 | Bluetooth presence: pet greets the owner when the phone is near | Needs BT re-enabled |
| B-8 | Pi 2 as Pi-hole + Tailscale exit node at home | D-38 |
| B-9 | Simple button game (word-game prototype) | |
| B-10 | Living-room TV prayer clock (HDMI layout) | Reuses prayer engine |
| B-11 | Fix K-3 overlaps | |
| B-12 | Pixel-consistency pass: single pixel scale for all sprites/effects, pixel-art icons for weather/umbrella, pixel font at native size | Owner's pixel-art standard |
| B-13 | Move to Raspberry Pi OS Trixie (fresh install) before 2028-06-30 | Test app on Python 3.13 (tests already pass on 3.13) |
| B-14 | Upgrade path: Pi 4 (4 GB) or Pi 5; check PiTFT + cooler fit; Pi 5 RTC battery keeps time offline | |

## 14. References

- Kemenag schedule (via myQuran API): `https://api.myquran.com/v2/sholat/jadwal/1301/2026/10/31`
- Adafruit PiTFT 2.8" guide (buttons GPIO 17/22/23/27): https://learn.adafruit.com/adafruit-pitft-28-inch-resistive-touchscreen-display-raspberry-pi
- Open-Meteo forecast / air quality: https://open-meteo.com/en/docs, https://open-meteo.com/en/docs/air-quality-api
- Debian 12 LTS handover: https://www.debian.org/News/2026/20260712.en.html
- Gemini CLI individual accounts stopped (2026-06-18): https://github.com/google-gemini/gemini-cli/discussions/28017
- Antigravity CLI (arm64): https://learn.arm.com/install-guides/antigravity/
- Google AI plans vs Gemini API: https://ai.google.dev/gemini-api/docs/google-ai-plans
- OpenClaw Raspberry Pi requirements: https://docs.openclaw.ai/install/raspberry-pi
- rtl8xxxu AP mode for RTL8188EU (Mar 2026): https://lkml.iu.edu/hypermail/linux/kernel/2603.1/09310.html
- Raspberry Pi 12.5 W micro-USB supply: https://www.raspberrypi.com/products/micro-usb-power-supply/
