#!/usr/bin/env bash
# Convenience installer that provisions Azazel and its dependencies on Debian-based systems.
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 [--start]

Options:
  --start   Start the azctl.target after provisioning completes.
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
while [[ $# -gt 0 ]]; do
  case "$1" in
    --start)
      START_SERVICES=1
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

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
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

log "Updating apt repositories"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq

APT_PACKAGES=(
  curl
  git
  jq
  moreutils
  netfilter-persistent
  nftables
  python3
  python3-pip
  python3-venv
  python3-yaml
  rsync
  suricata
  suricata-update
)

log "Installing base packages: ${APT_PACKAGES[*]}"
apt-get install -yqq "${APT_PACKAGES[@]}"

if ! command -v vector >/dev/null 2>&1; then
  log "Vector not found. Adding Vector repository and installing."
  curl -1sLf 'https://repositories.timber.io/public/vector/cfg/setup/bash.deb.sh' | bash
  apt-get install -yqq vector
fi

if ! command -v opencanaryd >/dev/null 2>&1; then
  log "Installing OpenCanary via pip"
  PIP_INSTALL=(python3 -m pip install)
  if python3 -m pip help install 2>&1 | grep -q -- '--break-system-packages'; then
    PIP_INSTALL+=(--break-system-packages)
  fi
  "${PIP_INSTALL[@]}" --upgrade pip
  "${PIP_INSTALL[@]}" opencanary scapy
  if [[ -x /usr/local/bin/opencanaryd && ! -e /usr/bin/opencanaryd ]]; then
    ln -s /usr/local/bin/opencanaryd /usr/bin/opencanaryd
  fi
fi

log "Staging Azazel runtime under $TARGET_ROOT"
mkdir -p "$TARGET_ROOT" "$CONFIG_ROOT"
rsync -a --delete "$REPO_ROOT/azazel_core" "$REPO_ROOT/azctl" "$TARGET_ROOT/"
rsync -a "$REPO_ROOT/configs/" "$CONFIG_ROOT/"
rsync -a "$REPO_ROOT/systemd/" /etc/systemd/system/

install -m 755 "$REPO_ROOT/scripts/nft_apply.sh" "$TARGET_ROOT/nft_apply.sh"
install -m 755 "$REPO_ROOT/scripts/tc_reset.sh" "$TARGET_ROOT/tc_reset.sh"
install -m 755 "$REPO_ROOT/scripts/sanity_check.sh" "$TARGET_ROOT/sanity_check.sh"
install -m 755 "$REPO_ROOT/scripts/rollback.sh" "$TARGET_ROOT/rollback.sh"

systemctl daemon-reload
systemctl enable azctl.target

log "Installer complete. Review /etc/azazel/azazel.yaml before starting services."

if (( START_SERVICES )); then
  log "Starting azctl.target"
  systemctl start azctl.target
fi

log "Next steps:" 
log "  * Adjust Suricata, Vector, and OpenCanary configs under /etc/azazel"
log "  * Run 'systemctl restart azctl.target' after making changes"
log "  * Use scripts/sanity_check.sh to verify services"
