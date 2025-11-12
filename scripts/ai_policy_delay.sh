#!/usr/bin/env bash
# AI-driven traffic delay policy script
# Applies network delay based on AI threat assessment

set -euo pipefail

SRC_IP=${1:?source IP required}
DELAY=${2:-200ms}
# Interface precedence: positional arg -> AZAZEL_WAN_IF env -> fallback ${AZAZEL_WAN_IF:-wlan1}
INTERFACE=${3:-${AZAZEL_WAN_IF:-wlan1}}

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2
}

# Check if IP is valid
if ! [[ $SRC_IP =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
    log "ERROR: Invalid IP address: $SRC_IP"
    exit 1
fi

# Ensure interface exists
if ! ip link show "$INTERFACE" >/dev/null 2>&1; then
    log "ERROR: Interface $INTERFACE not found"
    exit 1
fi

log "Applying delay $DELAY to traffic from $SRC_IP on $INTERFACE"

# Check if root privileges
if [[ $EUID -ne 0 ]]; then
    log "ERROR: This script requires root privileges"
    exit 1
fi

# Clean existing rules for this IP (best effort)
tc filter del dev "$INTERFACE" protocol ip parent 1:0 prio 3 \
  u32 match ip src "$SRC_IP" 2>/dev/null || true

# Ensure basic qdisc structure exists (replace preferred)
tc qdisc replace dev "$INTERFACE" root handle 1: prio 2>/dev/null || {
    log "Creating base qdisc on $INTERFACE"
    existing_qdisc=$(tc qdisc show dev "$INTERFACE" root 2>/dev/null | head -n1 || true)
    if [ -z "${existing_qdisc}" ] || echo "${existing_qdisc}" | grep -qi "noqueue"; then
        tc qdisc add dev "$INTERFACE" root handle 1: prio
    else
        echo "tc qdisc replace failed and interface has existing qdisc; skipping add to avoid RTNETLINK conflicts" >&2
    fi
}

# Create delay qdisc (replace preferred)
tc qdisc replace dev "$INTERFACE" parent 1:3 handle 30: netem delay "$DELAY" 2>/dev/null || {
    log "Creating delay qdisc with $DELAY"
    # Only add if the specific parent/class doesn't already have a qdisc
    parent_qdisc=$(tc qdisc show dev "$INTERFACE" | grep "parent 1:3" || true)
    if [ -z "${parent_qdisc}" ]; then
        tc qdisc add dev "$INTERFACE" parent 1:3 handle 30: netem delay "$DELAY"
    else
        echo "tc qdisc replace failed for parent 1:3 but parent qdisc exists; skipping add to avoid conflicts" >&2
    fi
}

# Apply filter to target specific source IP (use replace to avoid File exists races)
tc filter replace dev "$INTERFACE" protocol ip parent 1:0 prio 3 \
  u32 match ip src "$SRC_IP" flowid 1:3

# Verify the rule was applied
if tc filter show dev "$INTERFACE" | grep -q "$SRC_IP"; then
    log "SUCCESS: Delay $DELAY applied to $SRC_IP on $INTERFACE"
    
    # Optional: Set cleanup timer (5 minutes)
    (
        sleep 300
        tc filter del dev "$INTERFACE" protocol ip parent 1:0 prio 3 \
          u32 match ip src "$SRC_IP" 2>/dev/null || true
        log "Cleanup: Removed delay rule for $SRC_IP"
    ) &
    
    exit 0
else
    log "ERROR: Failed to apply delay rule"
    exit 1
fi