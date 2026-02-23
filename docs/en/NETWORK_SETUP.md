# Network Setup Guide

This guide covers network configuration for Azazel-Edge deployments, including automatic setup via the installer and manual configuration procedures for advanced use cases.

## Overview

Azazel-Edge can operate in multiple network modes:

1. **Gateway Mode**: Acting as a Wi-Fi access point with internet sharing
2. **Monitor Mode**: Monitoring existing network traffic without routing
3. **Bridge Mode**: Transparent inline monitoring between network segments

The installer provides automatic configuration for most scenarios, with manual options available for specialized deployments.

Note on interface names and dynamic selection:

- Many examples in this guide use common interface names such as `wlan0`, `wlan1`, or `eth0` for clarity. These are examples only.
- Azazel now supports dynamic WAN selection via the `wan-manager`. If you omit `--wan-if` in CLI commands, the system will prefer the runtime-selected WAN interface. To override defaults explicitly, set the environment variables `AZAZEL_WAN_IF` and/or `AZAZEL_LAN_IF`, or pass `--wan-if` / `--lan-if` on the CLI.


## Automatic Network Configuration

### During Installation

The `install_azazel.sh` script automatically configures network interfaces based on your `azazel.yaml` settings. This is the **recommended approach** for most deployments.

#### Configuration via azazel.yaml

Edit `/etc/azazel/azazel.yaml` to specify your network requirements:

```yaml
network:
  # Primary monitoring interface (use AZAZEL_WAN_IF to override at runtime)
  interface: "${AZAZEL_WAN_IF:-eth0}"
  
  # Home network definition for IDS rules
  home_net: "192.168.1.0/24"
  
  # Gateway mode configuration (optional)
  gateway_mode:
    enabled: false
  ap_interface: "${AZAZEL_LAN_IF:-wlan0}"
  client_interface: "${AZAZEL_WAN_IF:-wlan1}"
    internal_network: "172.16.0.0/24"
    ap_ssid: "Azazel-GW"
    ap_passphrase: "SecurePassphrase123"
    
  # Static IP configuration (optional)
  static_ip:
    enabled: false
    address: "192.168.1.100/24"
    gateway: "192.168.1.1"
    dns: ["8.8.8.8", "1.1.1.1"]
```

#### Apply Network Configuration

After editing the configuration:

```bash
# Restart Azazel services to apply network changes
sudo systemctl restart azctl-unified.service

# Verify interface configuration
ip addr show
ip route show
```

## Gateway Mode Setup

When Azazel-Edge needs to act as a Wi-Fi access point with internet sharing:

### Automatic Gateway Setup

1. **Configure Interfaces**: Set `gateway_mode.enabled: true` in `azazel.yaml`
2. **Specify Interfaces**: 
   - `ap_interface`: Interface for hosting the access point (e.g., `wlan0`)
   - `client_interface`: Interface connected to internet (e.g., `wlan1` or `eth0`)
3. **Restart Services**: `sudo systemctl restart azctl-unified.service`

### Verification

```bash
# Check access point status
sudo systemctl status hostapd

# Verify DHCP server
sudo systemctl status dnsmasq

# Test internet connectivity (uses the runtime-selected WAN interface)
ping -I ${AZAZEL_WAN_IF:-wlan1} 8.8.8.8

# Check NAT rules
sudo nft list ruleset | grep -A5 -B5 masquerade
```

### Client Connection Test

From a client device:
1. Connect to the configured SSID (e.g., "Azazel-GW")
2. Verify DHCP IP assignment (should receive IP in configured range)
3. Test internet connectivity
4. Verify access to Azazel web interface

## Monitor Mode Setup

For deployments that monitor existing network traffic without routing:

### Configuration

```yaml
network:
  interface: "eth0"
  mode: "monitor"
  home_net: "192.168.1.0/24"
  
  # Promiscuous mode for packet capture
  promiscuous: true
  
  # Suricata monitoring configuration
  suricata:
    interface: "eth0"
    capture_mode: "af-packet"
```

### Suricata Integration

Configure Suricata for the monitoring interface:

```bash
# Generate Suricata configuration
sudo /opt/azazel/scripts/suricata_generate.py \
  /etc/azazel/azazel.yaml \
  /etc/azazel/suricata/suricata.yaml.tmpl \
  --output /etc/suricata/suricata.yaml

# Restart Suricata
sudo systemctl restart suricata

# Verify monitoring
sudo tail -f /var/log/suricata/eve.json
```

## Manual Network Configuration

For advanced deployments requiring custom network setup:

### Manual Wi-Fi Access Point Setup

If automatic configuration doesn't meet your needs, you can configure components manually:

#### 1. hostapd Configuration

```bash
# Create hostapd configuration (AP interface uses AZAZEL_LAN_IF)
sudo tee /etc/hostapd/hostapd.conf <<EOF
interface=${AZAZEL_LAN_IF:-wlan0}
driver=nl80211
ssid=Azazel-GW
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=SecurePassphrase123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
country_code=US
EOF

# Set hostapd configuration path
echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' | sudo tee -a /etc/default/hostapd

# Enable and start hostapd
sudo systemctl unmask hostapd
sudo systemctl enable --now hostapd
```

#### 2. DHCP Server Configuration

```bash
# Configure dnsmasq for DHCP (AP interface uses AZAZEL_LAN_IF)
sudo tee /etc/dnsmasq.d/01-azazel.conf <<EOF
interface=${AZAZEL_LAN_IF:-wlan0}
dhcp-range=172.16.0.100,172.16.0.200,255.255.255.0,24h
dhcp-option=3,172.16.0.1    # Gateway
dhcp-option=6,8.8.8.8       # DNS
EOF

# Restart dnsmasq
sudo systemctl restart dnsmasq
```

#### 3. Static IP Configuration

```bash
# Configure static IP for AP interface (AP interface uses AZAZEL_LAN_IF)
sudo tee -a /etc/dhcpcd.conf <<EOF

# Azazel-Edge AP configuration
interface ${AZAZEL_LAN_IF:-wlan0}
static ip_address=172.16.0.1/24
nohook wpa_supplicant
EOF

# Restart network service
sudo systemctl restart dhcpcd
```

#### 4. NAT and IP Forwarding

```bash
# Enable IP forwarding
echo 'net.ipv4.ip_forward=1' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Configure NAT with nftables
sudo tee /etc/nftables.d/nat.nft <<EOF
table ip nat {
    chain prerouting {
        type nat hook prerouting priority -100;
    }
    
  chain postrouting {
    type nat hook postrouting priority 100;
    oifname "${AZAZEL_WAN_IF:-wlan1}" masquerade
  }
}
EOF

# Apply nftables rules
sudo nft -f /etc/nftables.d/nat.nft
sudo systemctl enable nftables
```

### External Client Connection Setup

For connecting to external Wi-Fi networks:

#### wpa_supplicant Configuration

```bash
# Configure external Wi-Fi connection
sudo tee /etc/wpa_supplicant/wpa_supplicant-wlan1.conf <<EOF
country=US
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="ExternalNetworkSSID"
    psk="ExternalNetworkPassword"
    key_mgmt=WPA-PSK
}
EOF

# Set permissions
sudo chmod 600 /etc/wpa_supplicant/wpa_supplicant-wlan1.conf

# Enable wpa_supplicant service
sudo systemctl enable wpa_supplicant@wlan1.service
sudo systemctl start wpa_supplicant@wlan1.service
```

## Network Troubleshooting

### Interface Issues

```bash
# List all network interfaces
ip link show

# Check interface status
ip addr show <interface>

# Bring interface up/down
sudo ip link set <interface> up
sudo ip link set <interface> down

# Check wireless capabilities
sudo iwlist scan | head -20
```

### DHCP Issues

```bash
# Check DHCP server status
sudo systemctl status dnsmasq

# View DHCP leases
sudo cat /var/lib/dhcp/dhcpcd.leases

# Test DHCP from client
sudo dhclient -v <interface>
```

### Access Point Issues

```bash
# Check hostapd status
sudo systemctl status hostapd

# View hostapd logs
sudo journalctl -u hostapd -f

# Test AP beacon
sudo iwlist <interface> scan | grep -A5 -B5 "Azazel"
```

### Connectivity Issues

```bash
# Test internet connectivity
ping -c 4 8.8.8.8

# Check routing table
ip route show

# Test NAT functionality
sudo tcpdump -i wlan1 -n icmp

# Check firewall rules
sudo nft list ruleset
```

### Performance Issues

```bash
# Check interface statistics
cat /proc/net/dev

# Monitor wireless statistics
watch -n1 cat /proc/net/wireless

# Test bandwidth
iperf3 -c <server> -t 30
```

## Advanced Networking

### VLAN Configuration

For deployments requiring VLAN segmentation:

```bash
# Create VLAN interface
sudo ip link add link eth0 name eth0.100 type vlan id 100
sudo ip link set dev eth0.100 up
sudo ip addr add 192.168.100.1/24 dev eth0.100

# Configure Suricata for VLAN
# Update /etc/azazel/azazel.yaml with VLAN interface
```

### Bridge Configuration

For transparent monitoring setups:

```bash
# Create bridge
sudo brctl addbr br0
sudo brctl addif br0 eth0
sudo brctl addif br0 eth1

# Enable bridge
sudo ip link set dev br0 up

# Configure Suricata for bridge mode
# Update suricata.yaml with bridge configuration
```

### Traffic Shaping

Configure QoS and traffic control:

```bash
# Apply traffic control rules
sudo /opt/azazel/tc_reset.sh
sudo /opt/azazel/nft_apply.sh

# Monitor traffic shaping
sudo tc -s qdisc show
sudo tc -s class show dev <interface>
```

## Network Security

### Firewall Configuration

```bash
# View current nftables rules
sudo nft list ruleset

# Apply Azazel firewall rules
sudo nft -f /etc/azazel/nftables/lockdown.nft

# Check rule statistics
sudo nft list ruleset -a
```

### Intrusion Detection

```bash
# Check Suricata alerts
sudo tail -f /var/log/suricata/fast.log

# Monitor network traffic
sudo tcpdump -i <interface> -n -c 100

# Check OpenCanary honeypot logs
docker logs -f azazel_opencanary
```

## Legacy Network Configurations

For reference, the following archived documents contain additional manual configuration procedures:

- **wlan_setup.md** (archived): Detailed manual Wi-Fi AP setup procedures
- **RaspAP_config.md** (archived): RaspAP integration guide

These are kept in `docs/archive/` for reference but are **not recommended** for new deployments. Use the automatic configuration methods described above instead.

## Integration with Existing Infrastructure

### Corporate Networks

For deployment in existing corporate networks:

1. **Static IP Assignment**: Configure static IP to avoid DHCP conflicts
2. **VLAN Integration**: Use appropriate VLAN tags for network segmentation
3. **DNS Configuration**: Use internal DNS servers
4. **Proxy Settings**: Configure for corporate proxy if required
5. **Certificate Authority**: Install corporate CA certificates if needed

### Cloud Integration

For cloud-connected deployments:

1. **VPN Configuration**: Set up site-to-site VPN for remote management
2. **Log Forwarding**: Configure Vector to send logs to cloud SIEM
3. **Remote Monitoring**: Enable secure remote access to web interface
4. **Backup Connectivity**: Configure failover network connections

## See Also

- [`INSTALLATION.md`](INSTALLATION.md) - Complete installation guide
- [`OPERATIONS.md`](OPERATIONS.md) - Operational procedures
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) - Network troubleshooting
- [`docs/archive/wlan_setup.md`](archive/wlan_setup.md) - Legacy manual setup procedures

---

*For the latest networking guidance, refer to the [Azazel-Edge repository](https://github.com/01rabbit/Azazel-Edge) and consult your network administrator for enterprise deployments.*
