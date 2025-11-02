# Archived Documentation

This directory contains documentation that has been superseded by newer, consolidated guides. These files are preserved for reference but are **not recommended** for new deployments.

## Archived Files

### Installation and Setup
- **`setup.md`** - Legacy system architecture and Docker-based setup procedures
  - **Replaced by**: [`INSTALLATION.md`](../INSTALLATION.md)
  - **Reason**: Outdated Docker-centric approach, superseded by single-script installer

- **`Minimal_Install_and_Verification.md`** - Manual RaspAP installation procedures  
  - **Replaced by**: [`INSTALLATION.md`](../INSTALLATION.md) and [`NETWORK_SETUP.md`](../NETWORK_SETUP.md)
  - **Reason**: Manual steps now automated by `install_azazel.sh`

### Network Configuration
- **`RaspAP_config.md`** - RaspAP WebGUI configuration guide
  - **Replaced by**: [`NETWORK_SETUP.md`](../NETWORK_SETUP.md)
  - **Reason**: RaspAP integration deprecated in favor of native configuration

- **`wlan_setup.md`** - Manual Wi-Fi access point configuration
  - **Replaced by**: [`NETWORK_SETUP.md`](../NETWORK_SETUP.md)
  - **Reason**: Manual network setup consolidated into comprehensive guide

## Migration Guide

If you're using procedures from these archived documents, migrate to the current documentation:

### From `setup.md` → [`INSTALLATION.md`](../INSTALLATION.md)
- Replace Docker Compose workflows with `scripts/install_azazel.sh`
- Update service management from docker commands to systemctl
- Migrate configuration from Docker environment files to `/etc/azazel/azazel.yaml`

### From `Minimal_Install_and_Verification.md` → [`INSTALLATION.md`](../INSTALLATION.md)
- Use automated installation instead of manual package installation
- Follow E-Paper setup procedures in main installation guide
- Use built-in health checks instead of manual verification steps

### From `RaspAP_config.md` → [`NETWORK_SETUP.md`](../NETWORK_SETUP.md)  
- Configure network settings via `azazel.yaml` instead of RaspAP WebGUI
- Use automatic gateway mode setup instead of manual WebGUI configuration
- Migrate DHCP settings to new configuration format

### From `wlan_setup.md` → [`NETWORK_SETUP.md`](../NETWORK_SETUP.md)
- Use automatic network configuration instead of manual interface setup
- Migrate hostapd/dnsmasq configs to Azazel configuration management
- Follow new NAT and firewall configuration procedures

## Why These Were Archived

1. **Complexity Reduction**: Manual multi-step procedures replaced by single-script automation
2. **Maintenance Burden**: Multiple configuration methods created support overhead  
3. **User Experience**: Consolidated guides provide clearer path from installation to operation
4. **Technology Evolution**: Newer approaches (systemd, native packaging) replaced Docker-centric design
5. **Documentation Debt**: Overlapping information caused confusion and consistency issues

## Current Documentation Structure

For new deployments, use this documentation hierarchy:

1. **[`INSTALLATION.md`](../INSTALLATION.md)** - Complete installation guide
2. **[`NETWORK_SETUP.md`](../NETWORK_SETUP.md)** - Network configuration procedures  
3. **[`OPERATIONS.md`](../OPERATIONS.md)** - Day-to-day operational procedures
4. **[`TROUBLESHOOTING.md`](../TROUBLESHOOTING.md)** - Comprehensive problem resolution
5. **[`EPD_SETUP.md`](../EPD_SETUP.md)** - E-Paper display configuration
6. **[`ARCHITECTURE.md`](../ARCHITECTURE.md)** - System design and components
7. **[`API_REFERENCE.md`](../API_REFERENCE.md)** - Python modules and HTTP endpoints

---

*These archived documents are maintained for historical reference only. For current procedures, always refer to the main documentation in the parent directory.*