#!/usr/bin/env bash
set -euo pipefail

## Interface precedence: positional arg -> AZAZEL_WAN_IF env -> fallback ${AZAZEL_WAN_IF:-wlan1}
IFACE=${1:-${AZAZEL_WAN_IF:-wlan1}}

tc qdisc del dev "$IFACE" root 2>/dev/null || true
tc qdisc add dev "$IFACE" root handle 1: htb default 30
