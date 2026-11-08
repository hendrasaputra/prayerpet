# AGENTS.md — how to work on Prayer Pet

Read this first, then `HANDSOFF.md` (current state) and `PRD.md` (features, design, decision log).

## What this is
A Python app for a Raspberry Pi 3 Model B+ with an Adafruit PiTFT 2.8" (320×240, resistive touch, 4 buttons):
prayer times (offline, Kemenag-matched), a pixel pet, weather/air quality, a system monitor, a Telegram bot,
and a Wi-Fi setup hotspot. It runs as systemd services on Raspberry Pi OS Bookworm (64-bit), console boot.

## Repository layout
```
prayerpet/            the Python package (copied to ~/prayerpet-app/prayerpet on the Pi)
  app.py              CLI + main loop + Schedule (awake/alert/prayer/sleep)
  prayer.py           prayer-time engine and method table
  ui.py               all drawing, palette, fonts, id/en strings
  pet.py              pet stats (PetState) and sprite/animation (PetAnimator)
  display.py          framebuffer / PNG / pygame backends
  touch.py buttons.py input threads
  sysinfo.py weather.py  background data threads
  inbox.py            cross-process request folder (~/.prayerpet-inbox)
  bot.py              Telegram bot
  config.py           defaults; merged with ~/prayerpet.toml
tools/                wifi-fallback (root service script), wifi-join, fbtest.py, GEMINI.md (assistant guide for the Pi)
tests/                unittest suite + tests/test_wifi_fallback.sh
scripts/package.sh    test + build dist/prayerpet-<version>.tar.gz
install.sh            on-device installer (idempotent)
prayerpet.toml        settings template (copied to ~ only if missing)
docs/img/             screenshots generated from code
```

## Commands
| Task | Command |
|---|---|
| Run all tests | `python3 -m unittest discover -s tests -t .` and `bash tests/test_wifi_fallback.sh` |
| Build a release | `bash scripts/package.sh` (runs tests, checks versions, refuses to ship secrets) |
| Render a frame | `python3 -m prayerpet --config prayerpet.toml --png /tmp/x.png --at "2026-10-31 14:47" --page home` |
| Regenerate `docs/img` | `python3 scripts/screenshots.py` (all states, placeholder data; or pass an output folder) |
| Preview window (desktop) | `pip install pygame` then `python3 -m prayerpet --config prayerpet.toml --window` |
| Prayer times | `python3 -m prayerpet --config prayerpet.toml --times 2026-12-25` |

Dev machine needs Python ≥ 3.11 with `pillow` and `numpy` (`pip install pillow numpy`; add `gpiozero` to run the button tests).
Tests that need missing packages are skipped, not failed.

## Hard constraints
1. **Python 3.11 compatible** (Bookworm). No 3.12+ syntax or stdlib features. Tests also pass on 3.13 (Trixie).
2. **No pip on the Pi.** Runtime dependencies must come from apt: `python3-pil python3-numpy python3-evdev python3-gpiozero python3-lgpio`. Network code uses `urllib` only. Adding a dependency means adding it to `install.sh` and PRD §5.
3. **Weak hardware.** Pi 3B+ currently capped at 800 MHz (power issue, see HANDSOFF). Keep per-frame work small (fps 4; render ~30 ms on the Pi). Never block the render loop on network or subprocesses — use the existing background threads.
4. **Screen is 320×240.** Check every layout change by rendering PNGs at the alert, prayer, sleep, hungry, rain+smog, hotspot and speech-bubble states (`python3 scripts/screenshots.py`). Look at the images before shipping.
5. **The bot never runs shell commands** and only answers `allowed_ids` in private chats. New bot commands must be fixed, hard-coded handlers. Anything that reaches the screen goes through `inbox.post()`; `inbox.drain()` accepts only `say|feed|pat`.
6. **Settings stay in sync** in three places: `config.py` DEFAULTS, `prayerpet.toml` template (with a plain-language comment), README. The installer never overwrites the user's `~/prayerpet.toml` or `~/.prayerpet-telegram.toml`, so new settings must have defaults in code.
7. **Bilingual strings** (`id` and `en`) for anything on screen or in bot replies.

## Safety rules
- **Privacy:** never write the owner's name, email, username, hostname, Wi-Fi names, IPs, Telegram IDs, tokens or keys into code, docs, tests, commit messages, User-Agent strings or screenshots. Use placeholders (`<owner>`, `<user>`, `<hostname>`, `<home-wifi>`) and ask the owner before using real values.
- **Secrets** live only on the Pi in `~/.prayerpet-telegram.toml` (mode 600). Never print them, never copy them into the repo.
- **Boot files** (`/boot/firmware/config.txt`, `cmdline.txt`): always back up before editing; a mistake can stop the Pi booting, and there is no keyboard attached.
- **Shell scripts:** `set -eE` with an ERR trap that writes to **stderr** (D-24). Guard deletions with `${VAR:?}`. `|| true` on greps inside `$(...)`.
- **Don't reboot, shut down or restart services on the owner's device** unless asked.
- Hardware facts and third-party APIs change — verify against current docs before relying on them (e.g. Gemini model names, Telegram reachability, Raspberry Pi kernels). Record what you verified and when in PRD.

## Release process
1. Bump `__version__` in `prayerpet/__init__.py` **and** the `echo "Prayer Pet installer vX.Y"` line in `install.sh` (package.sh checks they match).
2. Run `bash scripts/package.sh` → `dist/prayerpet-X.Y.tar.gz`. Always version the file name (D-23).
3. Add a row to PRD §9 Release history; add decisions to PRD §8; update HANDSOFF.md.
4. Owner deploys: `scp dist/prayerpet-X.Y.tar.gz <user>@<pi-host>:~`, then on the Pi
   `cd ~ && tar xzf prayerpet-X.Y.tar.gz && cd prayerpet && bash install.sh` — first line must show the new version.
5. Verify on device: `prayerpet --info`, `journalctl -u prayerpet -n 20`, Telegram `/status` and `/screen`.

## Testing on the device (owner runs; you read the output)
| Check | Command | Good result |
|---|---|---|
| Version/devices | `prayerpet --info` | version, `service: active`, screen `ili9341drmfb 320x240`, touch `stmpe-ts`, telegram configured |
| Screen ownership | `journalctl -u prayerpet -b \| grep screen:` | `console on /dev/tty1 paused`, no `failed` |
| Touch/buttons | `sudo systemctl stop prayerpet; prayerpet --input-test` | TOUCH lines; BUTTON GPIOxx lines |
| Raw screen | `sudo python3 tools/fbtest.py /dev/fb0` | red/green/blue |
| Power | `vcgencmd get_throttled` under the 5-min load test | `0x0` |
| Hotspot | see HANDSOFF "Wi-Fi hotspot test" | joins hotspot, `wifi-join` works |

## Pixel art standard (owner's rules — apply to all new art)
- One pixel size for everything: sprites, effects and UI icons on the same pixel grid (the pet uses 5×; new art should use the same scale or a whole-number scale chosen deliberately for the whole UI).
- Nearest-neighbour only; no smoothing, no rotation of pixel art at runtime (use hand-drawn frames or 90° steps).
- Snap all positions to whole pixels of the chosen grid.
- Pixel fonts at native size with antialiasing off, if/when a pixel font is adopted.
- Effects/particles on the same grid. Place any new asset next to the pet at 1× to check pixel sizes match.
- Current deviations are listed in PRD K-4 / B-12 — don't add more; fix them when touching that code.

## Writing style for anything the owner reads
(README, installer output, bot replies, on-screen text, HANDSOFF)
- Lead with the instruction, then the reason. Name who does what. One idea per sentence.
- No noun stacks; turn abstract nouns into verbs. Define jargon inline the first time.
- State consequences concretely ("the SD card can corrupt"), not as category names.
- Test: could someone new act on it today without asking what a word means?

## Keep the docs current
After any change: update `HANDSOFF.md` (state, open threads), PRD §8 decisions (date, why, alternatives), §9 release history, §12 known issues, §13 backlog.
