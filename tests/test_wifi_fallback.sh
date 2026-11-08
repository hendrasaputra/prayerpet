#!/bin/bash
# Simulates NetworkManager with stub commands to test tools/wifi-fallback.
#   case 1: no known network -> hotspot starts -> a new network is saved and the hotspot dropped -> joins it
#   case 2: nobody on the hotspot -> after RETRY_MIN it re-checks known networks (router back after a power cut)
# Run:  bash tests/test_wifi_fallback.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIM="$(mktemp -d)"
[ -n "$SIM" ] && [ -d "$SIM" ] || { echo "mktemp failed"; exit 1; }
mkdir -p "${SIM:?}/bin" "${SIM:?}/st"

cat > "${SIM:?}/bin/nmcli" <<STUB
#!/bin/bash
S=${SIM}/st; args="\$*"
case "\$args" in
  *"device status"*)
    if [ -f \$S/online ]; then echo "wlan0:connected:\$(cat \$S/online)";
    elif [ -f \$S/ap ]; then echo "wlan0:connected:setup-hotspot";
    else echo "wlan0:disconnected:"; fi
    echo "lo:connected (externally):lo";;
  *"connection show --active"*) [ -f \$S/ap ] && echo setup-hotspot; [ -f \$S/online ] && cat \$S/online; true;;
  *"device wifi list"*) [ -f \$S/ap ] && { echo "Other:40:WPA2"; exit 0; }; cat \$S/visible 2>/dev/null; echo "Other:40:WPA2";;
  *"connection up id setup-hotspot"*) touch \$S/ap;;
  *"connection down id setup-hotspot"*) rm -f "\${S:?}/ap";;
  *"-t -f NAME,TYPE connection show"*) echo "setup-hotspot:802-11-wireless"; cat \$S/saved 2>/dev/null; true;;
  *"-g 802-11-wireless.ssid connection show"*) echo "\${@: -1}";;
  *"connection up id "*) name="\${@: -1}"; grep -q "^\$name:" \$S/visible 2>/dev/null && echo "\$name" > \$S/online;;
  *) true;;
esac
STUB
printf '#!/bin/sh\n[ -f %s/st/station ] && echo "Station aa:bb"\n' "$SIM" > "${SIM:?}/bin/iw"
printf '#!/bin/sh\nexit 0\n' > "${SIM:?}/bin/sleep"
chmod +x "${SIM:?}/bin/"*
printf 'AP_CON=setup-hotspot\nAP_SSID=test-setup\nAP_PASS=testpass12\nGRACE=10\nRETRY_MIN=1\n' > "${SIM:?}/st/conf"
sed "s|CONF=/etc/wifi-fallback.conf|CONF=${SIM}/st/conf|; s|RUN=/run/wifi-fallback|RUN=${SIM}/run|" \
  "$ROOT/tools/wifi-fallback" > "${SIM:?}/wf"
chmod +x "${SIM:?}/wf"
fail=0

# --- case 1: user joins a new network through the hotspot
echo "OldNet:802-11-wireless" > "${SIM:?}/st/saved"
touch "${SIM:?}/st/station"
( PATH="${SIM}/bin:$PATH" timeout 20 "${SIM}/wf" >/dev/null 2>&1 ) &
for _ in $(seq 1 100); do [ -f "${SIM}/st/ap" ] && break; /bin/sleep 0.05; done
[ -f "${SIM}/st/ap" ] || { echo "FAIL case 1: hotspot did not start"; fail=1; }
echo "CafeWifi:802-11-wireless" >> "${SIM:?}/st/saved"   # what wifi-join does
echo "CafeWifi:80:WPA2" > "${SIM:?}/st/visible"
rm -f "${SIM:?}/st/ap"                                    # wifi-join brings the hotspot down
wait
if grep -q "^state=online" "${SIM}/run/state" && [ "$(cat "${SIM}/st/online")" = "CafeWifi" ]; then
  echo "ok   case 1: hotspot -> joined CafeWifi"
else
  echo "FAIL case 1"; fail=1
fi

# --- case 2: router comes back while nobody is on the hotspot
rm -rf "${SIM:?}/run"
rm -f "${SIM:?}/st/online" "${SIM:?}/st/ap" "${SIM:?}/st/station" "${SIM:?}/st/visible"
echo "HomeWiFi:802-11-wireless" > "${SIM:?}/st/saved"
echo "HomeWiFi:90:WPA2" > "${SIM:?}/st/visible"
PATH="${SIM}/bin:$PATH" timeout 20 "${SIM}/wf" >/dev/null 2>&1
if grep -q "^state=online" "${SIM}/run/state" && [ "$(cat "${SIM}/st/online")" = "HomeWiFi" ]; then
  echo "ok   case 2: rejoined HomeWiFi after retry"
else
  echo "FAIL case 2"; fail=1
fi

rm -rf "${SIM:?}"
exit $fail
