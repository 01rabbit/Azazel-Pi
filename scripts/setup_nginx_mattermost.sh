#!/usr/bin/env bash
# Setup Nginx as a reverse proxy in front of Mattermost (listening on 127.0.0.1:8065)
# - Installs nginx (Debian/Raspberry Pi OS)
# - Deploys azazel-mattermost site config
# - Tests and reloads nginx
#
# Usage:
#   sudo scripts/setup_nginx_mattermost.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo $0" >&2
  exit 1
fi

# Ensure nginx is installed
if ! command -v nginx >/dev/null 2>&1; then
  echo "Installing nginx..."
  apt update
  apt install -y nginx
fi

SITE_NAME="azazel-mattermost"
CONF_SRC="$(pwd)/deploy/nginx-site.conf"
CONF_DST="/etc/nginx/sites-available/${SITE_NAME}.conf"
ENABLED_LINK="/etc/nginx/sites-enabled/${SITE_NAME}.conf"

if [[ ! -f "$CONF_SRC" ]]; then
  echo "Template not found: $CONF_SRC" >&2
  exit 1
fi

# Copy template
install -D -m 0644 "$CONF_SRC" "$CONF_DST"

# Enable site (disable default if present)
if [[ -e /etc/nginx/sites-enabled/default ]]; then
  rm -f /etc/nginx/sites-enabled/default
fi
ln -sf "$CONF_DST" "$ENABLED_LINK"

# Test nginx configuration
nginx -t

# Reload nginx
systemctl enable nginx
systemctl restart nginx

cat <<EOF

Nginx reverse proxy is configured for Mattermost.
- Listen: http://<device-ip>/ (port 80)
- Backend: http://127.0.0.1:8065

If you plan to use HTTPS, consider placing a TLS-enabled server block or Certbot-managed configuration.
Also make sure your firewall allows inbound TCP/80 (and 443 if you enable TLS).
EOF
