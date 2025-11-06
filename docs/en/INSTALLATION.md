# Azazel-Pi Installation Guide

This comprehensive guide covers the installation and initial setup of Azazel-Pi on Raspberry Pi systems, including the main system components, E-Paper display integration, and troubleshooting procedures.

## Overview

Azazel-Pi provides a **single-script installation** that automatically provisions all required components:
- **Core services**: Suricata IDS/IPS, OpenCanary honeypot, Vector log collection
- **Control plane**: azctl daemon and state machine
- **Collaboration platform**: Mattermost with PostgreSQL database
- **Web interface**: Nginx reverse proxy
- **Optional hardware**: E-Paper status display

## Prerequisites

### Hardware Requirements
- **Raspberry Pi 5 Model B** (recommended) or compatible ARM64 device
- **8GB+ microSD card** with Raspberry Pi OS (64-bit Lite)
- **Ethernet connection** for initial setup
- **Optional**: Waveshare 2.13" E-Paper display for status visualization

### Software Requirements
- **Raspberry Pi OS (64-bit Lite)** or Debian-based distribution
- **Internet connection** for dependency installation
- **Administrator privileges** (sudo access)

### Network Configuration
- Device should have a **static IP** or reliable DHCP reservation
- **Ports 80/443** available for web interface
- **Port 8065** available for Mattermost (internal)

## Installation

### 1. System Preparation

Update your Raspberry Pi to the latest packages:

```bash
sudo apt update && sudo apt upgrade -y
sudo reboot
```

### 2. Download Azazel-Pi

#### Option A: Clone from GitHub (Development)
```bash
git clone https://github.com/01rabbit/Azazel-Pi.git
cd Azazel-Pi
```

#### Option B: Download Release Bundle (Production)
```bash
# Use specific version tag (recommended for production)
TAG=v1.0.0
curl -fsSL https://github.com/01rabbit/Azazel-Pi/releases/download/${TAG}/azazel-installer-${TAG}.tar.gz \
  | tar xz -C /tmp
cd /tmp/azazel-installer
```

### 3. Run Installation Script

Execute the automated installer as root:

```bash
# Basic installation
sudo scripts/install_azazel.sh

# Install and automatically start services
sudo scripts/install_azazel.sh --start

# Dry run to see what would be installed (no changes made)
sudo scripts/install_azazel.sh --dry-run
```

#### What the Installer Does

The `install_azazel.sh` script performs the following actions:

1. **System Dependencies**: Installs required packages via apt
   - Core tools: `curl`, `git`, `jq`, `python3`, `rsync`
   - Security components: `suricata`, `nftables`, `netfilter-persistent`
   - Infrastructure: `docker.io`, `nginx`, `python3-venv`

2. **Specialized Services**:
   - **Vector**: Log collection agent (official repo or tarball fallback)
   - **OpenCanary**: Honeypot in dedicated Python virtual environment
   - **Mattermost**: Collaboration platform with PostgreSQL database

3. **Azazel Components**:
   - Core Python modules to `/opt/azazel/`
   - Configuration templates to `/etc/azazel/`
   - systemd service units and targets
   - Utility scripts and rollback capability

4. **Runtime Environment**:
   - Creates `/var/log/azazel/` for operational logs
   - Configures PostgreSQL container for Mattermost
   - Sets up Nginx reverse proxy
   - Enables but does not start the `azctl-unified.service`

### 4. Configuration

Before starting services, review and customize the main configuration:

```bash
sudo nano /etc/azazel/azazel.yaml
```

Key settings to adjust:

- **Interface names**: Match your network setup (`eth0`, `wlan0`, etc.)
- **QoS profiles**: Bandwidth limits for each defensive mode
- **Defensive thresholds**: Score limits for Shield/Lockdown transitions
- **Lockdown allowlists**: Critical services that remain accessible

Example configuration structure:
```yaml
network:
  interface: "eth0"
  home_net: "192.168.1.0/24"

modes:
  portal:
    delay_ms: 100
    enabled: true
  shield:
    delay_ms: 200
    shape_kbps: 128
    enabled: true
  lockdown:
    delay_ms: 300
    shape_kbps: 64
    block_enabled: true

scoring:
  shield_threshold: 50
  lockdown_threshold: 100
  window_size: 10
```

### 5. Start Services

Enable and start the Azazel system:

```bash
# Start all Azazel services
sudo systemctl start azctl-unified.service

# Verify service status
sudo systemctl status azctl-unified.service

# Check individual services
sudo systemctl status mattermost nginx docker
```

### 6. Verification

#### Service Health Check
```bash
# Run built-in health check
sudo /opt/azazel/sanity_check.sh

# Check system logs
sudo journalctl -u azctl-unified.service -f
```

#### Web Interface Access
- **Mattermost**: `http://your-pi-ip` (via Nginx proxy)
- **Direct Mattermost**: `http://your-pi-ip:8065` (if Nginx unavailable)

#### Command Line Interface
```bash
# Basic status (requires active configuration)
python3 -m azctl.cli status --config /etc/azazel/azazel.yaml

# Rich terminal interface
python3 -m azctl.cli status --tui --config /etc/azazel/azazel.yaml

# JSON output for automation
python3 -m azctl.cli status --json --config /etc/azazel/azazel.yaml
```

#### Interactive TUI Menu
```bash
# Comprehensive modular menu system
python3 -m azctl.cli menu

# Custom interface specification
python3 -m azctl.cli menu --lan-if wlan0 --wan-if wlan1
```

**TUI Menu Features:**
- **Modular Design**: 8 function-specific modules for enhanced maintainability
- **Real-time Monitoring**: Live system status, services, and log updates
- **Safe Operations**: Confirmation dialogs for dangerous operations
- **Comprehensive Management**: Control entire system from single interface
- **Extensible Structure**: Easy addition of new functionality

## E-Paper Display Setup (Optional)

If you have a Waveshare E-Paper display, follow these additional steps:

### 1. Hardware Connection

Connect the E-Paper HAT to your Raspberry Pi following the standard SPI pinout. See [`EPD_SETUP.md`](EPD_SETUP.md) for detailed wiring information.

### 2. Enable SPI Interface

```bash
# Using raspi-config
sudo raspi-config
# Navigate to: Interface Options → SPI → Enable

# Or enable manually
echo "dtparam=spi=on" | sudo tee -a /boot/config.txt
sudo reboot
```

### 3. Install E-Paper Dependencies

```bash
# Install E-Paper library and dependencies
sudo scripts/install_epd.sh

# Test the display
sudo python3 -m azazel_pi.core.display.epd_daemon --mode test
```

### 4. Enable E-Paper Service

```bash
# Enable automatic E-Paper updates
sudo systemctl enable --now azazel-epd.service

# Check service status
sudo systemctl status azazel-epd.service

# View update logs
sudo journalctl -u azazel-epd.service -f
```

### 5. Configuration

Edit the E-Paper service configuration:

```bash
sudo nano /etc/default/azazel-epd
```

Key settings:
```bash
# Update interval in seconds
UPDATE_INTERVAL=10

# Path to events log
EVENTS_LOG=/var/log/azazel/events.json

# Enable debug output
DEBUG=0
```

## Network Configuration

For deployments requiring AP (Access Point) functionality:

### Automatic Network Setup

The installer can configure network interfaces automatically. Edit `/etc/azazel/azazel.yaml` to specify:

```yaml
network:
  # Primary interface for monitoring
  interface: "wlan1"
  
  # Internal network when acting as gateway
  internal_network: "172.16.0.0/24"
  
  # AP interface configuration (if needed)
  ap_interface: "wlan0"
  ap_ssid: "Azazel-GW"
  ap_passphrase: "SecurePassphrase123"
```

### Manual Network Configuration

For advanced setups, see the archived network configuration guides:
- Manual Wi-Fi AP setup: `docs/archive/wlan_setup.md`
- RaspAP integration: `docs/archive/RaspAP_config.md`

## Troubleshooting

### Installation Issues

#### Package Installation Failures
```bash
# Clear apt cache and retry
sudo apt clean
sudo apt update
sudo apt install -f

# Check disk space
df -h /
```

#### Service Start Failures
```bash
# Check service status
sudo systemctl status <service-name>

# View detailed logs
sudo journalctl -u <service-name> --no-pager

# Reset failed services
sudo systemctl reset-failed
```

### Runtime Issues

#### Database Connection Problems
```bash
# Check PostgreSQL container
sudo docker ps | grep postgres

# Restart database container
cd /opt/azazel/config
sudo docker-compose --project-name azazel-db restart

# Verify Mattermost database configuration
sudo cat /opt/mattermost/config/config.json | jq '.SqlSettings'
```

#### Network Interface Issues
```bash
# List available interfaces
ip link show

# Check interface status
ip addr show <interface-name>

# Update configuration with correct interface names
sudo nano /etc/azazel/azazel.yaml
sudo systemctl restart azctl-unified.service
```

#### E-Paper Display Problems
```bash
# Check SPI interface
ls -l /dev/spidev0.0

# Test display manually
sudo python3 -m azazel_pi.core.display.epd_daemon --mode test

# Check for driver conflicts
sudo journalctl -u azazel-epd.service | grep -i error
```

### Performance Issues

#### High CPU Usage
```bash
# Identify resource-intensive processes
htop

# Reduce E-Paper update frequency
sudo nano /etc/default/azazel-epd
# Set UPDATE_INTERVAL=30

# Check for log rotation issues
sudo du -sh /var/log/*
```

#### Memory Issues
```bash
# Check memory usage
free -h

# Restart services to free memory
sudo systemctl restart azctl-unified.service

# Consider increasing swap space
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile  # Set CONF_SWAPSIZE=1024
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

### Recovery Procedures

#### Complete System Reset
```bash
# Stop all Azazel services
sudo systemctl stop azctl-unified.service

# Remove installation (keeps logs)
sudo /opt/azazel/rollback.sh

# Clean reinstall
sudo scripts/install_azazel.sh --start
```

#### Configuration Reset
```bash
# Backup current config
sudo cp -r /etc/azazel /etc/azazel.backup

# Restore default configuration
sudo rsync -a configs/ /etc/azazel/

# Customize and restart
sudo nano /etc/azazel/azazel.yaml
sudo systemctl restart azctl-unified.service
```

#### Database Reset
```bash
# Stop services using database
sudo systemctl stop mattermost

# Remove database container and data
cd /opt/azazel/config
sudo docker-compose --project-name azazel-db down -v
sudo rm -rf /opt/azazel/data/postgres

# Recreate database
sudo docker-compose --project-name azazel-db up -d
sudo systemctl start mattermost
```

## Advanced Configuration

### Custom Suricata Rules

Generate environment-specific IDS configuration:

```bash
# Generate Suricata config from template
sudo /opt/azazel/scripts/suricata_generate.py \
  /etc/azazel/azazel.yaml \
  /etc/azazel/suricata/suricata.yaml.tmpl \
  --output /etc/suricata/suricata.yaml

# Restart Suricata to apply changes
sudo systemctl restart suricata
```

### Custom QoS Profiles

Edit traffic control settings:

```bash
sudo nano /etc/azazel/tc/classes.htb
sudo systemctl restart azctl-unified.service
```

### Integration with External SIEM

Configure Vector log forwarding:

```bash
sudo nano /etc/azazel/vector/vector.toml
sudo systemctl restart vector
```

## Maintenance

### Regular Updates

```bash
# Update system packages
sudo apt update && sudo apt upgrade

# Update Suricata rules
sudo suricata-update

# Restart services after updates
sudo systemctl restart azctl-unified.service
```

### Log Management

```bash
# Check log sizes
sudo du -sh /var/log/azazel/*

# Rotate logs manually
sudo logrotate -f /etc/logrotate.d/azazel

# Clean old Docker images
sudo docker system prune -f
```

### Backup and Restore

```bash
# Backup configuration
sudo tar -czf azazel-backup-$(date +%Y%m%d).tar.gz \
  /etc/azazel /opt/azazel/config

# Restore configuration
sudo tar -xzf azazel-backup-YYYYMMDD.tar.gz -C /
sudo systemctl restart azctl-unified.service
```

## Next Steps

After successful installation:

1. **Review Configuration**: Ensure all settings match your environment
2. **Test Defensive Modes**: Manually trigger mode transitions to verify behavior
3. **Configure Notifications**: Set up Mattermost webhooks and integrations
4. **Monitor Performance**: Use built-in tools to track system health
5. **Plan Maintenance**: Establish update and backup schedules

## See Also

- [`OPERATIONS.md`](OPERATIONS.md) - Day-to-day operational procedures
- [`ARCHITECTURE.md`](ARCHITECTURE.md) - System architecture and design
- [`EPD_SETUP.md`](EPD_SETUP.md) - E-Paper display configuration details
- [`API_REFERENCE.md`](API_REFERENCE.md) - Python modules and HTTP endpoints
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) - Comprehensive troubleshooting guide

---

*For the latest installation instructions and updates, always refer to the official [Azazel-Pi repository](https://github.com/01rabbit/Azazel-Pi).*