#!/usr/bin/env bash
# bin/azazel-qos-apply.sh
set -euo pipefail

CSV="${1:-configs/network/privileged.csv}"
CFG="${CFG:-configs/network/azazel.yaml}"
MODE="${MODE:-verify}"

for cmd in nft yq ip; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "missing command: $cmd" >&2; exit 1; }
done

MARK_PREMIUM=$(yq -r '.mark_map.premium' "$CFG")
LAN_IF=$(yq -r '.lan_iface' "$CFG")

# Prepare sets
nft flush set inet azazel v4ipmac || true
nft flush set inet azazel v4priv || true

# Load CSV lines skipping comments/empties
mapfile -t LINES < <(grep -vE '^\s*#' "$CSV" | sed '/^\s*$/d')
for line in "${LINES[@]}"; do
  IFS=',' read -r IP MAC NOTE <<<"$line"
  IP=$(echo "$IP" | xargs); MAC=$(echo "$MAC" | xargs)
  [[ -n "$IP" && -n "$MAC" ]] || continue
  nft add element inet azazel v4ipmac { $IP . $MAC : $MARK_PREMIUM }
  nft add element inet azazel v4priv { $IP }
done

# Rebuild prerouting rules
nft flush chain inet azazel prerouting || true
nft add rule inet azazel prerouting ip saddr . ether saddr @v4ipmac meta mark set $MARK_PREMIUM

if [[ "$MODE" == "verify" || "$MODE" == "lock" ]]; then
  nft add rule inet azazel prerouting ip saddr @v4priv meta mark != $MARK_PREMIUM drop
fi

if [[ "$MODE" == "lock" ]]; then
  while IFS=',' read -r IP MAC NOTE; do
    IP=$(echo "$IP" | xargs); MAC=$(echo "$MAC" | xargs)
    [[ -n "$IP" && -n "$MAC" ]] || continue
    ip neigh replace "$IP" lladdr "$MAC" dev "$LAN_IF" nud permanent || true
  done < <(printf "%s\n" "${LINES[@]}")
fi

echo "applied mode=$MODE entries=${#LINES[@]}"
