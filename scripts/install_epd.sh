#!/usr/bin/env bash
# DEPRECATED: E-Paper setup has been integrated into install_azazel_complete.sh
# Replacement: sudo scripts/install_azazel_complete.sh --enable-epd [--epd-emulate]

set -euo pipefail
printf '\033[1;33m[epd-setup]\033[0m This script is deprecated. Use:\n' >&2
printf '  sudo scripts/install_azazel_complete.sh --enable-epd [--epd-emulate]\n' >&2
exit 1
