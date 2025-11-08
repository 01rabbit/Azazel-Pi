# E-Paper Display Setup for Azazel Pi

This guide describes how to set up and use the Waveshare E-Paper display with Azazel Pi for real-time status visualization.

## Overview

The E-Paper display integration provides:

- **Real-time status visualization** of Azazel Pi's defensive posture
- **Mode indication** (Portal, Shield, Lockdown) with visual highlighting
- **Network status** showing interface state and IP address
- **Alert counters** for recent and total security events
- **Service monitoring** for Suricata and OpenCanary
- **Boot/shutdown animations** for system state feedback
 - Boot/shutdown animations were removed to improve stability; boot now clears to a clean white screen and shutdown clears then sleeps the display
- **Low power consumption** with partial update support to reduce flicker

## Hardware Requirements

### Supported Displays

- Waveshare 2.13" E-Paper Display (250×122 pixels)
  - Monochrome version: `epd2in13_V4` (recommended)
  - Bicolor version: `epd2in13b_V4`
  - Older versions: `epd2in13_V3`, `epd2in13_V2`

### Connection

The display connects to the Raspberry Pi via SPI interface:

| E-Paper Pin | Raspberry Pi Pin | Function |
|-------------|------------------|----------|
| VCC | 3.3V (Pin 1 or 17) | Power |
| GND | GND (Pin 6, 9, 14, 20, 25, 30, 34, 39) | Ground |
| DIN | GPIO 10 (MOSI, Pin 19) | SPI Data In |
| CLK | GPIO 11 (SCLK, Pin 23) | SPI Clock |
| CS | GPIO 8 (CE0, Pin 24) | Chip Select |
| DC | GPIO 25 (Pin 22) | Data/Command |
| RST | GPIO 17 (Pin 11) | Reset |
| BUSY | GPIO 24 (Pin 18) | Busy Signal |

## Installation

### 1. Enable SPI Interface

```bash
# Using raspi-config
sudo raspi-config
# Navigate to: Interface Options → SPI → Enable

# Or manually edit config
echo "dtparam=spi=on" | sudo tee -a /boot/config.txt

# Reboot to apply
sudo reboot
```

Verify SPI is enabled:

```bash
ls /dev/spidev0.0
# Should exist after reboot
```

### 2. Integrated Installation (Recommended)

E-Paper setup is now integrated into the complete installer. You can prepare the library and service even without the hardware attached.

```bash
# Install with E-Paper integration
sudo scripts/install_azazel_complete.sh --enable-epd --start

# If hardware is not connected, enable emulation mode
sudo scripts/install_azazel_complete.sh --enable-epd --epd-emulate --start
```

After installation, an env file is placed at `/etc/default/azazel-epd`. You can pass extra flags via `EPD_OPTS` (for example to enable emulation):

```bash
sudo sed -i '/^EPD_OPTS=/d' /etc/default/azazel-epd
echo 'EPD_OPTS=--emulate' | sudo tee -a /etc/default/azazel-epd
sudo systemctl restart azazel-epd.service
```

### 2b. Legacy standalone script (deprecated)

`scripts/install_epd.sh` is deprecated. Use `--enable-epd` instead.

### 3. Install systemd Service

The E-Paper service is installed automatically with Azazel Pi, but can be manually installed:

```bash
# Copy service file
sudo cp systemd/azazel-epd.service /etc/systemd/system/

# Copy default configuration
sudo cp deploy/azazel-epd.default /etc/default/azazel-epd

# Reload systemd
sudo systemctl daemon-reload
```

## Configuration

### Service Configuration

Edit `/etc/default/azazel-epd` to customize:

```bash
# Update interval in seconds (default: 10)
UPDATE_INTERVAL=10

# Path to events.json log file
EVENTS_LOG=/var/log/azazel/events.json

# Enable debug logging (0 or 1)
DEBUG=0
```

### Display Driver Selection

If using a different E-Paper model, you may need to adjust the driver:

1. Check available drivers in `/opt/waveshare-epd/RaspberryPi_JetsonNano/python/lib/waveshare_epd/`
2. Edit `azazel_pi/core/display/renderer.py` and update the `driver_name` parameter

## Usage

### Enable and Start Service

```bash
# If you used --start, the service may already be enabled
sudo systemctl enable azazel-epd.service
sudo systemctl start azazel-epd.service
sudo systemctl status azazel-epd.service
```

### Manual Testing

Test the display without running the full daemon:

```bash
# Test mode: single status update (use --emulate if no hardware)
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=test --emulate

# Boot performs a non-animated clear-to-white (no long animation)
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=boot

# Shutdown clears the display and puts the hardware to sleep
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=shutdown

# Run daemon in foreground with debug output
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py \
    --mode=daemon \
    --interval=5 \
    --debug
```

### View Logs

```bash
# View service logs
sudo journalctl -u azazel-epd.service -f

# View recent activity
sudo journalctl -u azazel-epd.service --since "10 minutes ago"
```

## Display Layout

The E-Paper display shows the following information:

```
╔════════════════════════════════════════════╗
║          Azazel-Pi (inverted)              ║
╠════════════════════════════════════════════╣
║ [Mode: SHIELD]          Score: 32.5        ║
╟────────────────────────────────────────────╢
║ ● eth0: 192.168.1.100                      ║
║ Alerts: 3/47 (5m/total)                    ║
║ Svc: Suri✓ Canary✓                         ║
╟────────────────────────────────────────────╢
║ Up 12h34m | 14:23:45                       ║
╚════════════════════════════════════════════╝
```

### Mode Indicators

- **PORTAL**: White background (normal operations)
- **SHIELD**: Black background, white text (heightened monitoring)
- **LOCKDOWN**: Black background, white text (full containment)

### Status Icons

- `●` = Interface up and active
- `○` = Interface down or no link
- `✓` = Service active
- `✗` = Service inactive

## Troubleshooting

### Display Not Updating

1. **Check SPI is enabled:**
   ```bash
   lsmod | grep spi
   # Should show spi_bcm2835 or similar
   ```

2. **Verify device exists:**
   ```bash
   ls -l /dev/spidev0.0
   # Should be present
   ```

3. **Check service status:**
   ```bash
   sudo systemctl status azazel-epd.service
   ```

4. **Review logs:**
   ```bash
   sudo journalctl -u azazel-epd.service --no-pager | tail -50
   ```

### Display Shows Artifacts or Ghosting

This is normal for E-Paper displays. To mitigate:

1. **Full refresh:** Disable gentle updates
   ```bash
   # Edit /etc/default/azazel-epd
   # Run daemon with --no-gentle flag
   ```

2. **Clear display manually:**
   ```bash
   sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=shutdown
   ```

### Driver Not Found Error

If you see "E-Paper driver not found":

1. **Check library installation:**
   ```bash
   ls /opt/waveshare-epd/RaspberryPi_JetsonNano/python/lib/waveshare_epd/
   ```

2. **Verify your display model:**
   - Check the label on your E-Paper HAT
   - Match with available driver files

3. **Try alternative driver:**
   ```python
   # Edit renderer.py, try different driver name:
   # epd2in13_V3, epd2in13_V2, epd2in13b_V4, etc.
   ```

### Permission Errors

The E-Paper service runs as root because SPI access requires elevated privileges.

If testing manually, always use `sudo`:

```bash
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=test
```

### High CPU Usage

E-Paper updates are CPU-intensive. To reduce load:

1. **Increase update interval:**
   ```bash
   # Edit /etc/default/azazel-epd
   UPDATE_INTERVAL=30  # Update every 30 seconds instead of 10
   ```

2. **Use gentle updates** (default):
   - Partial refresh uses less CPU
   - May cause slight ghosting over time

## Integration with Azazel Pi

The E-Paper display automatically integrates with:

- **State Machine**: Shows current mode (portal/shield/lockdown)
- **Scorer**: Displays moving average of threat score
- **Event Logs**: Counts alerts from `/var/log/azazel/events.json`
- **Network Status**: Monitors primary interface (eth0 by default)
- **Service Status**: Checks Suricata and OpenCanary via systemd

## Advanced Configuration

### Custom Interface Monitoring

To monitor a different network interface, modify the status collector:

```python
# Edit azazel_pi/core/display/status_collector.py
# In the collect() method, change:
network=self._get_network_status("wlan0"),  # Instead of "eth0"
```

### Custom Display Layout

The display renderer can be customized:

```python
# Edit azazel_pi/core/display/renderer.py
# Modify the render_status() method to change layout
```

### Multiple Displays

To run multiple displays (e.g., different update intervals):

1. Create separate systemd services
2. Use different configuration files
3. Ensure each uses a unique SPI chip select pin

## Performance Notes

- **Update Time**: ~2-3 seconds for full refresh, ~1 second for partial
- **Power Consumption**: ~15mA active, ~0mA when sleeping
- **Refresh Rate**: Recommended 10-30 seconds to balance visibility and lifespan
- **Display Lifespan**: Millions of refreshes (years of continuous use)

## See Also

- [Waveshare E-Paper Documentation](https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT)
- [Azazel Pi Architecture](ARCHITECTURE.md)
- [Operations Guide](OPERATIONS.md)

## Credits

E-Paper integration adapted from the [Azazel-Zero](../Azazel-Zero/) portable barrier project, which implements similar status display functionality on Raspberry Pi Zero 2 W.
