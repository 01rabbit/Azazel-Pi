#!/usr/bin/env bash
# bin/azazel-qos-apply.sh
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

CSV="${1:-configs/network/privileged.csv}"
CFG="${CFG:-configs/network/azazel.yaml}"
MODE="${MODE:-verify}"

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

if [[ "$DRY_RUN" == "1" ]]; then
  for cmd in nft ip; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "missing command: $cmd" >&2; exit 1; }
  done
  # yq is optional in DRY_RUN mode, use fallback defaults
  if command -v yq >/dev/null 2>&1; then
    MARK_PREMIUM=$(yq -r '.mark_map.premium' "$CFG")
    LAN_IF=$(yq -r '.lan_iface' "$CFG")
  else
    echo "[DRY_RUN] yq not found, using fallback defaults" >&2
    MARK_PREMIUM="0x10"
    # Allow environment override for LAN interface in DRY_RUN
    # Use the AZAZEL_LAN_IF environment variable when present, otherwise
    # fall back to the historical default (wlan0). This mirrors how the
    # non-DRY_RUN path resolves the LAN interface.
    LAN_IF="${AZAZEL_LAN_IF:-wlan0}"
  fi
else
  for cmd in nft yq ip; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "missing command: $cmd" >&2; exit 1; }
  done
  MARK_PREMIUM=$(yq -r '.mark_map.premium' "$CFG")
  # Prefer environment override, then config
  if [[ -n "${AZAZEL_LAN_IF:-}" ]]; then
    LAN_IF="$AZAZEL_LAN_IF"
  else
    LAN_IF=$(yq -r '.lan_iface' "$CFG")
  fi
fi

# Prepare nftables table/sets so that flushing never fails
ensure_nft_primitives
run nft flush set inet azazel v4ipmac '||' true
run nft flush set inet azazel v4priv '||' true

# Load CSV lines skipping comments/empties
mapfile -t LINES < <(grep -vE '^\s*#' "$CSV" | sed '/^\s*$/d')
for line in "${LINES[@]}"; do
  IFS=',' read -r IP MAC NOTE <<<"$line"
  IP=$(echo "$IP" | xargs); MAC=$(echo "$MAC" | xargs)
  [[ -n "$IP" && -n "$MAC" ]] || continue
  run_nft_block "add element inet azazel v4ipmac { $IP . $MAC }"
  run_nft_block "add element inet azazel v4priv { $IP }"
done

# Rebuild prerouting rules
run nft flush chain inet azazel prerouting '||' true
run nft add rule inet azazel prerouting ip saddr . ether saddr @v4ipmac meta mark set $MARK_PREMIUM

if [[ "$MODE" == "verify" || "$MODE" == "lock" ]]; then
  run nft add rule inet azazel prerouting ip saddr @v4priv meta mark '!=' $MARK_PREMIUM drop
fi

if [[ "$MODE" == "lock" ]]; then
  while IFS=',' read -r IP MAC NOTE; do
    IP=$(echo "$IP" | xargs); MAC=$(echo "$MAC" | xargs)
    [[ -n "$IP" && -n "$MAC" ]] || continue
    run ip neigh replace "$IP" lladdr "$MAC" dev "$LAN_IF" nud permanent '||' true
  done < <(printf "%s\n" "${LINES[@]}")
fi

echo "applied mode=$MODE entries=${#LINES[@]}"
