# HANDSOFF — current state (2026-11-08)

Snapshot for whoever picks this up next (human or Claude Code). Update it after every session.

## Where things stand
- **Deployed version on the Pi: 1.8** (11-08, installed by Claude over SSH; service active, no errors in the log, live framebuffer capture shows the new art).
- All tests pass: `python3 -m unittest discover -s tests -t .` (24 tests) and `bash tests/test_wifi_fallback.sh` (2 scenarios). Locally, install `pillow numpy` or 7 tests are skipped; CI runs them all.
- The repo is public on GitHub. README lists the required hardware ("What you need"); the screen driver comes from Adafruit's PiTFT installer, not `install.sh`.
- GitHub Actions (`.github/workflows/python-package.yml`) runs both test commands on Python 3.11 and 3.13 on every push to `main`.
- `python3 scripts/screenshots.py` regenerates every image in `docs/img` (placeholder data; login name forced to `user`).
- Claude can reach the Pi over SSH from the owner's Mac (login kept out of the repo). Read-only checks are fine; ask before sudo, upgrades, restarts or reboots.

## Device state (checked over SSH on 11-08 unless noted)
| Area | State | Verified? |
|---|---|---|
| Hardware | Pi 3B+, PiTFT 2.8" resistive, 4 buttons | yes |
| OS | Raspberry Pi OS Bookworm 64-bit, console boot | yes |
| Framebuffer | `/dev/fb1` (`ili9341drmfb`, 320×240, 32 bpp) — auto-detected | yes |
| Screen app | 1.8, `service: active`, console paused at boot, touch `stmpe-ts`, buttons on GPIO 17/22/23/27 | yes |
| Location config | set on the device in `~/prayerpet.toml` (not recorded in the repo); Asr school confirmed by the owner | yes |
| Touch, buttons | calibrated by the owner (`[touch]`, `[buttons] order / hint_edge` set) | yes (owner) |
| Config backup | taken by the owner | yes (owner) |
| fps | 4 | yes |
| Telegram bot | running. Long run of connection time-outs on 11-03 (~20 min), recovered by itself | yes |
| `/ask` | key and `gemini-3.5-flash-lite` are valid (model lookup 11-08); used once on 11-06. The bot doesn't log `/ask` errors, so the answer itself is unconfirmed | **owner: send one `/ask`** |
| Antigravity CLI (`agy`) | installed, signed in | **whether it reads `~/.gemini/GEMINI.md` not confirmed** |
| Tailscale | running; 1.104.4 installed, 1.104.5 available | yes |
| Wi-Fi setup hotspot | installed and tested by the owner | yes |
| log2ram | working; journald capped at 30 MB | yes (11-01) |
| SD card | 4.9 GB used of 235 GB; health clean on 11-01 | yes |
| Power | `get_throttled` = `0x0`, 800 MHz, 62 °C | yes — owner chose to **stay at 800 MHz** |
| CPU load | load ~4.6 shortly after boot. Two `node` worker processes from the owner's other project (nice 10) use most of it; the screen app uses ~44 % of one core (K-12) | yes |
| Kernel CVE-2026-98432 | **running 6.12.109 — not fixed** (needs ≥ 6.12.113); 6.12.115 is waiting in apt | **owner: `sudo apt full-upgrade -y` then reboot** |
| Unattended upgrades | enabled, but only Debian origins. The Raspberry Pi origin (kernels, firmware) is missing, so kernels never update by themselves | **owner decision** |
| SSH | `PasswordAuthentication yes` — passwords still accepted | **owner decision: keys only** |
| sudo | works without a password for the owner's user (so `install.sh` runs over SSH) | yes — together with password SSH login this means a guessed password gives root |

## Open threads (suggested next steps)
1. Look at 1.8 on the screen in daylight and rain (umbrella, hearts, weather icons) and say what to change.
2. Security: `sudo apt update && sudo apt full-upgrade -y`, reboot, check `uname -r` ≥ 6.12.113. Add `"origin=Raspberry Pi Foundation,codename=${distro_codename},label=Raspberry Pi Foundation";` to `/etc/apt/apt.conf.d/50unattended-upgrades`. Turn off SSH passwords once key login is tested from every device.
3. Send one `/ask` to confirm it answers; if not, read the error in the reply.
4. K-12: profile why the screen app uses ~44 % of a core.
5. B-12 part 2: pixel font (bundle an OFL bitmap font, or add an apt package) and pixel UI chrome. Owner to choose.
6. Next features the owner showed interest in: prayer chime (B-1), Ramadan mode (B-2), Pi 2 as Pi-hole + Tailscale exit node (B-8), weekly backup via bot (B-4).

## How to deploy a change
```
bash scripts/package.sh                         # tests + dist/prayerpet-X.Y.tar.gz
scp dist/prayerpet-X.Y.tar.gz <user>@<pi-host>:~
# on the Pi:
cd ~ && tar xzf prayerpet-X.Y.tar.gz && cd prayerpet && bash install.sh
prayerpet --info
```
The installer's first line must show the new version. If it doesn't, the wrong file was copied (browsers rename repeat downloads to "name (1).tar.gz").

## Useful owner-side commands
```
journalctl -u prayerpet -n 30 --no-pager        # screen app log
journalctl -u prayerpet-bot -n 30 --no-pager    # bot log
vcgencmd get_throttled                          # 0x0 = power OK
prayerpet --times                               # today's times for the configured place
```

## Config backup (run on the Mac; nothing private is written into the repo)
```
ssh <user>@<pi-host> 'apt-mark showmanual > /tmp/packages.txt; sudo tar czf - --ignore-failed-read \
  $HOME/prayerpet.toml $HOME/.prayerpet-state.json $HOME/.prayerpet-telegram.toml $HOME/.gemini \
  $HOME/.ssh/authorized_keys /etc/NetworkManager/system-connections /etc/wifi-fallback.conf /etc/log2ram.conf \
  /etc/systemd/journald.conf.d /etc/ssh/sshd_config.d /etc/apt/apt.conf.d/50unattended-upgrades \
  /etc/sudoers.d/prayerpet /etc/systemd/system/prayerpet.service /etc/systemd/system/prayerpet-bot.service \
  /etc/systemd/system/wifi-fallback.service /boot/firmware/config.txt /boot/firmware/cmdline.txt \
  /tmp/packages.txt 2>/dev/null' > ~/pi-backup-$(date +%F).tar.gz
```
Contains secrets (bot token, Gemini key, Wi-Fi passwords): keep it encrypted, outside this repo. Tailscale state is deliberately excluded — after a restore run `sudo tailscale up`.

## Wi-Fi hotspot test (at home)
```
sudo nmcli connection modify <home-wifi> connection.autoconnect no && sudo reboot
# ~2 min later join "<hostname>-setup" from the Mac (password on the TFT), then:
ssh <user>@10.42.0.1
sudo nmcli connection modify <home-wifi> connection.autoconnect yes
sudo nmcli connection down setup-hotspot
```

## Lessons learned (don't repeat)
- Bookworm ignores `wpa_supplicant.conf` on the boot partition; use NetworkManager profiles.
- With `set -E`, an ERR trap that prints to stdout leaks into `$(...)` — print to stderr.
- `pgrep -f unattended-upgr` always matches the idle shutdown helper; match `bin/unattended-upgrade( |$)`.
- The DRM fbdev display doesn't show writes while the text console owns it; take the VT (`KD_GRAPHICS`).
- The TFT can be `/dev/fb0` or `/dev/fb1`; detect by size.
- In `urllib` wrappers, don't name the HTTP timeout `timeout` if API params also use `timeout` (Telegram long-poll).
- Gemini CLI no longer accepts Google AI Pro sign-ins (2026-06-18); use Antigravity CLI (`agy`). Consumer subscriptions don't include API access.
- Google retires Gemini model names; read the 404 message (it names the replacement).
- "LOW VOLT" with a 3 A charger was the cable. Test with `vcgencmd get_throttled` under a 4-core load.
- Ship versioned tarball names; check the installer's version line.
- The Pi 3B+ micro-USB port is power-only (no USB gadget mode).
- Pi 2 v1.1 is 32-bit only; TL-WN725N is 2.4 GHz only with no AP mode on current Pi kernels.
