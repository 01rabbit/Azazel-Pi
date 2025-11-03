#!/usr/bin/env bash
# Safe setup script to configure wlan0 as an internal AP (172.16.0.0/24)
# This script is intended to be run on the Raspberry Pi that will act as the AP.
# It will prompt before making any system changes. Run as root (sudo).

set -euo pipefail

# --- Configuration (edit before running if desired) ---
SSID="Azazel_Internal"
PASSPHRASE="change-this-to-a-strong-pass"
WLAN_AP="wlan0"
WLAN_UP="wlan1"
INTERNAL_NET="172.16.0.0/24"
AP_IP="172.16.0.254"
DHCPS_START="172.16.0.10"
DHCPS_END="172.16.0.200"
# -----------------------------------------------------

confirm() {
  read -r -p "$1 [y/N]: " ans
  case "$ans" in
    [Yy]*) return 0 ;;
    *) return 1 ;;
  esac
}

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root: sudo $0"
  exit 1
fi

echo "This script will configure $WLAN_AP as an access point with IP $AP_IP and network $INTERNAL_NET."
echo "It will also enable NAT via $WLAN_UP using nftables."
confirm "Continue and modify system files?" || { echo "Aborted."; exit 1; }

echo "Installing required packages (hostapd, dnsmasq, nftables, if missing)..."
apt update
apt install -y hostapd dnsmasq nftables || true

echo "Creating /etc/hostapd/hostapd.conf"
cat > /etc/hostapd/hostapd.conf <<EOF
interface=$WLAN_AP
driver=nl80211
ssid=$SSID
hw_mode=g
channel=6
country_code=JP
ieee80211n=1
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_passphrase=$PASSPHRASE
EOF

echo "Configuring /etc/default/hostapd"
echo "DAEMON_CONF=\"/etc/hostapd/hostapd.conf\"" > /etc/default/hostapd

echo "Backing up /etc/dhcpcd.conf to /etc/dhcpcd.conf.orig if not already backed up..."
if [ ! -f /etc/dhcpcd.conf.orig ]; then
  cp /etc/dhcpcd.conf /etc/dhcpcd.conf.orig
fi

echo "Adding static IP configuration for $WLAN_AP to /etc/dhcpcd.conf"
grep -q "interface $WLAN_AP" /etc/dhcpcd.conf || cat >> /etc/dhcpcd.conf <<EOF

interface $WLAN_AP
static ip_address=$AP_IP/24
nohook wpa_supplicant
EOF

echo "Backing up existing dnsmasq configuration and writing new file /etc/dnsmasq.d/01-wlan0.conf"
if [ -f /etc/dnsmasq.conf ]; then
  cp /etc/dnsmasq.conf /etc/dnsmasq.conf.orig || true
fi
cat > /etc/dnsmasq.d/01-wlan0.conf <<EOF
interface=$WLAN_AP
dhcp-range=$DHCPS_START,$DHCPS_END,24h
dhcp-option=3,$AP_IP
dhcp-option=6,8.8.8.8,8.8.4.4
server=8.8.8.8
domain-needed
bogus-priv
listen-address=127.0.0.1,$AP_IP
EOF

echo "Enabling IPv4 forwarding"
sysctl -w net.ipv4.ip_forward=1
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-azazel.conf

echo "Writing nftables rules to /etc/nftables.conf"
cat > /etc/nftables.conf <<EOF
#!/usr/sbin/nft -f

flush ruleset

table ip nat {
    chain prerouting {
        type nat hook prerouting priority 0; policy accept;
    }
    chain postrouting {
        type nat hook postrouting priority 100; policy accept;
        oifname "$WLAN_UP" masquerade
    }
}

table inet filter {
    chain input {
        type filter hook input priority 0; policy accept;
    }
    chain forward {
        type filter hook forward priority 0; policy drop;
        ct state established,related accept
        iifname "$WLAN_AP" oifname "$WLAN_UP" accept
        iifname "$WLAN_UP" oifname "$WLAN_AP" ct state established,related accept
    }
    chain output {
        type filter hook output priority 0; policy accept;
    }
}
EOF

echo "Applying nftables rules"
nft -f /etc/nftables.conf || true

echo "Enabling and starting services: hostapd, dnsmasq, nftables"
systemctl unmask hostapd || true
systemctl enable hostapd
systemctl restart hostapd || true
systemctl restart dnsmasq || true
systemctl enable nftables || true
systemctl restart nftables || true

echo "Configuration complete. Reboot is recommended to ensure all changes take effect."
echo "Review /etc/hostapd/hostapd.conf and /etc/dnsmasq.d/01-wlan0.conf to change SSID/passphrase/DNS as needed."

exit 0
