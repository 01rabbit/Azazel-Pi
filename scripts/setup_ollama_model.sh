#!/usr/bin/env bash
# DEPRECATED: Use setup_ollama_unified.sh instead
set -euo pipefail
printf '\033[1;33m[ollama]\033[0m This script is deprecated. Use:\n' >&2
printf '  sudo scripts/setup_ollama_unified.sh --model-only\n' >&2
exit 1
