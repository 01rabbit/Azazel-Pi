#!/usr/bin/env bash
# Convenience installer that provisions Azazel and its dependencies on Debian-based systems.
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 [--start]

Options:
  --start   Start the azctl-unified.service after provisioning completes.
  -h, --help  Show this help message.
USAGE
}

log() {
  printf '\033[1;34m[azazel]\033[0m %s\n' "$1"
}

error() {
  printf '\033[1;31m[azazel]\033[0m %s\n' "$1" >&2
  exit 1
}

START_SERVICES=0
DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --start)
      START_SERVICES=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
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

if [[ ${DRY_RUN:-0} -eq 0 && ${EUID:-$(id -u)} -ne 0 ]]; then
  error "This installer must be run as root. Use sudo if necessary."
fi

if [[ ! -f /etc/os-release ]]; then
  error "Unsupported platform: /etc/os-release not found."
fi

. /etc/os-release
if [[ ${ID_LIKE:-} != *debian* && ${ID:-} != debian ]]; then
  error "This installer currently supports Debian-based distributions."
fi

if ! command -v apt-get >/dev/null 2>&1; then
  error "apt-get is required to install dependencies."
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_ROOT="/opt/azazel"
CONFIG_ROOT="/etc/azazel"

MATTERMOST_DB_NAME="${MATTERMOST_DB_NAME:-mattermost}"
MATTERMOST_DB_USER="${MATTERMOST_DB_USER:-mmuser}"
MATTERMOST_DB_PASSWORD="${MATTERMOST_DB_PASSWORD:-securepassword}"
MATTERMOST_VERSION="${MATTERMOST_VERSION:-9.7.1}"
MATTERMOST_TARBALL="${MATTERMOST_TARBALL:-}"
MATTERMOST_DIR="/opt/mattermost"
MATTERMOST_USER="mattermost"

install_mattermost() {
  if ! id -u "$MATTERMOST_USER" >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$MATTERMOST_DIR" "$MATTERMOST_USER"
  fi

  local mattermost_binary="$MATTERMOST_DIR/bin/mattermost"
  # If binary exists but is the wrong architecture (e.g., x86_64 on arm64 host), remove and re-install
  if [[ -f "$mattermost_binary" ]]; then
    BIN_INFO="$(file "$mattermost_binary" 2>/dev/null || true)"
    ARCHD="$(dpkg --print-architecture 2>/dev/null || true)"
    if [[ "$BIN_INFO" =~ "x86-64" && ( "$ARCHD" == "arm64" || "$ARCHD" == "aarch64" ) ]]; then
      log "Detected Mattermost binary for x86_64 on an ARM host; removing to reinstall correct arch"
      rm -rf "$MATTERMOST_DIR"
    fi
  fi

  if [[ ! -x "$mattermost_binary" ]]; then
    log "Installing Mattermost ${MATTERMOST_VERSION}"
    # Determine architecture-aware tarball if not provided
    if [[ -z "${MATTERMOST_TARBALL:-}" ]]; then
      ARCHD="$(dpkg --print-architecture 2>/dev/null || true)"
      case "$ARCHD" in
        amd64|x86_64)
          TARBALL_NAME="mattermost-team-${MATTERMOST_VERSION}-linux-amd64.tar.gz" ;;
        arm64|aarch64)
          # Recent Mattermost releases provide an arm64 tarball
          TARBALL_NAME="mattermost-team-${MATTERMOST_VERSION}-linux-arm64.tar.gz" ;;
        armhf|armv7l)
          # Fallback: try arm64 build; older armv7 builds may not be available
          TARBALL_NAME="mattermost-team-${MATTERMOST_VERSION}-linux-arm64.tar.gz" ;;
        *)
          TARBALL_NAME="mattermost-team-${MATTERMOST_VERSION}-linux-amd64.tar.gz" ;;
      esac
      MATTERMOST_TARBALL="https://releases.mattermost.com/${MATTERMOST_VERSION}/${TARBALL_NAME}"
      log "Selected Mattermost tarball: $MATTERMOST_TARBALL (arch: $ARCHD)"
    fi

    local tmp_tar tmp_dir SRC_DIR
    tmp_tar="$(mktemp /tmp/mattermost.XXXXXX.tar.gz)"
    # Download with retries to be more resilient to transient network errors
    if ! curl -fsSL --retry 3 --retry-connrefused --retry-delay 2 --max-time 600 "$MATTERMOST_TARBALL" -o "$tmp_tar"; then
      rm -f "$tmp_tar"
      error "Failed to download Mattermost tarball from $MATTERMOST_TARBALL"
    fi

    tmp_dir="$(mktemp -d /tmp/mattermost.XXXXXX)"
    if ! tar -xzf "$tmp_tar" -C "$tmp_dir"; then
      rm -f "$tmp_tar"
      rm -rf "$tmp_dir"
      error "Failed to extract Mattermost tarball (corrupt download?): $tmp_tar"
    fi
    # Many Mattermost tarballs contain a top-level directory named 'mattermost' or 'mattermost-team-*'
    if [[ -d "$tmp_dir/mattermost" ]]; then
      SRC_DIR="$tmp_dir/mattermost"
    else
      # Try to find first directory inside extracted tree
      SRC_DIR="$(find "$tmp_dir" -maxdepth 1 -type d | tail -n +2 | head -n1)"
    fi
    if [[ -z "$SRC_DIR" || ! -d "$SRC_DIR" ]]; then
      rm -rf "$tmp_dir" "$tmp_tar"
      error "Mattermost tarball did not contain the expected directory structure."
    fi
    # Backup existing install atomically before replacing
    if [[ -d "$MATTERMOST_DIR" && ! -L "$MATTERMOST_DIR" ]]; then
      BACKUP_DIR="${MATTERMOST_DIR}.bak.$(date +%s)"
      log "Backing up existing $MATTERMOST_DIR to $BACKUP_DIR"
      mv "$MATTERMOST_DIR" "$BACKUP_DIR"
    fi
    mkdir -p "$MATTERMOST_DIR"
    if ! rsync -a "$SRC_DIR/" "$MATTERMOST_DIR/"; then
      # restore backup on failure
      rm -rf "$MATTERMOST_DIR"
      if [[ -n "${BACKUP_DIR:-}" && -d "$BACKUP_DIR" ]]; then
        mv "$BACKUP_DIR" "$MATTERMOST_DIR"
      fi
      rm -rf "$tmp_dir" "$tmp_tar"
      error "Failed to copy Mattermost files into $MATTERMOST_DIR"
    fi
    # Basic validation: ensure mattermost binary exists and is ELF
    if [[ ! -x "$MATTERMOST_DIR/bin/mattermost" ]]; then
      rm -rf "$MATTERMOST_DIR"
      if [[ -n "${BACKUP_DIR:-}" && -d "$BACKUP_DIR" ]]; then
        mv "$BACKUP_DIR" "$MATTERMOST_DIR"
      fi
      rm -rf "$tmp_dir" "$tmp_tar"
      error "Installed Mattermost binary missing or not executable after installation"
    fi
    rm -rf "$tmp_dir" "$tmp_tar"
  else
    log "Mattermost already installed at $MATTERMOST_DIR"
  fi

  mkdir -p "$MATTERMOST_DIR/data" "$MATTERMOST_DIR/logs"
  chown -R "$MATTERMOST_USER:$MATTERMOST_USER" "$MATTERMOST_DIR"

  local cfg_path="$MATTERMOST_DIR/config/config.json"
  if [[ -f "$cfg_path" ]]; then
    python3 - "$cfg_path" "$MATTERMOST_DB_USER" "$MATTERMOST_DB_PASSWORD" "$MATTERMOST_DB_NAME" <<'PY'
import json
import sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
db_user = sys.argv[2]
db_password = sys.argv[3]
db_name = sys.argv[4]

cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
sql = cfg.setdefault("SqlSettings", {})
changed = False

dsn = f"postgres://{db_user}:{db_password}@127.0.0.1:5432/{db_name}?sslmode=disable&connect_timeout=10"
if sql.get("DriverName") != "postgres":
    sql["DriverName"] = "postgres"
    changed = True
if sql.get("DataSource") != dsn:
    sql["DataSource"] = dsn
    changed = True
if sql.get("DataSourceReplicas"):
    sql["DataSourceReplicas"] = []
    changed = True
if sql.get("DataSourceSearchReplicas"):
    sql["DataSourceSearchReplicas"] = []
    changed = True
if sql.get("UseExperimentalGorm"):
    sql["UseExperimentalGorm"] = False
    changed = True

service = cfg.setdefault("ServiceSettings", {})
if not service.get("ListenAddress"):
    service["ListenAddress"] = ":8065"
    changed = True
# Set SiteURL to internal network gateway for Azazel-Pi
if service.get("SiteURL") != "http://172.16.0.254:8065":
    service["SiteURL"] = "http://172.16.0.254:8065"
    changed = True

if changed:
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
PY
    chown "$MATTERMOST_USER:$MATTERMOST_USER" "$cfg_path"
    log "Mattermost configured to use PostgreSQL at 127.0.0.1:5432."
  else
    log "Mattermost config ($cfg_path) not found; skipping database configuration."
  fi
}

configure_nginx() {
  if [[ ! -f "$REPO_ROOT/deploy/nginx.conf" ]]; then
    return
  fi

  log "Deploying Nginx reverse proxy configuration"
  install -m 644 "$REPO_ROOT/deploy/nginx.conf" /etc/nginx/nginx.conf
  if nginx -t >/dev/null 2>&1; then
    systemctl enable nginx
    systemctl restart nginx
  else
    error "nginx configuration validation failed; please review /etc/nginx/nginx.conf"
  fi
}

configure_internal_network() {
  log "Configuring internal network (AP interface: ${AZAZEL_LAN_IF:-wlan0} — WAN interface: ${AZAZEL_WAN_IF:-wlan1})"
  
  # Run the unified wireless setup script
  if [[ -x "$REPO_ROOT/scripts/setup_wireless.sh" ]]; then
  log "Running setup_wireless.sh for AP configuration (AP: ${AZAZEL_LAN_IF:-wlan0})"
    "$REPO_ROOT/scripts/setup_wireless.sh" --ap-only --skip-confirm || {
      log "ERROR: Wireless setup script failed; manual configuration required"
      return 1
    }
  else
    log "ERROR: setup_wireless.sh not found at $REPO_ROOT/scripts/setup_wireless.sh"
    log "Please run: sudo $REPO_ROOT/scripts/setup_wireless.sh --ap-only"
    return 1
  fi
}

 

APT_PACKAGES=(
  curl
  docker.io
  docker-compose
  gnupg
  git
  iptables-persistent
  jq
  moreutils
  netfilter-persistent
  nginx
  python3
  python3-flask
  python3-pip
  python3-toml
  python3-venv
  python3-yaml
  rsync
  suricata
  suricata-update
)

log "Updating apt repositories"
export DEBIAN_FRONTEND=noninteractive

if [[ ${DRY_RUN:-0} -eq 1 ]]; then
  log "DRY RUN: installer would perform the following actions (no changes will be made):"
  cat <<-DRY
  - Verify OS and dependencies
  - Install APT packages: ${APT_PACKAGES[*]}
  - Install or enable Vector, OpenCanary, Mattermost and Azazel systemd units
  - Stage runtime files to $TARGET_ROOT and configs to $CONFIG_ROOT
  - Ensure /var/log/azazel exists and set permissions
  - Enable and start azctl-unified.service (if present)
  - Optionally start azctl-unified.service if --start supplied
DRY
  exit 0
fi

apt-get update -qq

log "Installing base packages: ${APT_PACKAGES[*]}"
apt-get install -yqq "${APT_PACKAGES[@]}"

# Textual TUI dependency (Azazel-Zero port). Prefer pip for broader distro compatibility.
if ! python3 -c "import textual" >/dev/null 2>&1; then
  log "Installing Python dependency: textual"
  pip3 install -q 'textual>=0.58.0' || log "Failed to install textual; menu TUI may be unavailable"
fi

if ! command -v vector >/dev/null 2>&1; then
  log "Vector not found. Installing via official repo (signed-by), with tarball fallback."

  # Determine architecture for repo and fallback tarball
  ARCH="$(dpkg --print-architecture)"
  case "$ARCH" in
    amd64)  VEC_DEB_ARCH="amd64";  TARBALL_ARCH="x86_64-unknown-linux-gnu" ;;
    arm64)  VEC_DEB_ARCH="arm64";  TARBALL_ARCH="aarch64-unknown-linux-gnu" ;;
    *) error "Unsupported architecture for Vector: $ARCH";;
  esac

  # Install repo key (dearmor) and add APT source
  mkdir -p /usr/share/keyrings
  if curl -1sLf 'https://packages.timber.io/vector/gpg.key' | gpg --dearmor -o /usr/share/keyrings/vector-archive-keyring.gpg; then
    echo "deb [arch=${VEC_DEB_ARCH} signed-by=/usr/share/keyrings/vector-archive-keyring.gpg] https://packages.timber.io/vector/deb stable main" > /etc/apt/sources.list.d/vector.list
    if apt-get update -qq && apt-get install -yqq vector; then
      log "Vector installed via APT repository."
    else
      log "APT install of Vector failed. Falling back to tarball method."
      FALLBACK=1
    fi
  else
    log "Failed to retrieve Vector repo key (DNS or network issue). Falling back to tarball method."
    FALLBACK=1
  fi

  if [[ "${FALLBACK:-0}" -eq 1 ]]; then
    # Minimal tarball-based install
    VECTOR_VERSION="${VECTOR_VERSION:-0.39.0}"
    TARBALL_URL="https://packages.timber.io/vector/${VECTOR_VERSION}/vector-${VECTOR_VERSION}-${TARBALL_ARCH}.tar.gz"
    TMP_TGZ="/tmp/vector-${VECTOR_VERSION}.tar.gz"
    TMP_DIR="/tmp/vector-${VECTOR_VERSION}"

    log "Downloading Vector tarball: $TARBALL_URL"
    if curl -fsSL --retry 3 --retry-connrefused -o "$TMP_TGZ" "$TARBALL_URL"; then
      mkdir -p "$TMP_DIR"
      tar -xzf "$TMP_TGZ" -C "$TMP_DIR" --strip-components=0
      # Find the binary path within the extracted tree
      if install -m 0755 "$(find "$TMP_DIR" -type f -path '*/bin/vector' | head -n1)" /usr/local/bin/vector; then
        log "Installed /usr/local/bin/vector from tarball."
        # Create a simple systemd unit if missing
        if [[ ! -f /etc/systemd/system/vector.service ]]; then
          cat >/etc/systemd/system/vector.service <<'UNIT'
[Unit]
Description=Vector observability agent
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/bin/sh -c "/usr/local/bin/vector --config /etc/azazel/vector/vector.toml || /usr/bin/vector --config /etc/azazel/vector/vector.toml"
Restart=always
RestartSec=5s
User=root
Group=root
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
UNIT
          log "Installed systemd unit for Vector."
        fi
        mkdir -p /etc/vector
        systemctl daemon-reload
        systemctl enable vector
        log "Vector (tarball) installed and enabled. Provide /etc/vector/vector.toml before starting."
      else
        error "Failed to install Vector binary from tarball."
      fi
    else
      error "Failed to download Vector tarball from $TARBALL_URL. Check DNS/connectivity."
    fi
  fi
fi

log "Configuring OpenCanary Docker deployment"
OPEN_CANARY_CONFIG_DIR="/opt/azazel/config"
mkdir -p "$OPEN_CANARY_CONFIG_DIR" /opt/azazel/logs
chmod 755 /opt/azazel/logs || true

if [[ -f "$REPO_ROOT/deploy/opencanary.conf" ]]; then
  install -m 0644 "$REPO_ROOT/deploy/opencanary.conf" "$OPEN_CANARY_CONFIG_DIR/opencanary.conf"
  log "Installed OpenCanary config at $OPEN_CANARY_CONFIG_DIR/opencanary.conf"
else
  warn "deploy/opencanary.conf not found; create $OPEN_CANARY_CONFIG_DIR/opencanary.conf manually"
fi

log "Staging Azazel runtime under $TARGET_ROOT"
mkdir -p "$TARGET_ROOT" "$CONFIG_ROOT"
# Copy current package layout (azazel_pi) and azctl CLI into target runtime
rsync -a --delete "$REPO_ROOT/azazel_pi" "$REPO_ROOT/azctl" "$REPO_ROOT/azazel_web" "$TARGET_ROOT/"
rsync -a "$REPO_ROOT/configs/" "$CONFIG_ROOT/"
rsync -a "$REPO_ROOT/systemd/" /etc/systemd/system/

# Install E-Paper default environment file if present
if [[ -f "$REPO_ROOT/deploy/azazel-epd.default" ]]; then
  install -D -m 0644 "$REPO_ROOT/deploy/azazel-epd.default" /etc/default/azazel-epd
fi

# Ensure runtime log directory exists so services that write decisions won't fail
mkdir -p /var/log/azazel
chmod 755 /var/log/azazel || true

install -m 755 "$REPO_ROOT/scripts/nft_apply.sh" "$TARGET_ROOT/nft_apply.sh"
install -m 755 "$REPO_ROOT/scripts/tc_reset.sh" "$TARGET_ROOT/tc_reset.sh"
install -m 755 "$REPO_ROOT/scripts/sanity_check.sh" "$TARGET_ROOT/sanity_check.sh"
install -m 755 "$REPO_ROOT/scripts/rollback.sh" "$TARGET_ROOT/rollback.sh"

systemctl daemon-reload
# Enable and start the unified control daemon if present. Don't fail the
# installer if the unit isn't available for some reason.
if systemctl list-unit-files | grep -q '^azctl-unified.service'; then
  systemctl enable --now azctl-unified.service || log "Failed to enable/start azctl-unified.service; continue"
fi
if systemctl list-unit-files | grep -q '^azazel-web.service'; then
  systemctl enable --now azazel-web.service || log "Failed to enable/start azazel-web.service; continue"
fi
configure_internal_network
install_mattermost
# Note: azctl.target is no longer used - azctl-unified.service handles all control
systemctl enable mattermost.service
configure_nginx

# Ensure docker is running and enabled (PostgreSQL runs in Docker)
if command -v docker >/dev/null 2>&1; then
  log "Enabling and starting Docker"
  systemctl enable --now docker
  usermod -aG docker "${SUDO_USER:-$USER}"
  
  # Prepare Docker compose config under /opt/azazel/config
  mkdir -p "$TARGET_ROOT/config"
  if [[ -f "$REPO_ROOT/deploy/docker-compose.yml" ]]; then
    install -m 644 "$REPO_ROOT/deploy/docker-compose.yml" "$TARGET_ROOT/config/docker-compose.yml"
  fi
  cat >"$TARGET_ROOT/config/.env" <<ENV
MATTERMOST_DB_NAME=${MATTERMOST_DB_NAME}
MATTERMOST_DB_USER=${MATTERMOST_DB_USER}
MATTERMOST_DB_PASSWORD=${MATTERMOST_DB_PASSWORD}
ENV
  chmod 600 "$TARGET_ROOT/config/.env"

  mkdir -p /opt/azazel/data/postgres
  chown 999:999 /opt/azazel/data/postgres || true

  # Launch docker-compose (prefer docker-compose binary, fallback to `docker compose`)
  if command -v docker-compose >/dev/null 2>&1; then
    log "Starting PostgreSQL via docker-compose"
    (cd "$TARGET_ROOT/config" && docker-compose --project-name azazel-db up -d) || log "docker-compose up returned non-zero exit code"
  else
    log "Starting PostgreSQL via 'docker compose'"
    (cd "$TARGET_ROOT/config" && docker compose --project-name azazel-db up -d) || log "docker compose up returned non-zero exit code"
  fi
else
  log "Docker not found; skipping PostgreSQL container setup."
fi

if systemctl list-unit-files | grep -q '^mattermost.service'; then
  log "Restarting Mattermost service so it connects to PostgreSQL"
  systemctl restart mattermost.service || log "Mattermost restart failed; verify PostgreSQL connectivity."
fi

log "Installer complete. Review /etc/azazel/azazel.yaml before starting services."

if (( START_SERVICES )); then
  log "Starting azctl-unified.service"
  systemctl start azctl-unified.service
fi

log "Next steps:" 
log "  * Adjust Suricata, Vector, and Mattermost configs under /etc/azazel and /opt/mattermost; edit /opt/azazel/config/opencanary.conf for honeypot settings"
log "  * Configure Mattermost webhooks at http://172.16.0.254:8065 (internal network gateway)"
log "  * Update webhook URLs in /etc/azazel/monitoring/notify.yaml to match your Mattermost setup"
log "  * Run 'systemctl restart azctl-unified.service' after making Azazel changes"
log "  * Use scripts/sanity_check.sh plus 'systemctl status mattermost nginx docker' to verify services"
LAN_IF=${AZAZEL_LAN_IF:-wlan0}
WAN_IF=${AZAZEL_WAN_IF:-wlan1}
log "  * Internal network (172.16.0.0/24) is accessible via ${LAN_IF} AP, external via ${WAN_IF}"
