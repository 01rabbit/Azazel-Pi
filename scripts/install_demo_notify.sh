#!/usr/bin/env bash
# Install demo notify config (back up existing configs/monitoring/notify.yaml -> notify.yaml.bak)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEMO_CFG="$REPO_ROOT/configs/monitoring/notify_demo.yaml"
TARGET_CFG="$REPO_ROOT/configs/monitoring/notify.yaml"
BACKUP="$TARGET_CFG.bak"

if [ ! -f "$DEMO_CFG" ]; then
  echo "Demo config not found: $DEMO_CFG"
  exit 1
fi

if [ -f "$TARGET_CFG" ] && [ ! -f "$BACKUP" ]; then
  echo "Backing up existing notify.yaml -> notify.yaml.bak"
  cp "$TARGET_CFG" "$BACKUP"
fi

cp "$DEMO_CFG" "$TARGET_CFG"
chmod 644 "$TARGET_CFG"

echo "Demo notify.yaml installed to $TARGET_CFG"

echo "Remember: edit $TARGET_CFG and set 'webhook_url' to your TEST webhook before running the demo."
