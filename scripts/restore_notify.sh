#!/usr/bin/env bash
# Restore original notify.yaml if backup exists
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_CFG="$REPO_ROOT/configs/notify.yaml"
BACKUP="$TARGET_CFG.bak"

if [ -f "$BACKUP" ]; then
  mv -f "$BACKUP" "$TARGET_CFG"
  echo "Restored original notify.yaml from backup"
else
  echo "No backup found. Nothing to restore."
fi
