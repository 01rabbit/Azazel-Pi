#!/usr/bin/env bash
# Installer to reproduce current Suricata environment (idempotent-ish).
# Run as root.
set -euo pipefail

# Variables
SURICATA_USER=suricata
SURICATA_HOME=/var/lib/suricata
SURICATA_LOG=/var/log/suricata
RULES_DIR=${SURICATA_HOME}/rules
UPDATE_SCRIPT_PATH=/usr/local/bin/azazel-suricata-update.sh
SYSTEMD_DROPIN_DIR=/etc/systemd/system/suricata.service.d
DROPIN_FILE=${SYSTEMD_DROPIN_DIR}/override-nonroot.conf
TIMER_UNIT=azazel-suricata-update.timer
SERVICE_UNIT=azazel-suricata-update.service

if [ "$EUID" -ne 0 ]; then
  echo "This installer must be run as root." >&2
  exit 2
fi

# 1) Create user
if ! id -u "$SURICATA_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SURICATA_USER"
  echo "Created system user $SURICATA_USER"
else
  echo "User $SURICATA_USER already exists"
fi

# 2) Ensure directories exist and ownership
mkdir -p "$RULES_DIR"
mkdir -p "$SURICATA_LOG"
chown -R ${SURICATA_USER}:${SURICATA_USER} "$SURICATA_HOME" "$SURICATA_LOG"
chmod -R 750 "$SURICATA_HOME"
chmod -R 750 "$SURICATA_LOG"
chmod 755 "$RULES_DIR"

# 3) Create systemd drop-in for non-root execution
mkdir -p "$SYSTEMD_DROPIN_DIR"
cat > "$DROPIN_FILE" <<'EOF'
[Service]
User=suricata
Group=suricata
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN
NoNewPrivileges=no
EOF

systemctl daemon-reload || true

# 4) Install suricata-update wrapper (overwrites if present)
cat > "$UPDATE_SCRIPT_PATH" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
LOG=/var/log/suricata/azazel-suricata-update.log
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

echo "=== azazel suricata-update run: $(date -Iseconds) ==="
# run suricata-update and test config
if ! /usr/bin/suricata-update; then
  echo "suricata-update failed"
  exit 2
fi
# test config
if ! /usr/bin/suricata -T -c /etc/suricata/suricata.yaml; then
  echo "suricata config test failed"
  exit 3
fi
# restart service if everything OK
systemctl restart suricata
echo "suricata update completed at $(date -Iseconds)"
EOF
chmod 755 "$UPDATE_SCRIPT_PATH"
chown root:root "$UPDATE_SCRIPT_PATH"

# 5) Install systemd service + timer units (simple template)
cat > "/etc/systemd/system/${SERVICE_UNIT}" <<'EOF'
[Unit]
Description=Run azazel suricata-update wrapper
RefuseManualStart=no
RefuseManualStop=no

[Service]
Type=oneshot
ExecStart=/usr/local/bin/azazel-suricata-update.sh

# If this service fails, run failure handler
OnFailure=azazel-suricata-update-failure@%n.service
EOF

cat > "/etc/systemd/system/${TIMER_UNIT}" <<'EOF'
[Unit]
Description=Daily timer for azazel suricata-update

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF

# 6) Failure handler unit
cat > "/etc/systemd/system/azazel-suricata-update-failure@.service" <<'EOF'
[Unit]
Description=Handle suricata-update failure

[Service]
Type=oneshot
ExecStart=/bin/sh -c '/bin/logger -t azazel-suricata-update "suricata-update failed on %i"; echo "suricata-update failed on %i at $(date)" >> /var/log/suricata/azazel-suricata-update-failure.log'

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now ${TIMER_UNIT} || true

# 7) Install logrotate for update log
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

# 8) Copy repository local.rules to runtime rules dir if present
if [ -f "$(pwd)/configs/suricata/local.rules" ]; then
  cp "$(pwd)/configs/suricata/local.rules" "$RULES_DIR/local.rules"
  chown ${SURICATA_USER}:${SURICATA_USER} "$RULES_DIR/local.rules"
  chmod 0640 "$RULES_DIR/local.rules"
  echo "Deployed local.rules"
fi

# 9) Final: reload and restart suricata
systemctl daemon-reload

# Ensure runtime directory for unix socket exists with correct ownership so
# the non-root suricata user can create the command socket there.
mkdir -p /run/suricata
chown ${SURICATA_USER}:${SURICATA_USER} /run/suricata
chmod 0755 /run/suricata

systemctl restart suricata

# 10) Vector log shipper (vector) 設定・ディレクトリ作成・サービス再起動
VECTOR_CONFIG_DIR="/etc/azazel/vector"
VECTOR_CONFIG_FILE="${VECTOR_CONFIG_DIR}/vector.toml"
VECTOR_DATA_DIR="/var/lib/vector"
mkdir -p "$VECTOR_CONFIG_DIR"
mkdir -p "$VECTOR_DATA_DIR"
cat > "$VECTOR_CONFIG_FILE" <<'EOF'
[sources.syslog]
type = "file"
include = ["/var/log/syslog"]

[transforms.parse_syslog]
type = "syslog_parser"
inputs = ["syslog"]

[sinks.local_file]
type = "file"
inputs = ["parse_syslog"]
path = "/var/lib/vector/syslog.log"
encoding.codec = "text"
EOF
chown root:root "$VECTOR_CONFIG_FILE"
chmod 644 "$VECTOR_CONFIG_FILE"
chown root:root "$VECTOR_DATA_DIR"
chmod 755 "$VECTOR_DATA_DIR"
if systemctl list-unit-files | grep -q '^vector.service'; then
  systemctl restart vector.service || true
fi

# 11) Dockerメモリ制限設定
DOCKER_CONFIG_FILE="/etc/docker/daemon.json"
cat > "$DOCKER_CONFIG_FILE" <<'EOF'
{
  "default-runtime": "runc",
  "runtimes": {"runc": {"path": "runc"}},
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"},
  "default-ulimits": {"memlock": {"Name": "memlock", "Hard": 524288000, "Soft": 524288000}}
}
EOF
chown root:root "$DOCKER_CONFIG_FILE"
chmod 644 "$DOCKER_CONFIG_FILE"
if systemctl list-unit-files | grep -q '^docker.service'; then
  systemctl restart docker.service || true
fi

# 12) azazel関連サービスの有効化
if systemctl list-unit-files | grep -q '^azctl-unified.service'; then
  systemctl enable azctl-unified.service || true
  systemctl restart azctl-unified.service || true
fi

cat <<EOF
Installer finished. Verify with:
  systemctl status suricata
  journalctl -u suricata -n 50
  ls -l /var/lib/suricata/rules
EOF
