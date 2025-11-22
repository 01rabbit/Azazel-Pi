#!/usr/bin/env bash
# Safe helper to update iptables DNAT rules for Azazel -> redirect SSH (tcp dport 22)
# to OpenCanary IP and port (default 127.0.0.1:2222).
# Usage (recommended): edit CANARY_IP / CANARY_PORT below if needed, then:
#   sudo cp scripts/azazel_update_dnat.sh /usr/local/sbin/azazel_update_dnat.sh
#   sudo bash /usr/local/sbin/azazel_update_dnat.sh --apply
# Or run interactively (no --apply runs in dry-run mode printing actions).

set -euo pipefail
SCRIPT_NAME=$(basename "$0")
BACKUP_DIR=/tmp/azazel_backup_$(date +%s)
SRC_IP_FILE="$BACKUP_DIR/src_ips.txt"
IPTABLES_BACKUP="$BACKUP_DIR/iptables_backup.rules"

# Default values (edit this file or pass via env)
CANARY_IP=${CANARY_IP:-127.0.0.1}
CANARY_PORT=${CANARY_PORT:-2222}
CHAIN_NAME=${CHAIN_NAME:-AZAZEL_DNAT}

usage(){
  cat <<EOF
$SCRIPT_NAME - safe DNAT updater for Azazel (iptables)

Options:
  --apply        Actually apply changes. Without this, the script does a dry-run and prints the commands it would run.
  --canary ip:port  Override CANARY target (e.g. 127.0.0.1:2222)
  --help         Show this help

Steps performed when --apply is provided:
  - backup full iptables ruleset to $IPTABLES_BACKUP
  - extract src IPs from $CHAIN_NAME chain and save to $SRC_IP_FILE
  - flush AZAZEL_DNAT chain (or create if not exists)
  - add single test DNAT rule for first src IP (if present) to validate syntax
  - if test succeeds, add DNAT rules for all saved src IPs mapping tcp dport 22 -> CANARY_IP:CANARY_PORT
  - print resulting iptables rules and suggest tcpdump / ss checks

To rollback, run:
  sudo iptables-restore < $IPTABLES_BACKUP

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

# Backup full iptables ruleset
run "iptables-save > '$IPTABLES_BACKUP' 2> '$BACKUP_DIR/iptables_backup.err' || true"

echo "Backup will be stored in $BACKUP_DIR"

# Create custom chain if not exists
run "iptables -t nat -N '$CHAIN_NAME' 2>/dev/null || true"

# Link chain to PREROUTING if not already linked
run "iptables -t nat -C PREROUTING -j '$CHAIN_NAME' 2>/dev/null || iptables -t nat -I PREROUTING -j '$CHAIN_NAME' || true"

# Extract src IPs from existing DNAT rules in custom chain
CMD_EXTRACT="iptables-save -t nat | grep -E '^-A $CHAIN_NAME.*--source' | grep -oP '\\-\\-source \\K[0-9.]+' | sort -u > '$SRC_IP_FILE'"
run "$CMD_EXTRACT"

# Show saved src IPs
if [ -f "$SRC_IP_FILE" ]; then
  echo "Saved src IPs:"; run "cat '$SRC_IP_FILE' || true"
else
  echo "No src IPs file created - proceeding but there may be nothing to add.";
fi

# Flush custom chain
run "iptables -t nat -F '$CHAIN_NAME' || true"

echo "AZAZEL_DNAT chain flushed (dry-run shows command)."

# If src IP file exists and not empty, add single test rule for first IP
if [ -s "$SRC_IP_FILE" ]; then
  FIRST=$(head -n1 "$SRC_IP_FILE")
  echo "Will attempt single test DNAT for $FIRST -> $CANARY_IP:$CANARY_PORT"
  run "iptables -t nat -A '$CHAIN_NAME' -p tcp -s $FIRST --dport 22 -j DNAT --to-destination $CANARY_IP:$CANARY_PORT || echo 'add failed'"
  echo "Show chain after test add:"; run "iptables -t nat -L '$CHAIN_NAME' -n -v || true"

  # If apply mode, then add for all
  if [ "$APPLY" = true ]; then
    echo "Adding DNAT entries for all saved src IPs..."
    while read -r src; do
      [ -z "$src" ] && continue
      run "iptables -t nat -A '$CHAIN_NAME' -p tcp -s $src --dport 22 -j DNAT --to-destination $CANARY_IP:$CANARY_PORT || echo 'failed for $src'"
    done < "$SRC_IP_FILE"
  else
    echo "Dry-run mode: skip bulk add. Rerun with --apply to apply changes."
  fi
else
  echo "No src IPs found. If you want to add a single test rule, run with --canary and --apply and supply an IP manually in the script or alter src file." >&2
fi

# Final view
echo "Final iptables NAT rules (AZAZEL_DNAT chain):"; run "iptables -t nat -L '$CHAIN_NAME' -n -v || true"

echo "Check OpenCanary listener (ss):"; run "ss -ltnp | egrep ':$CANARY_PORT\\s' || ss -ltnp | grep $CANARY_PORT || echo 'no listener on $CANARY_PORT detected'"

echo "Done. If you applied changes and want to rollback use: sudo iptables-restore < $IPTABLES_BACKUP"
