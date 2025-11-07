#!/usr/bin/env bash
# bin/azazel-traffic-init.sh
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "+ $*"
  else
    eval "$@"
  fi
}

CFG="${1:-configs/network/azazel.yaml}"

# Validate dependencies
for cmd in tc nft; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "missing command: $cmd" >&2; exit 1; }
done
if ! command -v yq >/dev/null 2>&1; then
  if [[ "$DRY_RUN" != "1" ]]; then
    echo "missing command: yq" >&2; exit 1;
  fi
fi

if command -v yq >/dev/null 2>&1; then
  WAN_IF=$(yq -r '.wan_iface' "$CFG")
else
  WAN_IF="eth0"
fi
[[ -n "$WAN_IF" && "$WAN_IF" != "null" ]] || { echo "wan_iface missing in $CFG" >&2; exit 1; }

# HTB root qdisc (idempotent replace)
run tc qdisc replace dev "$WAN_IF" root handle 1: htb default 30

# Create classes and filters mapping fwmark -> classid
for CLASS in premium standard best_effort restricted; do
  MARK=$(yq -r ".mark_map.${CLASS}" "$CFG" 2>/dev/null || echo "0x10")
  RATE=$(yq -r ".classes.${CLASS}.rate_kbps" "$CFG" 2>/dev/null || echo "10000")kbit
  CEIL=$(yq -r ".classes.${CLASS}.ceil_kbps" "$CFG" 2>/dev/null || echo "10000")kbit
  case "$CLASS" in
    premium)   CID=10 ;;
    standard)  CID=20 ;;
    best_effort) CID=30 ;;
    restricted) CID=40 ;;
  esac
  run tc class replace dev "$WAN_IF" parent 1: classid 1:${CID} htb rate "$RATE" ceil "$CEIL"
  # IPv4/IPv6 fwmark filters
  run tc filter replace dev "$WAN_IF" parent 1: protocol ip   handle "$MARK" fw flowid 1:${CID}
  run tc filter replace dev "$WAN_IF" parent 1: protocol ipv6 handle "$MARK" fw flowid 1:${CID}
done

# nftables table and sets
run nft list table inet azazel >/dev/null 2>&1 || run nft add table inet azazel
run nft delete chain inet azazel prerouting 2>/dev/null || true
run nft add chain inet azazel prerouting '{ type filter hook prerouting priority mangle; }'
run nft delete set inet azazel v4ipmac 2>/dev/null || true
run nft add set inet azazel v4ipmac '{ type ipv4_addr . ether_addr : mark; }'
run nft delete set inet azazel v4priv 2>/dev/null || true
run nft add set inet azazel v4priv '{ type ipv4_addr; flags interval; }'

echo "initialized"
