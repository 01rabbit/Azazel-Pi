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

# Resolve WAN interface in order of precedence:
# 1) Explicit runtime override via WAN_IF_OVERRIDE
# 2) Environment override AZAZEL_WAN_IF
# 3) Configuration value in YAML (requires yq)
# 4) Ask the Python WAN manager helper (get_active_wan_interface)
# 5) Final fallback: ${AZAZEL_WAN_IF:-eth0}

# 1) runtime override
if [[ -n "${WAN_IF_OVERRIDE:-}" ]]; then
  WAN_IF="$WAN_IF_OVERRIDE"
else
  # 2) environment override
  if [[ -n "${AZAZEL_WAN_IF:-}" ]]; then
    WAN_IF="$AZAZEL_WAN_IF"
  else
    # 3) config via yq
    if command -v yq >/dev/null 2>&1; then
      WAN_IF=$(yq -r '.wan_iface' "$CFG" 2>/dev/null || echo "")
    else
      WAN_IF=""
    fi

    # 4) try Python helper if still empty
    if [[ -z "${WAN_IF:-}" || "$WAN_IF" == "null" ]]; then
      if command -v python3 >/dev/null 2>&1; then
        # Use project-installed package if available; fall back silently on error
        PY_IF=$(python3 - <<'PY'
import sys
try:
    from azazel_pi.utils.wan_state import get_active_wan_interface
    iface = get_active_wan_interface()
    if iface:
        sys.stdout.write(iface)
except Exception:
    pass
PY
        2>/dev/null || true)
        if [[ -n "${PY_IF:-}" ]]; then
          WAN_IF="$PY_IF"
        fi
      fi
    fi
  fi
fi

# 5) final fallback — prefer AZAZEL_WAN_IF if set, otherwise fall back to ${AZAZEL_WAN_IF:-eth0}
: ${WAN_IF:=${AZAZEL_WAN_IF:-eth0}}

[[ -n "$WAN_IF" && "$WAN_IF" != "null" ]] || { echo "wan_iface missing in $CFG and no fallback available" >&2; exit 1; }

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
