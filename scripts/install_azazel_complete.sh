#!/usr/bin/env bash
# Complete Azazel-Pi Installation Script
# Handles all dependencies, configurations, and service setup automatically
set -euo pipefail

# Color output functions
log() {
  printf '\033[1;34m[azazel]\033[0m %s\n' "$1"
}

error() {
  printf '\033[1;31m[azazel]\033[0m %s\n' "$1" >&2
  exit 1
}

warn() {
  printf '\033[1;33m[azazel]\033[0m %s\n' "$1"
}

success() {
  printf '\033[1;32m[azazel]\033[0m %s\n' "$1"
}

usage() {
  cat <<USAGE
Usage: $0 [--start] [--skip-models] [--enable-epd] [--epd-force] [--epd-emulate]

Options:
  --start        Start all services after installation completes
  --skip-models  Skip Ollama model setup (for manual configuration)
  --enable-epd   Install and integrate E-Paper display (library + service)
  --epd-force    Proceed with E-Paper service install even if SPI device absent
  --epd-emulate  Enable E-Paper emulation mode (no hardware required)
  -h, --help     Show this help message

This script performs a complete Azazel-Pi installation including:
- Base dependencies (Suricata, Docker, Vector, OpenCanary)
- Service configuration and systemd units
- Ollama setup with Docker
- E-Paper display dependencies (Pillow, NumPy)
- Configuration file deployment
- Optional service startup

USAGE
}

# Parse arguments
START_SERVICES=0
SKIP_MODELS=0
ENABLE_EPD=0
EPD_FORCE=0
EPD_EMULATE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --start)
      START_SERVICES=1
      shift
      ;;
    --skip-models)
      SKIP_MODELS=1
      shift
      ;;
    --enable-epd)
      ENABLE_EPD=1
      shift
      ;;
    --epd-force)
      EPD_FORCE=1
      shift
      ;;
    --epd-emulate)
      EPD_EMULATE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      error "Unknown option: $1"
      ;;
  esac
done

# Check for root privileges
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  error "This installer must be run as root. Use sudo if necessary."
fi

# Verify we're in the Azazel-Pi directory
if [[ ! -f "scripts/install_azazel.sh" || ! -f "pyproject.toml" ]]; then
  error "Please run this script from the Azazel-Pi project root directory"
fi

log "Starting complete Azazel-Pi installation..."

# Step 1: Run base installation
log "Step 1/9: Running base installation (dependencies, Docker, services)"
bash scripts/install_azazel.sh || error "Base installation failed"

# Step 2: Optional E-Paper integration
log "Step 2/9: Optional E-Paper integration"
if [[ $ENABLE_EPD -eq 1 ]]; then
  log "E-Paper integration requested (--enable-epd)"
  apt-get update
  # Core deps (some may already be present)
  apt-get install -y \
    python3-pil \
    python3-numpy \
    python3-dev \
    python3-spidev \
    python3-rpi.gpio \
  libopenjp2-7 \
  libtiff6 \
  libtiff-tools \
    git || warn "One or more E-Paper dependency packages failed to install"

  # Enable SPI if not already enabled (both legacy + Pi5 path)
  CONFIG_FILE="/boot/config.txt"
  [[ -f /boot/firmware/config.txt ]] && CONFIG_FILE="/boot/firmware/config.txt"
  if ! grep -q '^dtparam=spi=on' "$CONFIG_FILE" 2>/dev/null; then
    echo "dtparam=spi=on" >> "$CONFIG_FILE"
    warn "SPI was not enabled. Added dtparam=spi=on to $CONFIG_FILE (reboot required)."
  fi

  EPD_ROOT="/opt/waveshare-epd"
  if [[ ! -d "$EPD_ROOT" ]]; then
    log "Cloning Waveshare E-Paper library to $EPD_ROOT"
    if ! git clone --depth 1 https://github.com/waveshare/e-Paper.git "$EPD_ROOT"; then
      warn "Failed to clone Waveshare E-Paper repository; continuing without E-Paper"
    fi
  else
    log "Waveshare E-Paper library already present"
  fi

  # Install default configuration + service
  if [[ -f deploy/azazel-epd.default ]]; then
    install -m 0644 deploy/azazel-epd.default /etc/default/azazel-epd
    if [[ $EPD_EMULATE -eq 1 ]]; then
      sed -i '/^#\?EMULATE=/d' /etc/default/azazel-epd
      echo 'EMULATE=1' >> /etc/default/azazel-epd
    fi
  fi
  if [[ -f systemd/azazel-epd.service ]]; then
    install -m 0644 systemd/azazel-epd.service /etc/systemd/system/azazel-epd.service
  fi

  # Decide whether to enable/start service
  SPI_PRESENT=0
  [[ -e /dev/spidev0.0 ]] && SPI_PRESENT=1
  if [[ $SPI_PRESENT -eq 1 || $EPD_FORCE -eq 1 || $EPD_EMULATE -eq 1 ]]; then
    log "Registering E-Paper service (SPI_PRESENT=$SPI_PRESENT FORCE=$EPD_FORCE EMULATE=$EPD_EMULATE)"
    systemctl daemon-reload || true
    systemctl enable azazel-epd.service || warn "Failed to enable azazel-epd.service"
    if [[ $START_SERVICES -eq 1 ]]; then
      systemctl start azazel-epd.service || warn "Failed to start azazel-epd.service"
    fi
  else
    warn "SPI device /dev/spidev0.0 not found; skipping service enable (use --epd-force or --epd-emulate to override)."
  fi
else
  log "E-Paper integration not requested (use --enable-epd to include)"
fi

# Step 3: Configure all service files
log "Step 3/9: Deploying configuration files"

# Copy all configs to /etc/azazel
cp -r configs/* /etc/azazel/ || error "Failed to copy configuration files"

# Ensure main config is in the root
if [[ -f "/etc/azazel/network/azazel.yaml" ]]; then
  cp /etc/azazel/network/azazel.yaml /etc/azazel/azazel.yaml
fi

# Enhanced Vector configuration
mkdir -p /etc/azazel/vector /var/lib/vector
if [[ -f "deploy/vector.toml" ]]; then
  cp deploy/vector.toml /etc/azazel/vector/vector.toml
else
  # Create optimized Vector configuration if not present
  cat > /etc/azazel/vector/vector.toml <<'EOF'
# Enhanced Vector configuration for Azazel-Pi
[sources.suricata_eve]
type = "file"
include = ["/var/log/suricata/eve.json"]
read_from = "beginning"

[sources.syslog]
type = "file"
include = ["/var/log/syslog"]

[transforms.parse_suricata]
type = "json_parser"
inputs = ["suricata_eve"]

[transforms.parse_syslog]
type = "syslog_parser"
inputs = ["syslog"]

[sinks.azazel_events]
type = "file"
inputs = ["parse_suricata"]
path = "/var/lib/vector/azazel-events.log"
encoding.codec = "json"

[sinks.system_logs]
type = "file"
inputs = ["parse_syslog"]
path = "/var/lib/vector/system.log"
encoding.codec = "text"
EOF
fi

# Set proper ownership for Vector
chown -R root:root /etc/azazel/vector
chown -R root:root /var/lib/vector
chmod 755 /var/lib/vector
chmod 644 /etc/azazel/vector/vector.toml

# Copy OpenCanary configuration
mkdir -p /etc/opencanaryd
if [[ -f "deploy/opencanary.conf" ]]; then
  cp deploy/opencanary.conf /etc/opencanaryd/opencanary.conf
fi

success "Configuration files deployed"

# Step 4: Enhanced Docker Configuration and Services
log "Step 4/9: Enhanced Docker configuration and services (PostgreSQL + Ollama)"

# Configure Docker with optimized settings for Raspberry Pi
DOCKER_CONFIG_FILE="/etc/docker/daemon.json"
log "Configuring Docker daemon for optimal performance..."
cat > "$DOCKER_CONFIG_FILE" <<'EOF'
{
  "default-runtime": "runc",
  "runtimes": {"runc": {"path": "runc"}},
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"},
  "default-ulimits": {"memlock": {"Name": "memlock", "Hard": 524288000, "Soft": 524288000}},
  "max-concurrent-downloads": 2,
  "max-concurrent-uploads": 2,
  "experimental": false
}
EOF
chown root:root "$DOCKER_CONFIG_FILE"
chmod 644 "$DOCKER_CONFIG_FILE"

# Ensure Docker is running with new configuration
systemctl enable --now docker || error "Failed to enable Docker"
systemctl restart docker || warn "Failed to restart Docker with new configuration"
sleep 5

# Start Docker Compose services
cd deploy
docker-compose up -d || error "Failed to start Docker services"
cd ..

# Wait for services to be ready with better health checking
log "Waiting for Docker services to initialize..."
for i in {1..30}; do
  if docker ps | grep -q "azazel_postgres.*Up" && docker ps | grep -q "azazel_ollama.*Up"; then
    success "Docker services are running"
    break
  fi
  if [[ $i -eq 30 ]]; then
    warn "Docker services may not be fully ready, continuing..."
  fi
  sleep 2
done

# Verify PostgreSQL is responding
for i in {1..30}; do
  if docker exec azazel_postgres pg_isready -U mmuser -d mattermost >/dev/null 2>&1; then
    success "PostgreSQL is ready"
    break
  fi
  if [[ $i -eq 30 ]]; then
    warn "PostgreSQL may not be fully ready, continuing..."
  fi
  sleep 2
done

# Verify Ollama is responding
for i in {1..15}; do
  if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    success "Ollama is ready"
    break
  fi
  if [[ $i -eq 15 ]]; then
    warn "Ollama may not be fully ready, continuing..."
  fi
  sleep 2
done

# Step 5: Enhanced Suricata Configuration
log "Step 5/9: Enhanced Suricata configuration with auto-update system"

# Configure Suricata for non-root execution with proper capabilities
SURICATA_USER=suricata
SURICATA_HOME=/var/lib/suricata
SURICATA_LOG=/var/log/suricata
RULES_DIR=${SURICATA_HOME}/rules
SYSTEMD_DROPIN_DIR=/etc/systemd/system/suricata.service.d
DROPIN_FILE=${SYSTEMD_DROPIN_DIR}/override-nonroot.conf

# Create suricata user if it doesn't exist
if ! id -u "$SURICATA_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SURICATA_USER"
  log "Created system user $SURICATA_USER"
fi

# Ensure directories exist with proper ownership
mkdir -p "$RULES_DIR" "$SURICATA_LOG"
chown -R ${SURICATA_USER}:${SURICATA_USER} "$SURICATA_HOME" "$SURICATA_LOG"
chmod -R 750 "$SURICATA_HOME" "$SURICATA_LOG"
chmod 755 "$RULES_DIR"

# Create systemd drop-in for non-root execution with capabilities
mkdir -p "$SYSTEMD_DROPIN_DIR"
cat > "$DROPIN_FILE" <<'EOF'
[Service]
User=suricata
Group=suricata
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN
NoNewPrivileges=no
EOF

# Install suricata-update auto-update system
UPDATE_SCRIPT_PATH=/usr/local/bin/azazel-suricata-update.sh
cat > "$UPDATE_SCRIPT_PATH" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
LOG=/var/log/suricata/azazel-suricata-update.log
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

echo "=== azazel suricata-update run: $(date -Iseconds) ==="
# Run suricata-update and test config
if ! /usr/bin/suricata-update; then
  echo "suricata-update failed"
  exit 2
fi
# Test config
if ! /usr/bin/suricata -T -c /etc/suricata/suricata.yaml; then
  echo "suricata config test failed"
  exit 3
fi
# Restart service if everything OK
systemctl restart suricata
echo "suricata update completed at $(date -Iseconds)"
EOF
chmod 755 "$UPDATE_SCRIPT_PATH"
chown root:root "$UPDATE_SCRIPT_PATH"

# Install systemd service + timer for auto-updates
cat > "/etc/systemd/system/azazel-suricata-update.service" <<'EOF'
[Unit]
Description=Run azazel suricata-update wrapper
RefuseManualStart=no
RefuseManualStop=no

[Service]
Type=oneshot
ExecStart=/usr/local/bin/azazel-suricata-update.sh
OnFailure=azazel-suricata-update-failure@%n.service
EOF

cat > "/etc/systemd/system/azazel-suricata-update.timer" <<'EOF'
[Unit]
Description=Daily timer for azazel suricata-update

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Failure handler for update failures
cat > "/etc/systemd/system/azazel-suricata-update-failure@.service" <<'EOF'
[Unit]
Description=Handle suricata-update failure

[Service]
Type=oneshot
ExecStart=/bin/sh -c '/bin/logger -t azazel-suricata-update "suricata-update failed on %i"; echo "suricata-update failed on %i at $(date)" >> /var/log/suricata/azazel-suricata-update-failure.log'

[Install]
WantedBy=multi-user.target
EOF

# Deploy local rules if present
if [ -f "configs/suricata/local.rules" ]; then
  cp "configs/suricata/local.rules" "$RULES_DIR/local.rules"
  chown ${SURICATA_USER}:${SURICATA_USER} "$RULES_DIR/local.rules"
  chmod 0640 "$RULES_DIR/local.rules"
  log "Deployed custom Suricata rules"
fi

# Ensure runtime directory for unix socket with correct ownership
mkdir -p /run/suricata
chown ${SURICATA_USER}:${SURICATA_USER} /run/suricata
chmod 0755 /run/suricata

# Install logrotate for update logs
cat > /etc/logrotate.d/azazel-suricata-update <<'EOF'
/var/log/suricata/azazel-suricata-update.log {
    rotate 7
    daily
    missingok
    notifempty
    compress
    create 0640 root adm
}
/var/log/suricata/azazel-suricata-update-failure.log {
    rotate 7
    daily
    missingok
    notifempty
    compress
    create 0640 root adm
}
EOF

success "Enhanced Suricata configuration completed"

# Step 5b: Configure all systemd services
log "Step 5b/9: Configuring systemd services"

# Enable core services
systemctl enable azctl-unified.service || warn "Failed to enable azctl-unified.service"
systemctl enable suricata.service || warn "Failed to enable suricata.service" 
systemctl enable vector.service || warn "Failed to enable vector.service"
systemctl enable opencanary.service || warn "Failed to enable opencanary.service"
systemctl enable mattermost.service || warn "Failed to enable mattermost.service"
systemctl enable nginx.service || warn "Failed to enable nginx.service"

# Enable Suricata auto-update timer
systemctl enable azazel-suricata-update.timer || warn "Failed to enable suricata auto-update timer"

success "Systemd services configured"

# Step 6: Configure Nginx reverse proxy
log "Step 6/9: Setting up Nginx reverse proxy"

if [[ -f "deploy/nginx-site.conf" ]]; then
  # Deploy nginx configuration
  cp deploy/nginx-site.conf /etc/nginx/sites-available/azazel
  ln -sf /etc/nginx/sites-available/azazel /etc/nginx/sites-enabled/azazel
  
  # Remove default site if it exists
  rm -f /etc/nginx/sites-enabled/default
  
  # Test nginx configuration
  nginx -t && systemctl reload nginx || warn "Nginx configuration may have issues"
  success "Nginx reverse proxy configured"
else
  warn "Nginx configuration file not found, skipping..."
fi

# Step 7: Ollama model setup instructions
log "Step 7/9: Ollama model setup"

if [[ $SKIP_MODELS -eq 0 ]]; then
  # Create models directory
  mkdir -p /opt/models
  chown root:root /opt/models
  chmod 755 /opt/models
  
  cat <<MODEL_SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📥 OLLAMA MODEL SETUP REQUIRED

Please download and place the following model file:

  Model: Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf
  Size:  ~1.1GB
  URL:   https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf

  Download command:
  wget -O /opt/models/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf \\
    https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf

  After download, run:
  sudo chmod 644 /opt/models/*.gguf
  sudo docker exec azazel_ollama ollama create qwen2.5-threat-v2 -f /opt/models/Qwen2.5-threat.Modelfile

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODEL_SETUP

  # Create Ollama Modelfile template
  cat > /opt/models/Qwen2.5-threat.Modelfile << 'EOF'
FROM /models/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf

PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER top_k 20
PARAMETER num_ctx 1024

SYSTEM """You are a cybersecurity threat analyst. Analyze network events and respond ONLY in valid JSON format.

Domain "malware-c2.example.com" is KNOWN MALICIOUS C&C infrastructure.
HTTP POST with encrypted payload to C&C = HIGH THREAT.

Respond exactly like this:
{"score": 85, "explanation": "C&C communication detected", "action": "block"}

Score ranges: 0-30=benign, 31-60=suspicious, 61-80=threat, 81-100=critical"""
EOF

  success "Model setup instructions provided. Modelfile created at /opt/models/Qwen2.5-threat.Modelfile"
else
  log "Skipping model setup as requested"
fi

# Step 8: Final service startup
log "Step 8/9: Final configuration and service startup"

# Ensure log directories exist
mkdir -p /var/log/azazel
chown azazel:azazel /var/log/azazel

# Final configuration sync
systemctl daemon-reload

if [[ $START_SERVICES -eq 1 ]]; then
  log "Starting all services..."
  
  # Start services in order
  systemctl start vector.service || warn "Vector service may have issues"
  systemctl start opencanary.service || warn "OpenCanary service may have issues"  
  systemctl start azctl-unified.service || warn "Azctl-unified service may have issues"
  systemctl start nginx.service || warn "Nginx service may have issues"
  
  # Wait a moment for services to stabilize
  sleep 5
  
  # Show service status
  # Start Suricata auto-update timer
  systemctl start azazel-suricata-update.timer || warn "Failed to start Suricata auto-update timer"
  
  log "Service status check:"
  services=("azctl-unified" "suricata" "vector" "opencanary" "nginx" "docker")
  for service in "${services[@]}"; do
    if systemctl is-active --quiet "$service.service"; then
      success "✓ $service: running"
    else
      warn "✗ $service: not running"
    fi
  done
  
  # Check Suricata auto-update timer
  if systemctl is-active --quiet "azazel-suricata-update.timer"; then
    success "✓ suricata-auto-update: timer active"
  else
    warn "✗ suricata-auto-update: timer not active"
  fi
  
  # Show Docker containers
  log "Docker containers:"
  docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(azazel_|NAMES)"
  
else
  log "Services configured but not started. Use --start flag to auto-start."
fi

# Installation summary
cat <<SUMMARY

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎉 AZAZEL-PI INSTALLATION COMPLETE

✅ Installed components:
  • Suricata IDS/IPS with auto-update system
  • Vector log shipper (enhanced configuration)
  • OpenCanary honeypot
  • PostgreSQL (Docker, optimized)
  • Ollama AI (Docker, optimized)
  • Nginx reverse proxy
$( [[ $ENABLE_EPD -eq 1 ]] && echo "   • E-Paper display integration ("$([ $EPD_EMULATE -eq 1 ] && echo emulation || ([[ -e /dev/spidev0.0 ]] && echo hardware || echo pending-hardware))")" )
  • Automated rule updates and monitoring

✅ Configuration files:
   • /etc/azazel/azazel.yaml (main config)
   • /etc/azazel/ai_config.json (AI settings)
   • /etc/opencanaryd/opencanary.conf
   • /etc/azazel/vector/vector.toml

📋 Next steps:
  1. Download Ollama model to /opt/models/ (see instructions above)
  2. Configure network interfaces in /etc/azazel/azazel.yaml if needed
  3. Set up Mattermost webhooks at http://YOUR_IP:8065
  4. (Optional) Reboot if SPI was just enabled for E-Paper
  5. Start services: sudo systemctl start azctl-unified.service (if not auto-started)
  6. Monitor status: python3 -m azctl.cli status
$( [[ $ENABLE_EPD -eq 1 ]] && echo "   7. Test E-Paper daemon: sudo systemctl status azazel-epd.service" )

📖 Documentation: docs/ja/INSTALLATION.md
🔧 Troubleshooting: scripts/sanity_check.sh

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUMMARY

success "Installation completed successfully!"
exit 0