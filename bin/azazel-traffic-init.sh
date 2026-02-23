#!/usr/bin/env bash
# bin/azazel-traffic-init.sh
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "+ $*"
  else
    local args=("$@")
    local argc=${#args[@]}
    if (( argc >= 2 )); then
      local guard_idx=$((argc - 2))
      local fallback_idx=$((argc - 1))
      if [[ "${args[$guard_idx]}" == "||" ]]; then
        local fallback="${args[$fallback_idx]}"
        unset "args[$fallback_idx]"
        unset "args[$guard_idx]"
        args=("${args[@]}")
        if "${args[@]}"; then
          return 0
        fi
        eval "$fallback"
        return $?
      fi
    fi
    "${args[@]}"
  fi
}

run_nft_block() {
  local snippet="$1"
  if [[ "$DRY_RUN" == "1" ]]; then
    printf "+ nft -f - <<'EOF'\n%s\nEOF\n" "$snippet"
    return 0
  fi
  nft -f - <<<"$snippet"
}

CFG="${1:-configs/network/azazel.yaml}"

# Flag indicating the target interface fundamentally cannot host a root qdisc.
SKIP_TC_SETUP=0

ensure_htb_root_qdisc() {
  if run tc qdisc replace dev "$WAN_IF" root handle 1: htb default 30; then
    return 0
  fi

  local existing_qdisc
  existing_qdisc=$(tc qdisc show dev "$WAN_IF" root 2>/dev/null | head -n1 || true)
  echo "tc replace failed on ${WAN_IF} (existing: ${existing_qdisc:-unknown}), retrying with delete/add" >&2

  run tc qdisc del dev "$WAN_IF" root '||' true
    if [ -z "${existing_qdisc}" ] || echo "${existing_qdisc}" | grep -qi "noqueue"; then
      # no existing root qdisc, try add
      if run tc qdisc add dev "$WAN_IF" root handle 1: htb default 30; then
        return 0
      else
        echo "failed to create qdisc on ${WAN_IF}" >&2
      fi
    else
      echo "tc replace failed on ${WAN_IF} (existing: ${existing_qdisc:-unknown}), skipping add to avoid RTNETLINK conflicts" >&2
    fi

  existing_qdisc=$(tc qdisc show dev "$WAN_IF" root 2>/dev/null | head -n1 || true)
  if [[ "$existing_qdisc" == *"noqueue"* ]]; then
    echo "Interface ${WAN_IF} reports noqueue root qdisc; skipping tc class configuration" >&2
    SKIP_TC_SETUP=1
    return 0
  fi

  echo "Failed to program HTB root qdisc on ${WAN_IF} (existing: ${existing_qdisc:-unknown})" >&2
  return 1
}

ensure_nft_primitives() {
  if ! nft list table inet azazel >/dev/null 2>&1; then
    run nft add table inet azazel
  fi
  if ! nft list chain inet azazel prerouting >/dev/null 2>&1; then
    run_nft_block "add chain inet azazel prerouting { type filter hook prerouting priority mangle; }"
  fi
  if ! nft list set inet azazel v4ipmac >/dev/null 2>&1; then
    run_nft_block "add set inet azazel v4ipmac { type ipv4_addr . ether_addr; }"
  fi
  if ! nft list set inet azazel v4priv >/dev/null 2>&1; then
    run_nft_block "add set inet azazel v4priv { type ipv4_addr; flags interval; }"
  fi
}

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
    from azazel_edge.utils.wan_state import get_active_wan_interface
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

# HTB root qdisc (idempotent with fallback)
ensure_htb_root_qdisc

if [[ "$SKIP_TC_SETUP" != "1" ]]; then
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
else
  echo "Skipping tc class/filter creation because ${WAN_IF} cannot host HTB root qdisc" >&2
fi

# nftables table and sets
ensure_nft_primitives
run nft delete chain inet azazel prerouting 2>/dev/null || true
run_nft_block "add chain inet azazel prerouting { type filter hook prerouting priority mangle; }"
run nft delete set inet azazel v4ipmac 2>/dev/null || true
run_nft_block "add set inet azazel v4ipmac { type ipv4_addr . ether_addr; }"
run nft delete set inet azazel v4priv 2>/dev/null || true
run_nft_block "add set inet azazel v4priv { type ipv4_addr; flags interval; }"

echo "initialized"
