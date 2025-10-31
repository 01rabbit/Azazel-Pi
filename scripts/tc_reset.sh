#!/usr/bin/env bash
set -euo pipefail

IFACE=${1:-wlan1}

tc qdisc del dev "$IFACE" root 2>/dev/null || true
tc qdisc add dev "$IFACE" root handle 1: htb default 30
