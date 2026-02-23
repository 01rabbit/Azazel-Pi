# nftables Configuration (Deprecated)

**⚠️ NOTICE: These nftables configuration files are no longer used.**

Azazel-Edge has been migrated from nftables to iptables for better compatibility with Docker and to avoid conflicts with the `inet filter/forward` chain.

## What changed?

- **Previous setup**: Used nftables with custom tables (`inet azazel`, `inet filter`, `ip nat`)
- **Current setup**: Uses iptables exclusively (via `iptables-nft` backend)
- **Reason**: The `inet filter/forward policy drop` in nftables was blocking Docker container traffic, including OpenCanary SSH (port 2222)

## Migration summary

1. `/etc/nftables.conf` has been minimized (no active rules)
2. `nftables.service` has been disabled
3. NAT rules are now managed via iptables:
   ```bash
   iptables -t nat -A POSTROUTING -s 172.16.0.0/24 -o wlan1 -j MASQUERADE
   iptables -t nat -A POSTROUTING -s 172.16.10.0/24 -o wlan1 -j MASQUERADE
   ```
4. Blocking rules are now managed via iptables custom chains (see `scripts/ai_policy_block.sh`)

## Files in this directory

- **azazel.nft**: Old nftables ruleset with blocked_hosts set and redirect chain (deprecated)
- **lockdown.nft**: Old lockdown mode configuration (deprecated)

## For future reference

If you need to implement equivalent functionality with iptables:

- **Blocked hosts**: Use iptables custom chain with DROP rules
- **DNAT/redirect**: Use iptables NAT table PREROUTING chain
- **Lockdown allowlist**: Use iptables with ipset for efficient IP set matching

See `scripts/ai_policy_block.sh` and `scripts/azazel_update_dnat.sh` for iptables implementations.
