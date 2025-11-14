#!/usr/bin/env bash
set -euo pipefail

REQUIRED=(suricata vector)

for svc in "${REQUIRED[@]}"; do
  if ! systemctl is-enabled --quiet "$svc"; then
    echo "[azazel] warning: service $svc is not enabled" >&2
  fi
  if ! systemctl is-active --quiet "$svc"; then
    echo "[azazel] warning: service $svc is not running" >&2
  fi
done

if command -v docker >/dev/null 2>&1; then
  if ! docker ps --format '{{.Names}} {{.Status}}' | grep -q '^azazel_opencanary '; then
    echo "[azazel] warning: container azazel_opencanary is not running" >&2
  fi
else
  echo "[azazel] warning: docker not found; unable to verify azazel_opencanary" >&2
fi
