#!/usr/bin/env bash
# Script to save current iptables rules for persistence
# This ensures NAT and filter rules survive reboots

set -euo pipefail

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2
}

# Check if root privileges
if [[ $EUID -ne 0 ]]; then
    log "ERROR: This script requires root privileges"
    exit 1
fi

log "Saving iptables rules..."

# Create directory for rules if it doesn't exist
mkdir -p /etc/iptables

# Save IPv4 rules
if iptables-save > /etc/iptables/rules.v4; then
    log "SUCCESS: IPv4 rules saved to /etc/iptables/rules.v4"
else
    log "ERROR: Failed to save IPv4 rules"
    exit 1
fi

# If netfilter-persistent is installed, use it
if command -v netfilter-persistent >/dev/null 2>&1; then
    log "Using netfilter-persistent to save rules..."
    netfilter-persistent save || log "WARNING: netfilter-persistent save had issues"
fi

log "Done. Rules will be restored on next boot."
log "To manually restore rules: iptables-restore < /etc/iptables/rules.v4"
