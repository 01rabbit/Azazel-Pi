#!/usr/bin/env bash
# Install Waveshare E-Paper library and dependencies for Azazel Pi
set -euo pipefail

log() {
  printf '\033[1;34m[epd-setup]\033[0m %s\n' "$1"
}

error() {
  printf '\033[1;31m[epd-setup]\033[0m %s\n' "$1" >&2
  exit 1
}

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  error "This script must be run as root. Use sudo."
fi

EPD_ROOT="/opt/waveshare-epd"
EPD_REPO="https://github.com/waveshare/e-Paper.git"
EPD_PYTHON_PATH="${EPD_ROOT}/RaspberryPi_JetsonNano/python"

# Install system dependencies
log "Installing system dependencies for E-Paper..."
apt-get update
apt-get install -y \
  python3-pil \
  python3-numpy \
  python3-spidev \
  python3-rpi.gpio \
  libopenjp2-7 \
  libtiff5 \
  git

# Enable SPI if not already enabled
if ! grep -q "^dtparam=spi=on" /boot/config.txt 2>/dev/null && \
   ! grep -q "^dtparam=spi=on" /boot/firmware/config.txt 2>/dev/null; then
  log "Enabling SPI interface..."
  CONFIG_FILE="/boot/config.txt"
  [[ -f /boot/firmware/config.txt ]] && CONFIG_FILE="/boot/firmware/config.txt"
  echo "dtparam=spi=on" >> "$CONFIG_FILE"
  log "SPI enabled. Reboot required for changes to take effect."
fi

# Clone Waveshare E-Paper library if not present
if [[ ! -d "$EPD_ROOT" ]]; then
  log "Cloning Waveshare E-Paper library..."
  git clone --depth 1 "$EPD_REPO" "$EPD_ROOT"
else
  log "Waveshare E-Paper library already present at $EPD_ROOT"
fi

# Verify Python library path exists
if [[ ! -d "$EPD_PYTHON_PATH" ]]; then
  error "E-Paper Python library not found at $EPD_PYTHON_PATH"
fi

log "E-Paper library setup complete!"
log "Library path: $EPD_PYTHON_PATH"
log ""
log "To test the display, run:"
log "  sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=test"
