#!/bin/bash
# Prayer Pet installer for Raspberry Pi OS Bookworm + Adafruit PiTFT 2.8"
# Run from the unpacked folder:   bash install.sh
set -eE
# messages go to stderr so they can never leak into a $(...) result
trap 'echo >&2; echo "!!! install.sh failed at line $LINENO: $BASH_COMMAND" >&2; echo "    Copy the lines above and send them for help." >&2' ERR

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this as your normal user (not with sudo). It will ask for sudo when needed."; exit 1
fi

echo "Prayer Pet installer v1.7"
ME="$(id -un)"
HOMEDIR="$HOME"
SRC="$(cd "$(dirname "$0")" && pwd)"
APP="$HOMEDIR/prayerpet-app"
CMDLINE=/boot/firmware/cmdline.txt

echo "==> 1/6  Installing packages (Pillow, numpy, evdev, fonts)"
echo "     Checking clock and internet..."
echo "     Pi clock says: $(date)"
if ! getent hosts deb.debian.org >/dev/null; then
  echo "!!! The Pi cannot look up deb.debian.org. Check Wi-Fi:  ping -c3 deb.debian.org"; exit 1
fi
if [ "$(date +%Y)" -lt 2025 ]; then
  echo "!!! The Pi clock is wrong. Wait a minute for it to sync (timedatectl), then run again."; exit 1
fi
# (unattended-upgrade-shutdown is always running; only the real upgrade process counts)
if pgrep -x apt-get >/dev/null || pgrep -x apt >/dev/null || pgrep -x dpkg >/dev/null || pgrep -f 'bin/unattended-upgrade( |$)' >/dev/null; then
  echo "     Another update is running in the background (common after first boot)."
  echo "     Waiting for it to finish - this can take several minutes..."
fi
echo "     Updating package lists (1-3 minutes on a Pi 3)..."
sudo apt-get -o DPkg::Lock::Timeout=900 update
echo "     Installing packages (2-5 minutes on a Pi 3)..."
sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=900 install -y \
  python3-pil python3-numpy python3-evdev python3-gpiozero python3-lgpio fonts-dejavu-core iw dnsmasq-base

echo "==> 2/6  Copying the app to $APP"
mkdir -p "$APP"
cp -r "$SRC/prayerpet" "$APP/"
if [ -f "$HOMEDIR/prayerpet.toml" ]; then
  echo "     Keeping your existing ~/prayerpet.toml"
else
  cp "$SRC/prayerpet.toml" "$HOMEDIR/prayerpet.toml"
  echo "     Created ~/prayerpet.toml (edit this to change settings)"
fi

echo "==> 3/6  Adding the 'prayerpet' command"
sudo tee /usr/local/bin/prayerpet >/dev/null <<EOF
#!/bin/sh
LG_WD=/tmp PYTHONPATH="$APP" exec python3 -m prayerpet "\$@"
EOF
sudo chmod +x /usr/local/bin/prayerpet

echo "==> 4/6  Installing the startup service"
sudo tee /etc/systemd/system/prayerpet.service >/dev/null <<EOF
[Unit]
Description=Prayer Pet on the PiTFT
After=systemd-user-sessions.service network.target
Wants=network.target

[Service]
User=$ME
SupplementaryGroups=video input bluetooth tty gpio
AmbientCapabilities=CAP_SYS_TTY_CONFIG
WorkingDirectory=$HOMEDIR
ExecStartPre=/bin/sh -c 'for i in \$(seq 1 20); do ls /dev/fb* >/dev/null 2>&1 && exit 0; sleep 1; done; exit 1'
ExecStart=/usr/local/bin/prayerpet
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=LG_WD=/tmp

[Install]
WantedBy=multi-user.target
EOF
# allow the app to shut the Pi down from the hold-button (and nothing else)
echo "$ME ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff" | sudo tee /etc/sudoers.d/prayerpet >/dev/null
sudo chmod 440 /etc/sudoers.d/prayerpet
sudo visudo -cf /etc/sudoers.d/prayerpet >/dev/null || { sudo rm -f /etc/sudoers.d/prayerpet; echo "     (could not add shutdown permission)"; }
sudo systemctl daemon-reload
sudo systemctl enable prayerpet.service >/dev/null

echo "==> 4b    Wi-Fi setup hotspot (for joining Wi-Fi at a new place)"
if [ ! -f /etc/wifi-fallback.conf ]; then
  AP_PASS=$(tr -dc 'a-km-np-z2-9' </dev/urandom | head -c 10)
  sudo tee /etc/wifi-fallback.conf >/dev/null <<EOF
# Setup hotspot started when no known Wi-Fi is found after boot. Edit, then re-run install.sh
AP_CON=setup-hotspot
AP_SSID=$(hostname)-setup
AP_PASS=$AP_PASS
AP_IP=10.42.0.1
GRACE=90
RETRY_MIN=10
EOF
  sudo chmod 644 /etc/wifi-fallback.conf
fi
# shellcheck disable=SC1091
. /etc/wifi-fallback.conf
sudo nmcli connection delete id "$AP_CON" >/dev/null 2>&1 || true
sudo nmcli connection add type wifi ifname wlan0 con-name "$AP_CON" autoconnect no ssid "$AP_SSID" \
  802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
  ipv4.method shared ipv4.addresses "$AP_IP/24" ipv6.method disabled \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$AP_PASS" wifi-sec.proto rsn \
  wifi-sec.pairwise ccmp wifi-sec.group ccmp wifi-sec.pmf disable >/dev/null
sudo install -m 755 "$SRC/tools/wifi-fallback" /usr/local/sbin/wifi-fallback
sudo install -m 755 "$SRC/tools/wifi-join" /usr/local/bin/wifi-join
sudo tee /etc/systemd/system/wifi-fallback.service >/dev/null <<EOF
[Unit]
Description=Start a Wi-Fi setup hotspot if no known network is found
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=simple
ExecStart=/usr/local/sbin/wifi-fallback
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable wifi-fallback.service >/dev/null
echo "     Hotspot name: $AP_SSID   password: $AP_PASS   (also shown on the TFT when active)"

echo "==> 4c    Telegram bot and AI assistant guide"
SECRETS="$HOMEDIR/.prayerpet-telegram.toml"
if [ ! -f "$SECRETS" ]; then
  cat > "$SECRETS" <<'EOF'
# Telegram bot settings. Keep this file private (it is readable only by you).
# 1. In Telegram, message @BotFather, send /newbot, and paste the token it gives you below.
token = ""
# 2. Send your new bot any message, then run:  prayerpet --bot-whoami
#    and put the user id it shows here. The bot ignores everyone else.
allowed_ids = []
# Prayer reminders sent to you on Telegram
remind_before_minutes = 10   # 0 = off
remind_at_time = true
# Optional: /ask command using a free Gemini API key from https://aistudio.google.com/apikey
gemini_api_key = ""
gemini_model = "gemini-3.5-flash-lite"
ask_daily_limit = 30
EOF
  echo "     Created ~/.prayerpet-telegram.toml (add your bot token there)"
fi
chmod 600 "$SECRETS"
sudo tee /etc/systemd/system/prayerpet-bot.service >/dev/null <<EOF
[Unit]
Description=Prayer Pet Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
User=$ME
WorkingDirectory=$HOMEDIR
ExecStart=/usr/local/bin/prayerpet --bot
Restart=on-failure
RestartSec=15
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
if grep -qE '^token = "[^"]+"' "$SECRETS" && grep -qE '^allowed_ids = \[[0-9]' "$SECRETS"; then
  sudo systemctl enable prayerpet-bot.service >/dev/null
  sudo systemctl restart prayerpet-bot.service
  echo "     Telegram bot running"
else
  echo "     Telegram bot installed but not configured yet (see README: Telegram bot)"
fi
mkdir -p "$HOMEDIR/.gemini"
if [ -f "$HOMEDIR/.gemini/GEMINI.md" ] && ! cmp -s "$SRC/tools/GEMINI.md" "$HOMEDIR/.gemini/GEMINI.md"; then
  cp "$SRC/tools/GEMINI.md" "$HOMEDIR/.gemini/GEMINI.md.prayerpet"
  echo "     You already have ~/.gemini/GEMINI.md; the Pi guide was saved next to it as GEMINI.md.prayerpet"
else
  cp "$SRC/tools/GEMINI.md" "$HOMEDIR/.gemini/GEMINI.md"
  echo "     Added ~/.gemini/GEMINI.md (tells the AI assistant how this Pi works)"
fi

echo "==> 5/6  Making sure nothing else draws on the TFT"
NEED_REBOOT=0
# a) console text was mapped to the TFT (fbcon=map:10) - move it to HDMI
if grep -q "fbcon=map:10" "$CMDLINE"; then
  sudo cp "$CMDLINE" "$CMDLINE.before-prayerpet"
  sudo sed -i 's/ fbcon=map:10//' "$CMDLINE"
  echo "     Removed fbcon=map:10 from cmdline.txt (backup: cmdline.txt.before-prayerpet)"
  NEED_REBOOT=1
fi
# b) HDMI-mirroring helpers from the Adafruit script would overwrite the screen
for u in $(systemctl list-unit-files --no-legend 2>/dev/null | awk '{print $1}' | grep -Ei '^(fbcp|rpi-fbcp|fbcp-ili9341)' || true); do
  sudo systemctl disable --now "$u" >/dev/null 2>&1 || true
  echo "     Disabled $u (it mirrors HDMI onto the TFT)"
done
# c) a desktop session would fight over the screen
if [ "$(systemctl get-default)" = "graphical.target" ]; then
  echo
  echo "     This Pi boots into the desktop. The desktop can take over the TFT."
  read -r -p "     Switch to console boot (recommended)? [Y/n] " ans
  if [ -z "$ans" ] || [[ "$ans" =~ ^[Yy] ]]; then
    sudo raspi-config nonint do_boot_behaviour B1
    echo "     Switched to console boot."
    NEED_REBOOT=1
  fi
fi

echo "==> 6/6  Checking"
prayerpet --times || true
prayerpet --info || true

echo
if [ "$NEED_REBOOT" = "1" ]; then
  echo "Done. Reboot to finish:   sudo reboot"
else
  sudo systemctl restart prayerpet
  echo "Done. Prayer Pet is running. Logs:   journalctl -u prayerpet -f"
fi
