# This machine: a Raspberry Pi 3 Model B+ running Prayer Pet

You are running on a small Raspberry Pi (1 GB RAM, SD card, Raspberry Pi OS Bookworm 64-bit)
with an Adafruit 2.8" 320x240 touchscreen (PiTFT) and 4 buttons. The owner talks to you over SSH.
Keep answers short. Prefer reading over changing.

## What runs here
- `prayerpet.service` — the screen app: prayer times, a pixel pet, weather/air quality, system status.
  Code: ~/prayerpet-app/prayerpet/  Settings: ~/prayerpet.toml  Pet save file: ~/.prayerpet-state.json
- `prayerpet-bot.service` — Telegram bot with fixed commands. Secrets: ~/.prayerpet-telegram.toml (never print the token).
- `wifi-fallback.service` — starts a setup hotspot when no known Wi-Fi is found at boot.
- `log2ram` — logs live in RAM and are copied to the SD card daily.
- Tailscale for remote access.

## Talking to the screen (safe, no sudo needed)
- Show a message in the pet's speech bubble:  `prayerpet --say "TEXT" --minutes 30`
  Keep it under ~120 characters so it fits on one or two pages. Plain text, no markdown.
- Feed or pat the pet:  `prayerpet --feed`   `prayerpet --pat`
- Prayer times:  `prayerpet --times`   Weather + air quality:  `prayerpet --weather`
- Screenshot of a page:  `prayerpet --png ~/shot.png --page home|weather|status`
- Detected screen/touch/buttons:  `prayerpet --info`

## Useful read-only checks
- App logs: `journalctl -u prayerpet -n 50 --no-pager`   Bot logs: `journalctl -u prayerpet-bot -n 50 --no-pager`
- Kernel version (security patch level): `uname -r`
- Disk, memory, temperature: `df -h /`, `free -h`, `vcgencmd measure_temp`, `vcgencmd get_throttled`
- Wi-Fi: `nmcli device status`, `wifi-join --list`

## Rules
1. Ask before any command that uses sudo, installs packages, restarts services, or edits files outside ~/.
2. Never edit /boot/firmware/cmdline.txt or /boot/firmware/config.txt without making a backup copy first,
   and explain that a mistake there can stop the Pi from booting.
3. Never reboot or shut down unless the owner asks in this conversation.
4. Never print, copy or send secrets: ~/.prayerpet-telegram.toml, /etc/wifi-fallback.conf, ~/.ssh, Tailscale keys.
5. Memory is tight (1 GB). Do not start heavy programs (browsers, compilers, large downloads) without asking.
6. After changing ~/prayerpet.toml, apply it with `sudo systemctl restart prayerpet` (ask first).
