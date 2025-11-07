#!/usr/bin/env bash
# bin/azazel-traffic-init.sh
set -euo pipefail

CFG="${1:-configs/network/azazel.yaml}"

# Validate dependencies
for cmd in tc nft yq; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "missing command: $cmd" >&2; exit 1; }
done

WAN_IF=$(yq -r '.wan_iface' "$CFG")
[[ -n "$WAN_IF" && "$WAN_IF" != "null" ]] || { echo "wan_iface missing in $CFG" >&2; exit 1; }

# HTB root qdisc (idempotent replace)
tc qdisc replace dev "$WAN_IF" root handle 1: htb default 30 || true

# Create classes and filters mapping fwmark -> classid
for CLASS in premium standard best_effort restricted; do
  MARK=$(yq -r ".mark_map.${CLASS}" "$CFG")
  RATE=$(yq -r ".classes.${CLASS}.rate_kbps" "$CFG")kbit
  CEIL=$(yq -r ".classes.${CLASS}.ceil_kbps" "$CFG")kbit
  case "$CLASS" in
    premium)   CID=10 ;;
    standard)  CID=20 ;;
    best_effort) CID=30 ;;
    restricted) CID=40 ;;
  esac
  tc class replace dev "$WAN_IF" parent 1: classid 1:${CID} htb rate "$RATE" ceil "$CEIL" || true
  # IPv4/IPv6 fwmark filters
  tc filter replace dev "$WAN_IF" parent 1: protocol ip   handle "$MARK" fw flowid 1:${CID} || true
  tc filter replace dev "$WAN_IF" parent 1: protocol ipv6 handle "$MARK" fw flowid 1:${CID} || true
done

# nftables table and sets
nft list table inet azazel >/dev/null 2>&1 || nft add table inet azazel
nft delete chain inet azazel prerouting 2>/dev/null || true
nft add chain inet azazel prerouting '{ type filter hook prerouting priority mangle; }' || true
nft delete set inet azazel v4ipmac 2>/dev/null || true
nft add set inet azazel v4ipmac '{ type ipv4_addr . ether_addr : mark; }' || true
nft delete set inet azazel v4priv 2>/dev/null || true
nft add set inet azazel v4priv '{ type ipv4_addr; flags interval; }' || true

echo "initialized"
