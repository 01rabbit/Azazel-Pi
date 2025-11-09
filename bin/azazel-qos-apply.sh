#!/usr/bin/env bash
# bin/azazel-qos-apply.sh
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "+ $*"
  else
    eval "$@"
  fi
}

CSV="${1:-configs/network/privileged.csv}"
CFG="${CFG:-configs/network/azazel.yaml}"
MODE="${MODE:-verify}"

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

# Prepare sets
run nft flush set inet azazel v4ipmac '||' true
run nft flush set inet azazel v4priv '||' true

# Load CSV lines skipping comments/empties
mapfile -t LINES < <(grep -vE '^\s*#' "$CSV" | sed '/^\s*$/d')
for line in "${LINES[@]}"; do
  IFS=',' read -r IP MAC NOTE <<<"$line"
  IP=$(echo "$IP" | xargs); MAC=$(echo "$MAC" | xargs)
  [[ -n "$IP" && -n "$MAC" ]] || continue
  run nft add element inet azazel v4ipmac "{ $IP . $MAC : $MARK_PREMIUM }"
  run nft add element inet azazel v4priv "{ $IP }"
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
