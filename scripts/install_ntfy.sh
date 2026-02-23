#!/usr/bin/env bash
# Install and configure ntfy server for Azazel-Edge

set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "ERROR: run as root" >&2
  exit 1
fi

MGMT_IP="${MGMT_IP:-10.55.0.10}"
NTFY_PORT="${NTFY_PORT:-8081}"
NTFY_USER="${NTFY_USER:-azazel-notify}"
TOPIC_ALERT="${NTFY_TOPIC_ALERT:-azg-alert-critical}"
TOPIC_INFO="${NTFY_TOPIC_INFO:-azg-info-status}"

SERVER_CFG="/etc/ntfy/server.yml"
TOKEN_PATH="/etc/azazel/ntfy.token"

echo "[ntfy] Installing package..."
apt-get update -y >/dev/null
apt-get install -y ntfy curl >/dev/null

mkdir -p /etc/azazel /var/lib/ntfy /var/cache/ntfy
if id -u _ntfy >/dev/null 2>&1; then
  chown _ntfy:_ntfy /var/lib/ntfy /var/cache/ntfy
fi
chmod 0750 /var/lib/ntfy /var/cache/ntfy

if [[ -f "$SERVER_CFG" ]] && [[ ! -f "${SERVER_CFG}.azazel.bak" ]]; then
  cp "$SERVER_CFG" "${SERVER_CFG}.azazel.bak"
fi

cat > "$SERVER_CFG" <<EOF
# Managed by Azazel installer (scripts/install_ntfy.sh)
base-url: "http://${MGMT_IP}:${NTFY_PORT}"
listen-http: ":${NTFY_PORT}"
cache-file: "/var/cache/ntfy/cache.db"
auth-file: "/var/lib/ntfy/user.db"
auth-default-access: "read-write"
behind-proxy: false
web-root: "/"
EOF

systemctl daemon-reload
systemctl restart ntfy.service

for _ in {1..20}; do
  if [[ -f /var/lib/ntfy/user.db ]]; then
    break
  fi
  sleep 0.2
done
if [[ ! -f /var/lib/ntfy/user.db ]]; then
  echo "ERROR: ntfy auth DB was not created: /var/lib/ntfy/user.db" >&2
  exit 1
fi

ntfy_password="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
if ! NTFY_PASSWORD="$ntfy_password" ntfy user add "$NTFY_USER" >/dev/null 2>&1; then
  NTFY_PASSWORD="$ntfy_password" ntfy user change-pass "$NTFY_USER" >/dev/null 2>&1 || true
fi

ntfy access "$NTFY_USER" "$TOPIC_ALERT" write-only >/dev/null 2>&1
ntfy access "$NTFY_USER" "$TOPIC_INFO" write-only >/dev/null 2>&1
ntfy access everyone "$TOPIC_ALERT" read-write >/dev/null 2>&1
ntfy access everyone "$TOPIC_INFO" read-write >/dev/null 2>&1

token_output="$(ntfy token add "$NTFY_USER" 2>&1)"
token=""
if [[ "$token_output" =~ (tk_[a-z0-9]+) ]]; then
  token="${BASH_REMATCH[1]}"
fi
if [[ -z "$token" ]]; then
  echo "ERROR: failed to create ntfy token" >&2
  exit 1
fi

umask 077
printf '%s\n' "$token" > "$TOKEN_PATH"
chown root:root "$TOKEN_PATH"
chmod 0600 "$TOKEN_PATH"

systemctl enable ntfy.service >/dev/null
systemctl restart ntfy.service

for _ in {1..20}; do
  if ss -ltnH 2>/dev/null | grep -Eq ":${NTFY_PORT}[[:space:]]"; then
    if curl -fsS --max-time 3 "http://${MGMT_IP}:${NTFY_PORT}/v1/health" | grep -q '"healthy":true'; then
      echo "[ntfy] Service is listening on TCP/${NTFY_PORT}"
      echo "[ntfy] Health endpoint OK: http://${MGMT_IP}:${NTFY_PORT}/v1/health"
      echo "[ntfy] Setup complete. token file: ${TOKEN_PATH}"
      exit 0
    fi
  fi
  sleep 0.25
done

echo "ERROR: ntfy did not pass TCP/health checks on ${MGMT_IP}:${NTFY_PORT}" >&2
exit 1
