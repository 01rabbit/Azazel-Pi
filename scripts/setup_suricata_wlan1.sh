#!/usr/bin/env bash
# DEPRECATED: Use setup_wireless.sh instead
set -euo pipefail
printf '\033[1;33m[wireless]\033[0m This script is deprecated. Use:\n' >&2
printf '  sudo scripts/setup_wireless.sh --suricata-only\n' >&2
exit 1
