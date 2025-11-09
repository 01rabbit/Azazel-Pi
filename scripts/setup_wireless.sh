#!/usr/bin/env bash
# Unified Wireless Network Setup for Azazel-Pi
# Configures an internal AP (default ${AZAZEL_LAN_IF:-wlan0}) and an upstream/monitoring interface (default ${AZAZEL_WAN_IF:-wlan1}).
# Interfaces may be overridden by environment variables: AZAZEL_LAN_IF (AP) and AZAZEL_WAN_IF (upstream).
# Run as root (sudo)

set -euo pipefail

# --- Configuration ---
SSID="Azazel_Internal"
PASSPHRASE="change-this-to-a-strong-pass"
# Allow environment overrides for interfaces. Precedence: AZAZEL_LAN_IF for AP, AZAZEL_WAN_IF for upstream
WLAN_AP="${AZAZEL_LAN_IF:-wlan0}"              # Internal AP interface (default ${AZAZEL_LAN_IF:-wlan0})
WLAN_UP="${AZAZEL_WAN_IF:-wlan1}"              # Upstream/monitoring interface (default ${AZAZEL_WAN_IF:-wlan1})
INTERNAL_NET="172.16.0.0/24"
AP_IP="172.16.0.254"
DHCPS_START="172.16.0.10"
DHCPS_END="172.16.0.200"
HOME_NET_CIDR="172.16.0.0/24"  # Suricata HOME_NET
# -------------------

# Color output functions
log() {
  printf '\033[1;34m[wireless-setup]\033[0m %s\n' "$1"
}

error() {
  printf '\033[1;31m[wireless-setup]\033[0m %s\n' "$1" >&2
  exit 1
}

warn() {
  printf '\033[1;33m[wireless-setup]\033[0m %s\n' "$1"
}

success() {
  printf '\033[1;32m[wireless-setup]\033[0m %s\n' "$1"
}

confirm() {
  read -r -p "$1 [y/N]: " ans
  case "$ans" in
    [Yy]*) return 0 ;;
    *) return 1 ;;
  esac
}

usage() {
  cat <<USAGE
Usage: $0 [OPTIONS]

Configure wireless interfaces for Azazel-Pi:
- ${AZAZEL_LAN_IF:-wlan0}: Internal Access Point (172.16.0.0/24)
- ${AZAZEL_WAN_IF:-wlan1}: Upstream connection + Suricata monitoring

Options:
  --ap-only           Configure only AP (default: ${AZAZEL_LAN_IF:-wlan0}), skip Suricata setup
  --suricata-only     Configure only Suricata monitoring (default: ${AZAZEL_WAN_IF:-wlan1}), skip AP
  --skip-confirm      Skip interactive confirmations (for automation)
  --ssid NAME         Set AP SSID (default: $SSID)
  --passphrase PASS   Set AP passphrase (default: $PASSPHRASE)
  -h, --help          Show this help

Configuration Overview:
  AP Interface:     $WLAN_AP -> $AP_IP
  Monitor Interface: $WLAN_UP (Suricata monitoring)
  Internal Network:  $INTERNAL_NET
  DHCP Range:       $DHCPS_START - $DHCPS_END
  HOME_NET:         $HOME_NET_CIDR

USAGE
}

# Parse arguments
SETUP_AP=1
SETUP_SURICATA=1
SKIP_CONFIRM=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ap-only)
      SETUP_SURICATA=0
      shift
      ;;
    --suricata-only)
      SETUP_AP=0
      shift
      ;;
    --skip-confirm)
      SKIP_CONFIRM=1
      shift
      ;;
    --ssid)
      SSID="$2"
      shift 2
      ;;
    --passphrase)
      PASSPHRASE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      error "Unknown option: $1. Use --help for usage."
      ;;
  esac
done

# Check for root privileges
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  error "This script must be run as root. Use sudo."
fi

# Check interfaces exist
if [[ $SETUP_AP -eq 1 ]] && ! ip link show "$WLAN_AP" >/dev/null 2>&1; then
  error "Interface $WLAN_AP not found. Check hardware configuration."
fi

if [[ $SETUP_SURICATA -eq 1 ]] && ! ip link show "$WLAN_UP" >/dev/null 2>&1; then
  error "Interface $WLAN_UP not found. Check hardware configuration."
fi

# Display configuration summary
log "Unified Wireless Network Setup for Azazel-Pi"
echo
echo "Configuration Summary:"
  echo "  AP Interface (${WLAN_AP}):     $([ $SETUP_AP -eq 1 ] && echo "✓ Configure as $AP_IP" || echo "✗ Skip")"
  echo "  Monitor Interface (${WLAN_UP}): $([ $SETUP_SURICATA -eq 1 ] && echo "✓ Configure for Suricata" || echo "✗ Skip")"
echo "  Internal Network:         $INTERNAL_NET"
echo "  AP SSID:                  $SSID"
echo "  DHCP Range:               $DHCPS_START - $DHCPS_END"
echo

# Confirmation
if [[ $SKIP_CONFIRM -eq 0 ]]; then
  confirm "Proceed with wireless configuration?" || { echo "Aborted."; exit 1; }
fi

# Function: Setup Access Point (${AZAZEL_LAN_IF:-wlan0})
setup_access_point() {
  log "Setting up Access Point on $WLAN_AP"
  
  # Install required packages
  log "Installing AP packages (hostapd, dnsmasq, nftables)..."
  apt update -qq
  apt install -y hostapd dnsmasq nftables || warn "Some packages may already be installed"
  
  # Configure hostapd
  log "Creating hostapd configuration..."
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
  
  # Configure hostapd default
  echo "DAEMON_CONF=\"/etc/hostapd/hostapd.conf\"" > /etc/default/hostapd
  
  # Backup and configure dhcpcd
  log "Configuring static IP for $WLAN_AP..."
  if [[ ! -f /etc/dhcpcd.conf.orig ]]; then
    cp /etc/dhcpcd.conf /etc/dhcpcd.conf.orig
    log "Backed up dhcpcd.conf"
  fi
  
  # Add static IP configuration if not present
  if ! grep -q "interface $WLAN_AP" /etc/dhcpcd.conf; then
    cat >> /etc/dhcpcd.conf <<EOF

# Azazel-Pi AP Configuration
interface $WLAN_AP
static ip_address=$AP_IP/24
nohook wpa_supplicant
EOF
  fi
  
  # Configure dnsmasq for DHCP
  log "Configuring DHCP server..."
  if [[ -f /etc/dnsmasq.conf && ! -f /etc/dnsmasq.conf.orig ]]; then
    cp /etc/dnsmasq.conf /etc/dnsmasq.conf.orig
  fi
  
  cat > /etc/dnsmasq.d/01-azazel-ap.conf <<EOF
interface=$WLAN_AP
dhcp-range=$DHCPS_START,$DHCPS_END,24h
dhcp-option=3,$AP_IP
dhcp-option=6,8.8.8.8,8.8.4.4
server=8.8.8.8
domain-needed
bogus-priv
listen-address=127.0.0.1,$AP_IP
EOF
  
  # Enable IPv4 forwarding
  log "Enabling IP forwarding..."
  sysctl -w net.ipv4.ip_forward=1 >/dev/null
  echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-azazel.conf
  
  # Configure nftables for NAT
  log "Configuring NAT rules..."
  cat > /etc/nftables.conf <<EOF
#!/usr/sbin/nft -f
# Azazel-Pi NAT Configuration

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
  
  # Apply nftables rules
  nft -f /etc/nftables.conf || warn "nftables rules may have issues"
  
  # Exclude ${AZAZEL_LAN_IF:-wlan0} from NetworkManager management
  log "Configuring NetworkManager to ignore $WLAN_AP..."
  mkdir -p /etc/NetworkManager/conf.d
[ -n "$WLAN_AP" ] || error "WLAN_AP not set"
  cat > /etc/NetworkManager/conf.d/unmanaged-${WLAN_AP}.conf <<EOF
[keyfile]
unmanaged-devices=interface-name:$WLAN_AP
EOF
  systemctl reload NetworkManager 2>/dev/null || true
  
  # Configure systemd-networkd for persistent IP on ${AZAZEL_LAN_IF:-wlan0}
  log "Configuring systemd-networkd for persistent IP..."
  mkdir -p /etc/systemd/network
  cat > /etc/systemd/network/10-${WLAN_AP}.network <<EOF
[Match]
Name=$WLAN_AP

[Network]
Address=$AP_IP/24
EOF
  systemctl enable systemd-networkd || true
  systemctl start systemd-networkd || true
  
  # Enable and start services
  log "Starting AP services..."
  systemctl unmask hostapd || true
  systemctl enable hostapd dnsmasq nftables
  systemctl restart hostapd || warn "hostapd restart failed"
  systemctl restart dnsmasq || warn "dnsmasq restart failed"
  systemctl restart nftables || warn "nftables restart failed"
  
  success "Access Point configuration completed"
}

# Function: Setup Suricata Monitoring (${AZAZEL_WAN_IF:-wlan1})
setup_suricata_monitoring() {
  log "Setting up Suricata monitoring on $WLAN_UP"
  
  # Check if Suricata is installed
  if [[ ! -f /etc/suricata/suricata.yaml ]]; then
    warn "Suricata not found. Install with: sudo apt install suricata suricata-update"
    return 1
  fi
  
  SURICATA_YAML="/etc/suricata/suricata.yaml"
  SURICATA_DEFAULT="/etc/default/suricata"
  
  # Backup configurations
  if [[ ! -f "${SURICATA_YAML}.orig" ]]; then
    cp "$SURICATA_YAML" "${SURICATA_YAML}.orig"
    log "Backed up suricata.yaml"
  fi
  
  if [[ -f "$SURICATA_DEFAULT" && ! -f "${SURICATA_DEFAULT}.orig" ]]; then
    cp "$SURICATA_DEFAULT" "${SURICATA_DEFAULT}.orig"
    log "Backed up suricata default config"
  fi
  
  # Update HOME_NET in suricata.yaml
  log "Configuring HOME_NET to $HOME_NET_CIDR..."
  perl -0777 -pe "s/(address-groups:\\s*\\n(?:(?:\\s+\\w+:.*\\n)*?)\\s*HOME_NET:\\s*\\[).*?\\]/\\1${HOME_NET_CIDR}\\]/s" -i "$SURICATA_YAML" || true
  
  # Fallback HOME_NET update
  if ! grep -q "HOME_NET: \\[${HOME_NET_CIDR}\\]" "$SURICATA_YAML"; then
    perl -0777 -pe "s/(HOME_NET:\\s*).*/\\1\\[${HOME_NET_CIDR}\\]/s" -i "$SURICATA_YAML" || true
  fi
  
  # Configure interface monitoring
  log "Configuring Suricata to monitor $WLAN_UP..."
  if [[ -f "$SURICATA_DEFAULT" ]]; then
    if grep -q "SURICATA_ARGS" "$SURICATA_DEFAULT"; then
      sed -i "s|^SURICATA_ARGS=.*|SURICATA_ARGS=\"-i ${WLAN_UP} --af-packet\"|" "$SURICATA_DEFAULT"
    else
      echo "SURICATA_ARGS=\"-i ${WLAN_UP} --af-packet\"" >> "$SURICATA_DEFAULT"
    fi
  else
    echo "SURICATA_ARGS=\"-i ${WLAN_UP} --af-packet\"" > "$SURICATA_DEFAULT"
  fi
  
  # Restart Suricata
  log "Restarting Suricata service..."
  systemctl daemon-reload
  systemctl enable suricata || warn "Failed to enable suricata"
  systemctl restart suricata || warn "Failed to restart suricata"
  
  success "Suricata monitoring configuration completed"
}

# Function: Display status
show_status() {
  log "Configuration Status Check"
  echo
  
  if [[ $SETUP_AP -eq 1 ]]; then
    echo "📡 Access Point Status:"
    if systemctl is-active --quiet hostapd; then
      success "  ✓ hostapd: running"
    else
      warn "  ✗ hostapd: not running"
    fi
    
    if systemctl is-active --quiet dnsmasq; then
      success "  ✓ dnsmasq: running"
    else
      warn "  ✗ dnsmasq: not running"
    fi
    
    if ip addr show "$WLAN_AP" | grep -q "$AP_IP"; then
      success "  ✓ $WLAN_AP: $AP_IP configured"
    else
      warn "  ✗ $WLAN_AP: IP not configured"
    fi
    echo
  fi
  
  if [[ $SETUP_SURICATA -eq 1 ]]; then
    echo "🔍 Suricata Monitoring Status:"
    if systemctl is-active --quiet suricata; then
      success "  ✓ suricata: running"
    else
      warn "  ✗ suricata: not running"
    fi
    
    if [[ -f /var/log/suricata/eve.json ]]; then
      success "  ✓ eve.json: logging active"
      echo "    Recent events: $(tail -n 1 /var/log/suricata/eve.json 2>/dev/null | wc -l) line(s)"
    else
      warn "  ✗ eve.json: no log found"
    fi
    echo
  fi
  
  # Network connectivity test
  echo "🌐 Network Status:"
  if ping -c1 -W2 8.8.8.8 >/dev/null 2>&1; then
    success "  ✓ Internet connectivity: OK"
  else
    warn "  ✗ Internet connectivity: Failed"
  fi
}

# Main execution
log "Starting unified wireless setup..."

# Execute setup functions based on options
if [[ $SETUP_AP -eq 1 ]]; then
  setup_access_point
fi

if [[ $SETUP_SURICATA -eq 1 ]]; then
  setup_suricata_monitoring
fi

# Show final status
show_status

# Final messages
echo
log "Setup completed! Summary:"
if [[ $SETUP_AP -eq 1 ]]; then
  echo "  📡 AP Network: $SSID (password: $PASSPHRASE)"
  echo "  🏠 Internal IP: $AP_IP"
  echo "  📱 Client range: $DHCPS_START - $DHCPS_END"
fi

if [[ $SETUP_SURICATA -eq 1 ]]; then
  echo "  🔍 Monitoring: $WLAN_UP interface"
  echo "  🏠 HOME_NET: $HOME_NET_CIDR"
fi

echo
if [[ $SETUP_AP -eq 1 ]]; then
  warn "Reboot recommended to ensure all wireless changes take effect"
  echo "To modify SSID/password, edit /etc/hostapd/hostapd.conf"
fi

if [[ $SETUP_SURICATA -eq 1 ]]; then
  echo "Check Suricata logs: tail -f /var/log/suricata/eve.json"
  echo "View Suricata status: systemctl status suricata"
fi

exit 0