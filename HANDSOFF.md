# HANDSOFF — current state (2026-11-08)

Snapshot for whoever picks this up next (human or Claude Code). Update it after every session.

## Where things stand
- **Deployed version on the Pi: 1.7.** This repo contains exactly 1.7 plus tests, scripts and docs (no app changes since).
- All tests pass: `python3 -m unittest discover -s tests -t .` (24 tests) and `bash tests/test_wifi_fallback.sh` (2 scenarios).
- The repo is public on GitHub. README lists the required hardware ("What you need"); the screen driver comes from Adafruit's PiTFT installer, not `install.sh`.
- Everything was built and tested in a cloud workspace; the owner installs on the Pi by hand (scp + `install.sh`). Claude cannot reach the Pi directly unless the owner runs commands or links a shell.

## Device state (owner-reported)
| Area | State | Verified? |
|---|---|---|
| Hardware | Pi 3B+, PiTFT 2.8" resistive, 4 buttons | yes |
| OS | Raspberry Pi OS Bookworm 64-bit, console boot | yes |
| Framebuffer | `/dev/fb0` or `/dev/fb1` (`ili9341drmfb`, 320×240, 32 bpp) — auto-detected | yes |
| Screen app | `prayerpet.service` running, screen shows pages | yes |
| Location config | Set on the device in `~/prayerpet.toml` (not recorded in the repo) | **Asr school (shafi vs hanafi) — owner to confirm** |
| Telegram bot | running; `/times /status /screen /pet /feed` confirmed working in a screenshot | yes |
| `/ask` | key set; model changed to `gemini-3.5-flash-lite` after a 404 | **not yet confirmed working** |
| Antigravity CLI (`agy`) | installed, signed in | **whether it reads `~/.gemini/GEMINI.md` not confirmed** |
| Tailscale | installed and running (status page shows an IP) | yes |
| Wi-Fi setup hotspot | installed and tested by the owner | yes |
| log2ram | working; journald capped at 30 MB; log2ram SIZE 128M, MAIL=false | yes |
| SD card health | `dmesg` clean; `tune2fs`: state clean, no error count | yes (11-01) |
| Power | New short micro-USB cable + 5 V/3 A USB-A charger; `arm_freq=800` and `dtoverlay=disable-bt` in `/boot/firmware/config.txt`; 5-min load test `0x0` | yes — owner chose to **stay at 800 MHz** |
| Touch | v1.2 fix shipped; calibration | **not confirmed** (run `prayerpet --input-test`) |
| Buttons | working via gpiozero | **physical `order` and `hint_edge` not confirmed** |
| Security updates | advised: `full-upgrade`, unattended-upgrades incl. Raspberry Pi origin, SSH keys only | **not confirmed which were done** |
| Kernel CVE-2026-98432 | Raspberry Pi kernel fix not confirmed as of 11-01 | **check `uname -r` ≥ 6.12.113** |
| Config backup | command provided | **not confirmed taken** |
| fps | may have been set to 2 during power tests | check `grep fps ~/prayerpet.toml` (4 is normal) |

## Open threads (suggested next steps)
1. Confirm `/ask` works with `gemini-3.5-flash-lite`; if quota/billing errors, pick a free-tier Flash-Lite model from the list command in PRD/README.
2. Run `prayerpet --input-test`; set `[touch]` calibration and `[buttons] order / hint_edge`.
3. Take the config backup (below) and a full SD image; store encrypted.
4. Check kernel version for the CVE fix; run `sudo apt update && sudo apt full-upgrade -y` and reboot.
5. Fix cosmetic overlaps K-3 and start the pixel-consistency pass B-12 (PRD).
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
