#!/usr/bin/env bash
set -euo pipefail

## Interface precedence: positional arg -> AZAZEL_WAN_IF env -> fallback ${AZAZEL_WAN_IF:-wlan1}
IFACE=${1:-${AZAZEL_WAN_IF:-wlan1}}

tc qdisc del dev "$IFACE" root 2>/dev/null || true
# Use replace to be idempotent; if replace is unsupported, fall back to add
tc qdisc replace dev "$IFACE" root handle 1: htb default 30 2>/dev/null || {
	existing_qdisc=$(tc qdisc show dev "$IFACE" root 2>/dev/null | head -n1 || true)
	if [ -z "${existing_qdisc}" ] || echo "${existing_qdisc}" | grep -qi "noqueue"; then
		tc qdisc add dev "$IFACE" root handle 1: htb default 30
	else
		echo "tc qdisc replace failed and interface has existing qdisc; skipping add to avoid RTNETLINK conflicts" >&2
	fi
}
