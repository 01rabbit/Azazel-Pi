#!/usr/bin/env bash
# NOTE: This script is deprecated as Azazel-Edge now uses iptables instead of nftables.
# For iptables rule management, use iptables-restore or netfilter-persistent.
set -euo pipefail

echo "WARNING: nft_apply.sh is deprecated. Azazel-Edge now uses iptables." >&2
echo "Please use 'iptables-restore < /path/to/rules' or 'netfilter-persistent reload' instead." >&2
exit 1

# RULESET=${1:-/etc/azazel/nftables/azazel.nft}
# 
# if [[ ! -f "$RULESET" ]]; then
#   echo "ruleset not found: $RULESET" >&2
#   exit 1
# fi
# 
# nft -f "$RULESET"
