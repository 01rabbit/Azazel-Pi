#!/usr/bin/env bash
# AI-driven traffic blocking policy script
# Blocks traffic based on AI threat assessment

set -euo pipefail

SRC_IP=${1:?source IP required}
DURATION=${2:-300}  # Default 5 minutes
TABLE_NAME="azazel_ai"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2
}

# Check if IP is valid
if ! [[ $SRC_IP =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
    log "ERROR: Invalid IP address: $SRC_IP"
    exit 1
fi

# Check if root privileges
if [[ $EUID -ne 0 ]]; then
    log "ERROR: This script requires root privileges"
    exit 1
fi

log "Blocking traffic from $SRC_IP for ${DURATION}s using iptables"

# Create custom chain if not exists
iptables -N "$TABLE_NAME" 2>/dev/null || true

# Link custom chain to INPUT if not already linked
iptables -C INPUT -j "$TABLE_NAME" 2>/dev/null || iptables -I INPUT -j "$TABLE_NAME"

# Remove existing rule for this IP (if any)
iptables -D "$TABLE_NAME" -s "$SRC_IP" -j DROP 2>/dev/null || true

# Add blocking rule
if iptables -A "$TABLE_NAME" -s "$SRC_IP" -j DROP; then
    log "SUCCESS: Blocked $SRC_IP via iptables"
    
    # Optional: Set cleanup timer
    if [[ "$DURATION" -gt 0 ]]; then
        (
            sleep "$DURATION"
            iptables -D "$TABLE_NAME" -s "$SRC_IP" -j DROP 2>/dev/null || true
            log "Cleanup: Removed block rule for $SRC_IP"
        ) &
    fi
    
    exit 0
else
    log "ERROR: Failed to block $SRC_IP"
    exit 1
fi