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

log "Blocking traffic from $SRC_IP for ${DURATION}s using nftables"

# Create table and chain if not exists
nft add table inet "$TABLE_NAME" 2>/dev/null || true
nft add chain inet "$TABLE_NAME" input '{ type filter hook input priority 0; }' 2>/dev/null || true

# Remove existing rule for this IP (if any)
nft delete rule inet "$TABLE_NAME" input ip saddr "$SRC_IP" drop 2>/dev/null || true

# Add blocking rule
if nft add rule inet "$TABLE_NAME" input ip saddr "$SRC_IP" drop; then
    log "SUCCESS: Blocked $SRC_IP via nftables"
    
    # Optional: Set cleanup timer
    if [[ "$DURATION" -gt 0 ]]; then
        (
            sleep "$DURATION"
            nft delete rule inet "$TABLE_NAME" input ip saddr "$SRC_IP" drop 2>/dev/null || true
            log "Cleanup: Removed block rule for $SRC_IP"
        ) &
    fi
    
    exit 0
else
    log "ERROR: Failed to block $SRC_IP"
    exit 1
fi