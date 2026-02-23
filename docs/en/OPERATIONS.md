# Operations guide

This document captures the procedures for staging, operating, and maintaining
Azazel in the field. The workflow assumes deployment on Raspberry Pi OS but can
be adapted to other Debian derivatives.

For initial installation, see [`INSTALLATION.md`](INSTALLATION.md) for comprehensive setup instructions.

## 1. Acquire a release

Pick a signed Git tag (for example `v1.0.0`) and download the installer bundle:

```bash
TAG=v1.0.0
curl -fsSL https://github.com/01rabbit/Azazel-Edge/releases/download/${TAG}/azazel-installer-${TAG}.tar.gz \
  | tar xz -C /tmp
```

The archive includes configuration templates, scripts, and systemd units.

## 2. Bootstrap the node

Run the installer on the target host. When working from a git checkout you can
use `scripts/install_azazel.sh`:

```bash
cd /tmp/azazel-installer
sudo bash scripts/install_azazel.sh
```

The script copies the repository payload to `/opt/azazel`, pushes configuration
into `/etc/azazel`, installs systemd units, and enables the unified
`azctl-unified.service`.

## 3. Configure services

### Interactive TUI Menu Usage

**Recommended**: Use the integrated TUI menu system for operational tasks

```bash
# Launch the main menu
python3 -m azctl.cli menu
```

**TUI Daily Tasks:**
1. **"System Information"** → Check resource usage, temperature, system load
2. **"Service Management"** → Verify all service states and view logs
3. **"Defense Control"** → Monitor current mode, scores, decision history
4. **"Log Monitoring"** → Real-time alert monitoring
5. **"Network Information"** → Interface status and traffic statistics

### Manual Configuration

1. Adjust `/etc/azazel/azazel.yaml` to reflect interface names, QoS policies, and
   alert thresholds.
2. Regenerate the Suricata configuration if a non-default ruleset is required:

   ```bash
   sudo /opt/azazel/scripts/suricata_generate.py \
     /etc/azazel/azazel.yaml \
     /etc/azazel/suricata/suricata.yaml.tmpl \
     --output /etc/suricata/suricata.yaml
   ```
3. Reload services: `sudo systemctl restart azctl-unified.service`.

### Mode presets

The controller maintains three defensive modes. Each mode applies a preset of
delay, traffic shaping, and block behaviour sourced from `azazel.yaml`. Refer to
the [API reference – `/v1/mode`](API_REFERENCE.md#post-v1mode) section for the
remote override that activates these presets during incident response.

| Mode     | Delay (ms) | Shape (kbps) | Block | Use case |
|----------|-----------:|-------------:|:-----:|----------|
| portal   | 100        | –            |  No   | Baseline latency padding to slow automated scanning while keeping users online. |
| shield   | 200        | 128          |  No   | Elevated response once intrusion scoring passes T1; throttles attackers but preserves remote work. |
| lockdown | 300        | 64           | Yes   | Emergency containment when T2 is exceeded; combines shaping with hard blocks until the unlock timer expires. |

Transitions to stricter modes occur when the moving average of recent scores
exceeds the configured thresholds. Unlock timers enforce a cooling-off period
before the daemon steps down to a less restrictive mode. When lockdown is
entered in the field the supervising `azctl/daemon` should apply
`nft -f configs/nftables/lockdown.nft` after updating the generated allowlist.

## 4. Health checks

Use `scripts/sanity_check.sh` to confirm Suricata, Vector, and OpenCanary are
enabled and running. Systemd journal entries from the `azctl` service expose
state transitions and scoring decisions.

## 5. Rollback

To remove Azazel from a host, execute `sudo /opt/azazel/rollback.sh`. The script
deletes `/opt/azazel`, removes `/etc/azazel`, and disables the `azctl-unified.service`.

## Defense Mode Details

### Portal Mode
- **Purpose**: Minimal impact baseline monitoring
- **Features**:
  - Light delay injection (100ms)
  - Normal traffic flow maintained
  - Event logging and scoring continues
- **Use Cases**: Daily operations, normal monitoring

### Shield Mode  
- **Purpose**: Enhanced monitoring and control when threats detected
- **Features**:
  - Moderate delay (200ms)
  - Bandwidth limiting (128kbps)
  - Traffic shaping applied
  - Detailed logging
- **Use Cases**: Suspicious activity detected, moderate threshold exceeded

### Lockdown Mode
- **Purpose**: Complete containment for high-risk situations
- **Features**:
  - High delay (300ms)
  - Strict bandwidth limiting (64kbps)
  - Allowlist-based communication only
  - Medical/emergency FQDN access maintained
- **Use Cases**: Critical threat detected, high score threshold exceeded

## Daily Operations

### TUI Menu-Based Operations

**Recommended**: Use the integrated TUI menu for daily monitoring and operations

```bash
# Launch main menu
python3 -m azctl.cli menu
```

### Routine Maintenance

#### Daily Tasks (TUI Recommended)
```bash
# TUI menu provides:
# - System Information → Resource usage monitoring
# - Service Management → All service status
# - Defense Control → Recent decision history
# - Log Monitoring → Alert summaries

# Command line (for scripting)
sudo systemctl status azctl-unified.service
sudo tail -f /var/log/azazel/decisions.log
sudo tail -f /var/log/suricata/fast.log
```

#### Weekly Tasks
```bash
# System updates
sudo apt update && sudo apt upgrade

# Suricata rule updates
sudo suricata-update
sudo systemctl restart suricata

# Log rotation check
sudo journalctl --disk-usage
sudo journalctl --vacuum-time=7d
```

#### Monthly Tasks
```bash
# Comprehensive health check
sudo /opt/azazel/sanity_check.sh

# Configuration backup
sudo tar -czf /backup/azazel-$(date +%Y%m%d).tar.gz /etc/azazel /opt/azazel/config

# Docker resource cleanup
sudo docker system prune -f

# Service restart (planned maintenance)
sudo systemctl restart azctl-unified.service
```

## Incident Response

### Manual Mode Switching

**Recommended**: Use TUI menu for manual mode changes

```bash
# TUI Menu approach:
# 1. Launch menu: python3 -m azctl.cli menu
# 2. Select "Defense Control"
# 3. Choose "Manual Mode Switch"
# 4. Select desired mode (Portal/Shield/Lockdown)
# 5. Confirm in dialog
```

### Manual Mode Switching (CLI)

Emergency manual mode changes:

```bash
# Switch to Shield mode
echo '{"mode": "shield"}' | sudo tee /tmp/mode.json
python3 -m azctl.cli events --config /tmp/mode.json

# Switch to Lockdown mode
echo '{"mode": "lockdown"}' | sudo tee /tmp/mode.json
python3 -m azctl.cli events --config /tmp/mode.json

# Return to Portal mode
echo '{"mode": "portal"}' | sudo tee /tmp/mode.json
python3 -m azctl.cli events --config /tmp/mode.json
```

### HTTP API Mode Control

```bash
# RESTful API mode switching
curl -X POST http://localhost:8080/v1/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "shield"}'

# Check current mode
curl http://localhost:8080/v1/health
```

### Log Analysis

#### Suricata Alert Analysis
```bash
# Alert type aggregation
jq 'select(.event_type=="alert") | .alert.signature' /var/log/suricata/eve.json | sort | uniq -c

# Source IP aggregation
jq 'select(.event_type=="alert") | .src_ip' /var/log/suricata/eve.json | sort | uniq -c | sort -nr

# Time series alert analysis
jq 'select(.event_type=="alert") | [.timestamp, .alert.signature, .src_ip]' /var/log/suricata/eve.json
```

#### Azazel Decision Log Analysis
```bash
# Mode transition history
grep "mode transition" /var/log/azazel/decisions.log

# Score trend analysis
grep "score:" /var/log/azazel/decisions.log | tail -20

# Threshold exceeded events
grep "threshold exceeded" /var/log/azazel/decisions.log
```

## Configuration Management

### Configuration Template Updates

```bash
# Apply new configuration templates
sudo rsync -av /opt/azazel/configs/ /etc/azazel/

# Check configuration differences
sudo diff -u /etc/azazel/azazel.yaml.backup /etc/azazel/azazel.yaml

# Apply configuration changes
sudo systemctl restart azctl-unified.service
```

### Environment-Specific Configuration

```bash
# Development environment
sudo cp /opt/azazel/configs/environments/development.yaml /etc/azazel/azazel.yaml

# Production environment
sudo cp /opt/azazel/configs/environments/production.yaml /etc/azazel/azazel.yaml

# Testing environment
sudo cp /opt/azazel/configs/environments/testing.yaml /etc/azazel/azazel.yaml
```

## Performance Optimization

### System Tuning

```bash
# I/O scheduler optimization
echo mq-deadline | sudo tee /sys/block/mmcblk0/queue/scheduler

# Network buffer optimization
echo 'net.core.rmem_max = 16777216' | sudo tee -a /etc/sysctl.conf
echo 'net.core.wmem_max = 16777216' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Suricata worker thread adjustment
sudo nano /etc/suricata/suricata.yaml
# Adjust threading.cpu-affinity
```

### Resource Usage Optimization

```bash
# Log level adjustment
sudo nano /etc/azazel/vector/vector.toml
# Set log_level = "warn"

# E-Paper update frequency adjustment  
sudo nano /etc/default/azazel-epd
# Set UPDATE_INTERVAL=30

# OpenCanary service selective enabling
sudo nano /opt/azazel/config/opencanary.conf
# Disable unnecessary services
```

## Monitoring and Alerting

### Key Monitoring Items
```bash
# CPU usage
htop

# Memory usage
free -h

# Disk usage
df -h

# Network traffic
sudo iftop

# Service status
sudo systemctl is-active azctl-unified.service mattermost nginx docker
```

### Alert Configuration Examples
```bash
# Automated health checks via cron
sudo crontab -e
# Add: */15 * * * * /opt/azazel/sanity_check.sh >> /var/log/azazel/health.log

# Disk space warning
sudo nano /etc/crontab
# Add: 0 6 * * * root df -h | grep -E '(9[0-9]%|100%)' && echo "Disk space warning" | wall
```

## Backup and Restore

### Configuration Backup

```bash
# Full backup
sudo tar -czf azazel-full-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  /etc/azazel \
  /opt/azazel/config \
  /var/log/azazel \
  /opt/mattermost/config

# Configuration-only backup
sudo tar -czf azazel-config-backup-$(date +%Y%m%d).tar.gz \
  /etc/azazel \
  /opt/azazel/config
```

### Restore Procedures

```bash
# Stop services
sudo systemctl stop azctl-unified.service

# Restore from backup
sudo tar -xzf azazel-config-backup-YYYYMMDD.tar.gz -C /

# Fix permissions
sudo chown -R root:root /etc/azazel
sudo chmod -R 644 /etc/azazel/*.yaml

# Restart services
sudo systemctl start azctl-unified.service
```

## Security Best Practices

### Access Control

```bash
# SSH key authentication setup
sudo nano /etc/ssh/sshd_config
# PasswordAuthentication no
# PubkeyAuthentication yes

# Firewall configuration
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

### Audit Logging

```bash
# Enable system auditing
sudo apt install auditd
sudo systemctl enable --now auditd

# Azazel file monitoring
echo "-w /etc/azazel/ -p wa -k azazel-config" | sudo tee -a /etc/audit/rules.d/azazel.rules
echo "-w /opt/azazel/ -p wa -k azazel-runtime" | sudo tee -a /etc/audit/rules.d/azazel.rules
sudo systemctl restart auditd
```

## Troubleshooting

For common issues and solutions, refer to [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

### Quick Diagnostics

```bash
# Comprehensive health check
sudo /opt/azazel/sanity_check.sh

# Service status check
sudo systemctl status azctl-unified.service --no-pager

# Recent error log check
sudo journalctl -u azctl-unified.service --since "1 hour ago" | grep -i error
```

## Related Documentation

- [`INSTALLATION.md`](INSTALLATION.md) - Complete installation guide
- [`NETWORK_SETUP.md`](NETWORK_SETUP.md) - Network configuration procedures
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) - Comprehensive problem resolution guide
- [`API_REFERENCE.md`](API_REFERENCE.md) - Python modules and HTTP endpoints
- [`ARCHITECTURE.md`](ARCHITECTURE.md) - System architecture and design

---

*For the latest operational guidance, refer to the [Azazel-Edge repository](https://github.com/01rabbit/Azazel-Edge) and consult with administrators for enterprise deployments.*
