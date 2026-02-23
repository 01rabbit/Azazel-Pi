# Azazel-Edge Troubleshooting Guide

This comprehensive troubleshooting guide covers common issues encountered during installation, configuration, and operation of Azazel-Edge systems.

## TUI Menu System Issues

### Menu Launch Failures

#### Problem: TUI menu fails to start

**Symptoms:**
```bash
$ python3 -m azctl.cli menu
ModuleNotFoundError: No module named 'textual'
```

**Solutions:**

```bash
# Install textual dependency
pip3 install textual

# Verify Python path
python3 -c "import sys; print('\n'.join(sys.path))"

# Run from correct directory
cd /opt/azazel
python3 -m azctl.cli menu
```

#### Problem: Unified TUI module import errors

**Symptoms:**
```
ImportError: cannot import name 'run_menu' from azctl.tui_zero
```

**Solutions:**

```bash
# Verify new TUI files exist
ls -la azctl/tui_zero.py azctl/tui_zero_textual.py

# Validate syntax
python3 -m py_compile azctl/tui_zero.py azctl/tui_zero_textual.py azctl/cli.py
```

### Menu Display Issues

#### Problem: Rich UI displays incorrectly

**Symptoms:**
- Colors not displaying
- Tables malformed
- Text corruption

**Solutions:**

```bash
# Check terminal environment variables
echo $TERM
echo $COLORTERM

# Test Rich console functionality
python3 -c "from rich.console import Console; c = Console(); c.print('[red]Test[/red]')"

# Use appropriate terminal
export TERM=xterm-256color
python3 -m azctl.cli menu
```

#### Problem: Keyboard input not responding

**Symptoms:**
- Number keys don't select menu items
- Ctrl+C doesn't exit
- Screen doesn't refresh

**Solutions:**

```bash
# Check terminal input mode
stty -a

# Verify standard input
python3 -c "import sys; print(sys.stdin.isatty())"

# For SSH connections
ssh -t user@host python3 -m azctl.cli menu
```

### WiFi Management Issues

#### Problem: WiFi scanning fails

**Symptoms:**
```
Error: No networks found or scan failed
```

**Solutions:**

```bash
# Check wireless interface
sudo iw dev

# Test scan permissions
sudo iw ${AZAZEL_WAN_IF:-wlan1} scan | head -20

# Resolve NetworkManager conflicts
sudo systemctl stop NetworkManager
sudo systemctl disable NetworkManager
```

#### Problem: WiFi connection fails

**Symptoms:**
- Connection fails after password entry
- wpa_supplicant errors

**Solutions:**

```bash
# Check wpa_supplicant status
# Note: replace 'wlan1' with the runtime WAN interface. You can override the detected
# interface by exporting AZAZEL_WAN_IF (or AZAZEL_LAN_IF for LAN-related commands).
# Example uses the environment override with a fallback to the historical default:
sudo wpa_cli -i ${AZAZEL_WAN_IF:-wlan1} status

# Verify configuration file permissions
ls -l /etc/wpa_supplicant/wpa_supplicant.conf

# Test manual connection (use AZAZEL_WAN_IF to override the interface name):
sudo wpa_cli -i ${AZAZEL_WAN_IF:-wlan1} add_network
sudo wpa_cli -i ${AZAZEL_WAN_IF:-wlan1} set_network 0 ssid '"YourSSID"'
sudo wpa_cli -i ${AZAZEL_WAN_IF:-wlan1} set_network 0 psk '"YourPassword"'
sudo wpa_cli -i ${AZAZEL_WAN_IF:-wlan1} enable_network 0
```

### Service Management Issues

#### Problem: Service control fails

**Symptoms:**
- Cannot start/stop services
- Permission errors

**Solutions:**

```bash
# Check sudoers configuration
sudo visudo
# Add if needed:
# %azazel ALL=(ALL) NOPASSWD: /bin/systemctl

# Test service status manually
sudo systemctl status azctl-unified.service

# Test systemctl permissions
sudo -u azazel sudo systemctl status azctl-unified.service
```

### Emergency Operations Issues

#### Problem: Emergency lockdown not working

**Symptoms:**
- Network not blocked
- nftables rules not applied

**Solutions:**

```bash
# Check nftables status
sudo nft list ruleset

# Test manual lockdown rules
sudo nft flush ruleset
sudo nft add table inet emergency
sudo nft add chain inet emergency input '{ type filter hook input priority 0; policy drop; }'

# Check network interface status
ip link show
```

#### Problem: System report generation fails

**Symptoms:**
- Report file not created
- Permission errors

**Solutions:**

```bash
# Check /tmp write permissions
ls -ld /tmp
touch /tmp/test && rm /tmp/test

# Test manual report generation
sudo python3 -c "
import subprocess
result = subprocess.run(['uname', '-a'], capture_output=True, text=True)
print(result.stdout)
"
```

### Performance Issues

#### Problem: Menu response is slow

**Symptoms:**
- Menu display takes long time
- Key input lag

**Solutions:**

```bash
# Check system resources
htop
free -h
df -h

# Monitor I/O wait
iostat -x 1 5

# Adjust process priority
sudo nice -n -10 python3 -m azctl.cli menu
```

### Debug and Logging

#### TUI Menu Debug Mode

```bash
# Enable debug logging
export AZAZEL_DEBUG=1
python3 -m azctl.cli menu

# Verbose logging
python3 -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from azctl.tui_zero import run_menu
run_menu(lan_if='wlan0', wan_if='wlan1', start_menu=True)
"
```

#### Log File Inspection

```bash
# TUI menu related logs
sudo journalctl -u azctl-unified.service --since "1 hour ago" | grep -i menu

# Python error logs
sudo tail -f /var/log/syslog | grep python3

# Manual log output
python3 -m azctl.cli menu 2>&1 | tee menu_debug.log
```

## Quick Diagnosis

### System Health Check

Start with the built-in health check script:

```bash
# Run comprehensive system check
sudo /opt/azazel/sanity_check.sh

# Check service status
sudo systemctl status azctl-unified.service

# View recent logs
sudo journalctl -u azctl-unified.service --since "10 minutes ago"
```

### Service Status Overview

```bash
# Check all Azazel-related services
sudo systemctl status azctl-unified.service mattermost nginx docker

# Check security services
sudo systemctl status suricata vector
docker ps --filter name=azazel_opencanary

# Check E-Paper service (if installed)
sudo systemctl status azazel-epd.service
```

## Installation Issues

### Package Installation Failures

#### Problem: APT package installation fails

**Symptoms:**
- `apt install` commands return errors
- Dependencies cannot be resolved
- Package conflicts reported

**Solutions:**

```bash
# Clear package cache and update
sudo apt clean
sudo apt autoremove
sudo apt update
sudo apt upgrade

# Fix broken packages
sudo apt install -f
sudo dpkg --configure -a

# Check disk space
df -h /
sudo apt autoclean

# Retry installation with verbose output
sudo apt install -v <package-name>
```

#### Problem: Docker installation fails

**Symptoms:**
- Docker daemon won't start
- Permission denied errors
- Container runtime not found

**Solutions:**

```bash
# Remove old Docker installations
sudo apt remove docker docker-engine docker.io containerd runc

# Install Docker via official repository
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Start Docker service
sudo systemctl enable --now docker

# Test Docker installation
docker run hello-world
```

### Installation Script Failures

#### Problem: install_azazel.sh fails midway

**Symptoms:**
- Script exits with error code
- Partial installation completed
- Services not properly configured

**Solutions:**

```bash
# Check installation log
sudo journalctl -xe

# Clean partial installation
sudo /opt/azazel/rollback.sh 2>/dev/null || true
sudo rm -rf /opt/azazel /etc/azazel

# Retry with verbose output
sudo bash -x scripts/install_azazel.sh

# Dry run to check what would be installed
sudo scripts/install_azazel.sh --dry-run
```

#### Problem: Mattermost download fails

**Symptoms:**
- Network timeouts during download
- Architecture mismatch errors
- Corrupt tarball errors

**Solutions:**

```bash
# Check network connectivity
ping -c 4 8.8.8.8
curl -I https://releases.mattermost.com

# Manual download and installation
ARCH=$(dpkg --print-architecture)
VERSION="9.7.1"
wget https://releases.mattermost.com/${VERSION}/mattermost-team-${VERSION}-linux-${ARCH}.tar.gz

# Verify tarball integrity
tar -tzf mattermost-team-${VERSION}-linux-${ARCH}.tar.gz | head

# Set custom tarball path
export MATTERMOST_TARBALL="/path/to/mattermost-tarball.tar.gz"
sudo scripts/install_azazel.sh
```

## Configuration Issues

### Network Configuration Problems

#### Problem: Interface not found

**Symptoms:**
- "Interface eth0 not found" errors
- Network services fail to start
- No network connectivity

**Solutions:**

```bash
# List available interfaces
ip link show

# Check interface status
ip addr show

# Update configuration with correct interface names
sudo nano /etc/azazel/azazel.yaml
# Update the 'interface' field with actual interface name

# Restart services
sudo systemctl restart azctl-unified.service
```

#### Problem: Wi-Fi AP not working

**Symptoms:**
- hostapd fails to start
- SSID not visible to clients
- Clients cannot connect

**Solutions:**

```bash
# Check hostapd status and logs
sudo systemctl status hostapd
sudo journalctl -u hostapd --no-pager

# Verify Wi-Fi interface supports AP mode
sudo iw list | grep -A 10 "Supported interface modes"

# Check for conflicting services
sudo systemctl status NetworkManager
sudo systemctl status wpa_supplicant

# Disable conflicting services if needed
sudo systemctl disable --now NetworkManager
sudo systemctl mask wpa_supplicant

# Restart hostapd
sudo systemctl restart hostapd
```

#### Problem: DHCP not assigning addresses

**Symptoms:**
- Clients connect but don't get IP addresses
- dnsmasq service fails
- DHCP range conflicts

**Solutions:**

```bash
# Check dnsmasq status
sudo systemctl status dnsmasq
sudo journalctl -u dnsmasq --no-pager

# Verify DHCP configuration
sudo cat /etc/dnsmasq.d/01-azazel.conf

# Check for port conflicts
sudo netstat -tuln | grep :53
sudo netstat -tuln | grep :67

# Stop conflicting services
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved

# Restart dnsmasq
sudo systemctl restart dnsmasq
```

### Database Configuration Issues

#### Problem: PostgreSQL container won't start

**Symptoms:**
- Docker container exits immediately
- Database connection errors in Mattermost
- Port already in use errors

**Solutions:**

```bash
# Check Docker status
sudo systemctl status docker
docker ps -a

# Check container logs
docker logs azazel-db-postgres-1

# Check port conflicts
sudo netstat -tuln | grep :5432

# Remove and recreate container
cd /opt/azazel/config
sudo docker-compose --project-name azazel-db down -v
sudo docker-compose --project-name azazel-db up -d

# Check database directory permissions
sudo ls -la /opt/azazel/data/postgres
sudo chown -R 999:999 /opt/azazel/data/postgres
```

#### Problem: Mattermost cannot connect to database

**Symptoms:**
- Mattermost service fails to start
- Database connection timeout errors
- Authentication failures

**Solutions:**

```bash
# Check Mattermost configuration
sudo cat /opt/mattermost/config/config.json | jq '.SqlSettings'

# Test database connection manually
docker exec -it azazel-db-postgres-1 psql -U mmuser -d mattermost

# Update database credentials
sudo nano /opt/azazel/config/.env
# Update MATTERMOST_DB_* variables

# Recreate container with new credentials
cd /opt/azazel/config
sudo docker-compose --project-name azazel-db down
sudo docker-compose --project-name azazel-db up -d

# Restart Mattermost
sudo systemctl restart mattermost
```

## Runtime Issues

### Service Management Problems

#### Problem: Services fail to start

**Symptoms:**
- systemctl start commands fail
- Services immediately exit
- Dependency failures

**Solutions:**

```bash
# Check service dependencies
sudo systemctl list-dependencies azctl-unified.service

# Start services individually
sudo systemctl start suricata
sudo systemctl start vector
docker start azazel_opencanary
sudo systemctl start azctl-unified.service

# Check for configuration errors
sudo systemctl status --full <service-name>
sudo journalctl -u <service-name> --no-pager

# Reset failed services
sudo systemctl reset-failed
sudo systemctl daemon-reload
```

#### Problem: High CPU usage

**Symptoms:**
- System becomes unresponsive
- High load averages
- Services timing out

**Solutions:**

```bash
# Identify CPU-intensive processes
htop
sudo iotop

# Check for log rotation issues
sudo du -sh /var/log/*
sudo logrotate -f /etc/logrotate.conf

# Reduce E-Paper update frequency
sudo nano /etc/default/azazel-epd
# Set UPDATE_INTERVAL=30

# Restart resource-intensive services
sudo systemctl restart vector
sudo systemctl restart suricata
```

#### Problem: Vector service fails to start

**Symptoms:**
- Vector service status shows "failed" or "inactive"
- Error logs show VRL syntax errors or configuration issues
- Log processing pipeline broken

**Solutions:**

```bash
# Check Vector configuration syntax
vector validate --no-environment /etc/azazel/vector/vector.toml

# View detailed error logs
sudo journalctl -u vector --since "10 minutes ago" --no-pager

# Common fixes for VRL syntax errors:
# 1. Update map() function syntax for Vector 0.39.0+
# 2. Fix closure parameter type mismatches
# 3. Ensure configuration paths are correct

# Test configuration manually
sudo /usr/local/bin/vector --config /etc/azazel/vector/vector.toml --dry-run

# Restart service after fixes
sudo systemctl restart vector
```

#### Problem: Memory exhaustion

**Symptoms:**
- Out of memory errors
- Services killed by OOM killer
- System becomes unresponsive

**Solutions:**

```bash
# Check memory usage
free -h
sudo dmesg | grep -i "killed process"

# Increase swap space
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Set CONF_SWAPSIZE=1024
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# Optimize service memory usage
sudo nano /etc/systemd/system/suricata.service
# Add: MemoryLimit=512M

# Restart services
sudo systemctl daemon-reload
sudo systemctl restart azctl-unified.service
```

### Network and Security Issues

#### Problem: Suricata not detecting traffic

**Symptoms:**
- Empty /var/log/suricata/eve.json
- No alerts being generated
- Traffic not being monitored

**Solutions:**

```bash
# Check Suricata status
sudo systemctl status suricata
sudo suricata --dump-config | grep interface

# Verify interface is receiving traffic
sudo tcpdump -i <interface> -c 10

# Check Suricata configuration
sudo suricata -T -c /etc/suricata/suricata.yaml

# Update rules
sudo suricata-update
sudo systemctl restart suricata

# Test with EICAR string
curl -s http://eicar.org/download/eicar.com.txt
```

#### Problem: OpenCanary honeypot not logging

**Symptoms:**
- No honeypot logs generated
- Services not responding to probes
- OpenCanary service fails

**Solutions:**

```bash
# Check OpenCanary status
docker ps --filter name=azazel_opencanary
docker logs --tail 100 azazel_opencanary

# Verify configuration
sudo cat /opt/azazel/config/opencanary.conf

# Test honeypot services
nmap -sS -O localhost

# Check for port conflicts
sudo netstat -tuln | grep -E ':(22|23|80|443|21)'

# Restart OpenCanary
docker restart azazel_opencanary
```

#### Problem: Firewall blocking legitimate traffic

**Symptoms:**
- Cannot access web interface
- Network services unreachable
- SSH connections dropped

**Solutions:**

```bash
# Check current firewall rules
sudo nft list ruleset

# Temporarily disable firewall
sudo systemctl stop nftables

# Check if issue persists
# Test connectivity

# Add exception rules
sudo nano /etc/azazel/nftables/lockdown.nft
# Add allow rules for required services

# Apply updated rules
sudo nft -f /etc/azazel/nftables/lockdown.nft

# Re-enable firewall
sudo systemctl start nftables
```

## Hardware-Specific Issues

### E-Paper Display Problems

#### Problem: E-Paper display not updating

**Symptoms:**
- Display shows old information
- azazel-epd service fails
- SPI communication errors

**Solutions:**

```bash
# Check SPI interface
ls -l /dev/spidev0.0
lsmod | grep spi

# Enable SPI if disabled
echo "dtparam=spi=on" | sudo tee -a /boot/config.txt
sudo reboot

# Check E-Paper service
sudo systemctl status azazel-epd.service
sudo journalctl -u azazel-epd.service --no-pager

# Test display manually
sudo python3 -m azazel_edge.core.display.epd_daemon --mode test

# Check wiring connections
# Verify pins match expected GPIO assignments
```

#### Problem: E-Paper shows artifacts or ghosting

**Symptoms:**
- Display shows overlapping images
- Partial updates leaving artifacts
- Text appears corrupted

**Solutions:**

```bash
# Force full refresh
sudo python3 -m azazel_edge.core.display.epd_daemon --mode shutdown
sudo python3 -m azazel_edge.core.display.epd_daemon --mode test

# Disable gentle updates
sudo nano /etc/default/azazel-epd
# Add: GENTLE_UPDATES=0

# Increase update interval
# Set UPDATE_INTERVAL=30

# Restart E-Paper service
sudo systemctl restart azazel-epd.service
```

### Raspberry Pi Specific Issues

#### Problem: SD card corruption

**Symptoms:**
- Read-only filesystem errors
- Services randomly failing
- Boot failures

**Solutions:**

```bash
# Check filesystem status
sudo fsck /dev/mmcblk0p2

# Check for bad blocks
sudo badblocks -v /dev/mmcblk0

# Enable read-only mode temporarily
sudo mount -o remount,ro /

# Backup critical data
sudo tar -czf /tmp/azazel-backup.tar.gz /etc/azazel /opt/azazel/config

# Consider replacing SD card with higher endurance model
```

#### Problem: Power supply insufficient

**Symptoms:**
- Random reboots
- USB devices disconnecting
- Under-voltage warnings

**Solutions:**

```bash
# Check power supply status
dmesg | grep -i voltage
vcgencmd get_throttled

# Use official Raspberry Pi power supply (5V 3A for Pi 5)
# Check USB power draw
lsusb -v | grep -i power

# Disable unnecessary services
sudo systemctl disable bluetooth
sudo systemctl disable wifi-powersave-off

# Reduce CPU frequency if needed
sudo nano /boot/config.txt
# Add: arm_freq=1000
```

## Performance Optimization

### System Performance

```bash
# Monitor system resources
htop
iostat 1
sudo iotop

# Optimize I/O scheduler
echo mq-deadline | sudo tee /sys/block/mmcblk0/queue/scheduler

# Reduce logging verbosity
sudo nano /etc/systemd/journald.conf
# Set: MaxLevelStore=warning

# Clean up disk space
sudo apt autoclean
sudo journalctl --vacuum-time=7d
sudo docker system prune -f
```

### Network Performance

```bash
# Monitor network interfaces
sudo iftop
nload

# Optimize network buffers
echo 'net.core.rmem_max = 16777216' | sudo tee -a /etc/sysctl.conf
echo 'net.core.wmem_max = 16777216' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Check for packet drops
cat /proc/net/dev
sudo netstat -i
```

## Recovery Procedures

### Emergency Access

#### Problem: SSH access lost

**Solutions:**

```bash
# Physical console access via HDMI/keyboard
# Check network configuration
ip addr show
ip route show

# Restart network services
sudo systemctl restart networking
sudo systemctl restart NetworkManager

# Reset firewall rules
sudo nft flush ruleset

# Re-enable SSH
sudo systemctl enable --now ssh
```

#### Problem: Web interface inaccessible

**Solutions:**

```bash
# Check nginx status
sudo systemctl status nginx

# Check Mattermost status
sudo systemctl status mattermost

# Temporarily bypass nginx
# Access Mattermost directly: http://ip:8065

# Reset nginx configuration
sudo cp /opt/azazel/config/nginx.conf /etc/nginx/nginx.conf
sudo nginx -t
sudo systemctl restart nginx
```

### Complete System Recovery

#### Factory Reset

```bash
# Stop all services
sudo systemctl stop azctl-unified.service

# Backup configuration
sudo tar -czf /tmp/config-backup.tar.gz /etc/azazel

# Remove installation
sudo /opt/azazel/rollback.sh

# Clean Docker resources
sudo docker system prune -af
sudo docker volume prune -f

# Reinstall from scratch
sudo scripts/install_azazel.sh --start

# Restore configuration
sudo tar -xzf /tmp/config-backup.tar.gz -C /
sudo systemctl restart azctl-unified.service
```

#### Selective Service Reset

```bash
# Reset specific service
sudo systemctl stop <service>
sudo systemctl reset-failed <service>

# Restore default configuration
sudo cp /opt/azazel/configs/<service>/* /etc/azazel/<service>/

# Restart service
sudo systemctl start <service>
```

## Log Analysis

### Important Log Locations

```bash
# System logs
sudo journalctl -u azctl-unified.service
sudo journalctl -u mattermost
sudo journalctl -u nginx

# Application logs  
tail -f /var/log/azazel/decisions.log
tail -f /var/log/suricata/eve.json
tail -f /opt/mattermost/logs/mattermost.log

# E-Paper logs
sudo journalctl -u azazel-epd.service
```

### Log Analysis Tools

```bash
# Search for errors
sudo journalctl --since "1 hour ago" | grep -i error

# Monitor real-time logs
sudo journalctl -f

# Export logs for analysis
sudo journalctl --since "24 hours ago" --output=json > /tmp/system-logs.json

# Analyze Suricata alerts
jq 'select(.event_type=="alert")' /var/log/suricata/eve.json | head -10
```

## Getting Help

### Information to Collect

Before seeking help, collect the following information:

```bash
# System information
uname -a
cat /etc/os-release
df -h
free -h

# Azazel version and configuration
git log --oneline -n 5  # if installed from git
sudo cat /etc/azazel/azazel.yaml

# Service status
sudo systemctl status azctl-unified.service --no-pager
sudo /opt/azazel/sanity_check.sh

# Recent logs
sudo journalctl --since "1 hour ago" > /tmp/recent-logs.txt
```

### Support Resources

- **GitHub Issues**: [Azazel-Edge Issues](https://github.com/01rabbit/Azazel-Edge/issues)
- **Documentation**: This troubleshooting guide and related docs
- **Community**: Mattermost channels (if available)
- **Professional Support**: Contact maintainers for enterprise deployments

## Preventive Maintenance

### Regular Maintenance Tasks

```bash
# Weekly tasks
sudo apt update && sudo apt upgrade
sudo suricata-update
sudo journalctl --vacuum-time=7d

# Monthly tasks
sudo docker system prune -f
sudo /opt/azazel/sanity_check.sh
sudo systemctl restart azctl-unified.service

# Backup configuration
sudo tar -czf /backup/azazel-$(date +%Y%m%d).tar.gz /etc/azazel /opt/azazel/config
```

### Monitoring and Alerting

```bash
# Set up monitoring scripts
sudo crontab -e
# Add: */5 * * * * /opt/azazel/sanity_check.sh >> /var/log/azazel/health.log

# Monitor disk space
sudo nano /etc/crontab
# Add: 0 6 * * * root df -h | grep -E '(9[0-9]%|100%)' && echo "Disk space warning" | wall

# Set up log rotation
sudo nano /etc/logrotate.d/azazel
```

---

*For additional troubleshooting help, consult the [INSTALLATION.md](INSTALLATION.md), [OPERATIONS.md](OPERATIONS.md), and [NETWORK_SETUP.md](NETWORK_SETUP.md) guides, or file an issue at the [Azazel-Edge repository](https://github.com/01rabbit/Azazel-Edge).*
