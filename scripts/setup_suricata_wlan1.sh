#!/usr/bin/env bash
# Configure Suricata to monitor wlan1 and set HOME_NET to 172.16.0.0/24
# Run as root. This script will backup /etc/suricata/suricata.yaml and /etc/default/suricata

set -euo pipefail

SURICATA_YAML="/etc/suricata/suricata.yaml"
SURICATA_DEFAULT="/etc/default/suricata"
BACKUP_SUFFIX=".orig"
MON_IFACE="wlan1"
HOME_NET_CIDR="172.16.0.0/24"

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root: sudo $0"
  exit 1
fi

if [ ! -f "$SURICATA_YAML" ]; then
  echo "Suricata configuration not found at $SURICATA_YAML. Is suricata installed?"
  exit 1
fi

echo "Backing up $SURICATA_YAML to ${SURICATA_YAML}${BACKUP_SUFFIX} if not present"
if [ ! -f "${SURICATA_YAML}${BACKUP_SUFFIX}" ]; then
  cp "$SURICATA_YAML" "${SURICATA_YAML}${BACKUP_SUFFIX}"
fi

echo "Updating HOME_NET in $SURICATA_YAML to [${HOME_NET_CIDR}]"
# Replace the HOME_NET definition under vars->address-groups; use a conservative perl replace
perl -0777 -pe "s/(address-groups:\s*\n(?:(?:\s+\w+:.*\n)*?)\s*HOME_NET:\s*\[).*?\]/\1${HOME_NET_CIDR}]/s" -i "$SURICATA_YAML" || true

# If replacement didn't run (no existing HOME_NET array), try a fallback that replaces HOME_NET: lines
if ! grep -q "HOME_NET: \[${HOME_NET_CIDR}\]" "$SURICATA_YAML"; then
  perl -0777 -pe "s/(HOME_NET:\s*).*/\1\[${HOME_NET_CIDR}\]/s" -i "$SURICATA_YAML" || true
fi

echo "Backing up $SURICATA_DEFAULT to ${SURICATA_DEFAULT}${BACKUP_SUFFIX} if not present"
if [ -f "$SURICATA_DEFAULT" ] && [ ! -f "${SURICATA_DEFAULT}${BACKUP_SUFFIX}" ]; then
  cp "$SURICATA_DEFAULT" "${SURICATA_DEFAULT}${BACKUP_SUFFIX}"
fi

echo "Configuring Suricata default args to monitor interface $MON_IFACE using af-packet"
# Ensure SURICATA_ARGS contains -i wlan1 --af-packet
if [ -f "$SURICATA_DEFAULT" ]; then
  if grep -q "SURICATA_ARGS" "$SURICATA_DEFAULT"; then
    sed -i "s|^SURICATA_ARGS=.*|SURICATA_ARGS=\"-i ${MON_IFACE} --af-packet\"|" "$SURICATA_DEFAULT"
  else
    echo "SURICATA_ARGS=\"-i ${MON_IFACE} --af-packet\"" >> "$SURICATA_DEFAULT"
  fi
else
  echo "SURICATA_ARGS=\"-i ${MON_IFACE} --af-packet\"" > "$SURICATA_DEFAULT"
fi

echo "Reloading systemd and restarting suricata service"
systemctl daemon-reload || true
systemctl restart suricata || true
systemctl enable suricata || true

echo "Suricata status (last 10 lines)"
systemctl status suricata --no-pager -l | sed -n '1,20p' || true
echo
echo "Recent suricata log (eve.json tail)"
if [ -f /var/log/suricata/eve.json ]; then
  tail -n 20 /var/log/suricata/eve.json || true
else
  echo "/var/log/suricata/eve.json not found; check /var/log/suricata for logs"
fi

echo "Done. Verify that Suricata is capturing on $MON_IFACE and that HOME_NET is set in $SURICATA_YAML"

exit 0
