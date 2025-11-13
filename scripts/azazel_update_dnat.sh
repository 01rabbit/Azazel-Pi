#!/usr/bin/env bash
# Safe helper to update nft DNAT rules for Azazel -> redirect SSH (tcp dport 22)
# to OpenCanary IP and port (default 192.168.1.100:2222).
# Usage (recommended): edit CANARY_IP / CANARY_PORT below if needed, then:
#   sudo cp scripts/azazel_update_dnat.sh /usr/local/sbin/azazel_update_dnat.sh
#   sudo bash /usr/local/sbin/azazel_update_dnat.sh --apply
# Or run interactively (no --apply runs in dry-run mode printing actions).

set -euo pipefail
SCRIPT_NAME=$(basename "$0")
BACKUP_DIR=/tmp/azazel_backup_$(date +%s)
SRC_IP_FILE="$BACKUP_DIR/src_ips.txt"
NFT_BACKUP="$BACKUP_DIR/nft_ruleset_backup.conf"

# Default values (edit this file or pass via env)
CANARY_IP=${CANARY_IP:-192.168.1.100}
CANARY_PORT=${CANARY_PORT:-2222}
NFT_TABLE=${NFT_TABLE:-inet azazel}
PREROUTING_CHAIN=${PREROUTING_CHAIN:-prerouting}

usage(){
  cat <<EOF
$SCRIPT_NAME - safe DNAT updater for Azazel

Options:
  --apply        Actually apply changes. Without this, the script does a a dry-run and prints the commands it would run.
  --canary ip:port  Override CANARY target (e.g. 192.168.1.100:2222)
  --help         Show this help

Steps performed when --apply is provided:
  - backup full nft ruleset to $NFT_BACKUP
  - extract src IPs from $NFT_TABLE $PREROUTING_CHAIN and save to $SRC_IP_FILE
  - flush prerouting chain
  - add single test DNAT rule for first src IP (if present) to validate syntax
  - if test succeeds, add DNAT rules for all saved src IPs mapping tcp dport 22 -> CANARY_IP:CANARY_PORT
  - print resulting nft table and suggest tcpdump / ss checks

To rollback, run:
  sudo nft -f $NFT_BACKUP

EOF
}

if [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

APPLY=false
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=true; shift ;;
    --canary)
      shift; if [ -z "${1:-}" ]; then echo "--canary needs argument"; exit 1; fi
      CANARY_IP=$(echo "$1" | cut -d: -f1)
      CANARY_PORT=$(echo "$1" | cut -s -d: -f2 || echo "$CANARY_PORT")
      shift ;;
    --canary=*)
      arg=${1#--canary=} ; CANARY_IP=$(echo "$arg" | cut -d: -f1) ; CANARY_PORT=$(echo "$arg" | cut -s -d: -f2 || echo "$CANARY_PORT") ; shift ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 1 ;;
  esac
done

echo "Script mode: ${APPLY:+APPLY=true}${APPLY:-DRY-RUN}"

# helper to run or echo commands
run(){
  if [ "$APPLY" = true ]; then
    echo "+ $*"
    bash -c "$*"
  else
    echo "DRY-RUN: $*"
  fi
}

# Create backup dir
run "mkdir -p '$BACKUP_DIR' && chmod 700 '$BACKUP_DIR'"

# Backup full nft ruleset
run "nft list ruleset > '$NFT_BACKUP' 2> '$BACKUP_DIR/nft_backup.err' || true"

echo "Backup will be stored in $BACKUP_DIR"

# Check table/chain existence
if ! nft list table inet azazel >/dev/null 2>&1; then
  echo "Warning: nft table 'inet azazel' not present. Trying 'ip nat' fallback." >&2
fi

# Extract src IPs from prerouting chain
# Use list chain which is safer than list table in some setups
if nft list chain inet azazel $PREROUTING_CHAIN >/dev/null 2>&1; then
  CMD_EXTRACT="nft list chain inet azazel $PREROUTING_CHAIN | grep -oP 'ip saddr \\K[^ ]+' | sort -u | sed '/^\s*$/d' > '$SRC_IP_FILE'"
  run "$CMD_EXTRACT"
else
  echo "Prerouting chain not found in inet azazel; trying 'nft list table inet azazel' to search rules." >&2
  CMD_EXTRACT2="nft list table inet azazel | grep -oP 'ip saddr \\K[^ ]+' | sort -u | sed '/^\s*$/d' > '$SRC_IP_FILE'"
  run "$CMD_EXTRACT2"
fi

# Show saved src IPs
if [ -f "$SRC_IP_FILE" ]; then
  echo "Saved src IPs:"; run "cat '$SRC_IP_FILE' || true"
else
  echo "No src IPs file created - proceeding but there may be nothing to add.";
fi

# Flush prerouting chain
run "nft flush chain inet azazel $PREROUTING_CHAIN || nft flush chain ip nat $PREROUTING_CHAIN || true"

echo "Prerouting chain flushed (dry-run shows command)."

# If src IP file exists and not empty, add single test rule for first IP
if [ -s "$SRC_IP_FILE" ]; then
  FIRST=$(head -n1 "$SRC_IP_FILE")
  echo "Will attempt single test DNAT for $FIRST -> $CANARY_IP:$CANARY_PORT"
  run "nft add rule inet azazel $PREROUTING_CHAIN ip saddr $FIRST tcp dport 22 dnat to $CANARY_IP:$CANARY_PORT || echo 'add failed'"
  echo "Show chain after test add:"; run "nft list chain inet azazel $PREROUTING_CHAIN || true"

  # If apply mode, then add for all
  if [ "$APPLY" = true ]; then
    echo "Adding DNAT entries for all saved src IPs..."
    while read -r src; do
      [ -z "$src" ] && continue
      run "nft add rule inet azazel $PREROUTING_CHAIN ip saddr $src tcp dport 22 dnat to $CANARY_IP:$CANARY_PORT || echo 'failed for $src'"
    done < "$SRC_IP_FILE"
  else
    echo "Dry-run mode: skip bulk add. Rerun with --apply to apply changes."
  fi
else
  echo "No src IPs found. If you want to add a single test rule, run with --canary and --apply and supply an IP manually in the script or alter src file." >&2
fi

# Final view
echo "Final nft table (prerouting chain):"; run "nft list chain inet azazel $PREROUTING_CHAIN || nft list table inet azazel || true"

echo "Check OpenCanary listener (ss):"; run "ss -ltnp | egrep ':$CANARY_PORT\\s' || ss -ltnp | grep $CANARY_PORT || echo 'no listener on $CANARY_PORT detected'"

echo "Done. If you applied changes and want to rollback use: sudo nft -f $NFT_BACKUP"
