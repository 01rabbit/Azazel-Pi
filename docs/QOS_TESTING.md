# QoS Internal Network Control - Testing Guide

## DRY_RUN Mode Testing (Completed)

### Purpose
Verify QoS script command generation without modifying actual network state or requiring root privileges.

### Test Environment
- Branch: `feature/internal-network-control`
- Date: 2025-01-XX
- System: Raspberry Pi (yq not installed)
- Privileges: Non-root user

### Tests Performed

#### 1. Syntax Validation
```bash
bash -n bin/azazel-traffic-init.sh  # ✅ PASS
bash -n bin/azazel-qos-apply.sh     # ✅ PASS
bash -n bin/azazel-qos-menu.sh      # ✅ PASS
```

#### 2. Python Module Import
```bash
python3 -c "from azazel_edge.core.network.internal_control import InternalControlManager"  # ✅ PASS
python3 -c "import sys; sys.path.insert(0, 'services'); import azazel_priorityd"        # ✅ PASS
```

#### 3. Logic Verification
```python
# Test compute_assignments() with sample scores
scores = {"172.16.0.80": 0, "172.16.0.81": 50, "172.16.0.82": 75, "172.16.0.83": 95}
# Result: {'172.16.0.80': 'premium', '172.16.0.81': 'standard', 
#          '172.16.0.82': 'standard', '172.16.0.83': 'best_effort'}
# ✅ PASS - Score-to-class mapping works correctly per config thresholds
```

#### 4. DRY_RUN Command Generation

**Traffic Initialization (traffic-init.sh):**
```bash
DRY_RUN=1 bin/azazel-traffic-init.sh configs/network/azazel.yaml
```
✅ **PASS** - Generated commands:
- tc qdisc replace: HTB root qdisc with default class 30
- tc class replace: 4 classes (10, 20, 30, 40) with rate/ceil 10000kbit
- tc filter replace: 8 filters (IPv4/IPv6 for each class) with mark 0x10
- nft operations: table creation, chain setup, set initialization
- Fallback defaults applied when yq not found (WAN_IF=eth0)

**QoS Apply - Verify Mode:**
```bash
DRY_RUN=1 MODE=verify bin/azazel-qos-apply.sh configs/network/privileged.csv
```
✅ **PASS** - Generated commands:
- nft flush set: v4ipmac, v4priv cleared
- nft add element: 2 IP/MAC pairs added to v4ipmac with mark 0x10
- nft add element: 2 IPs added to v4priv
- nft flush chain: prerouting chain cleared
- nft add rule: Marking rule for IP+MAC match
- nft add rule: Drop rule for mismatched privileged IPs
- Fallback defaults applied (MARK=0x10, LAN_IF=wlan0)

**QoS Apply - Lock Mode:**
```bash
DRY_RUN=1 MODE=lock bin/azazel-qos-apply.sh configs/network/privileged.csv
```
✅ **PASS** - Generated commands:
- All verify mode commands +
- ip neigh replace: 2 static ARP entries (172.16.0.10, 172.16.0.11) with permanent state

#### 5. Priority Daemon Startup
```bash
timeout 3 python3 services/azazel_priorityd.py
```
✅ **PASS** - Daemon started successfully:
- Output: `assignments={}`
- Behavior: No scores.json present → empty assignments (expected)
- Exit: Clean timeout after 3 seconds

### Observations

#### Strengths
1. **Safety**: No root required, no network modification
2. **Portability**: yq optional with sensible fallback defaults
3. **Transparency**: All commands printed with `+ ` prefix for easy review
4. **Correctness**: Variable substitution and CSV parsing work as designed
5. **Mode handling**: verify/lock modes generate appropriate rule differences

#### Identified Issues
None. All scripts behave as expected in DRY_RUN mode.

### Next Steps

#### Before Real Network Testing
1. ✅ DRY_RUN verification complete
2. ⏸️ Install yq on production system: `pip install yq` or package manager
3. ⏸️ Verify configs/network/azazel.yaml has correct interface names
4. ⏸️ Update configs/network/privileged.csv with real IP/MAC pairs
5. ⏸️ Schedule maintenance window with console access available
6. ⏸️ Backup current nftables rules: `nft list ruleset > backup.nft`
7. ⏸️ Backup current tc rules: `tc qdisc show > backup.tc`

#### Real Network Testing (Controlled Environment)
```bash
# Step 1: Initialize tc/nft infrastructure (idempotent, safe to re-run)
sudo bin/azazel-traffic-init.sh configs/network/azazel.yaml

# Step 2: Apply privileged host rules in none mode (mark only, no drop)
sudo MODE=none bin/azazel-qos-apply.sh configs/network/privileged.csv

# Step 3: Verify marking is working
sudo nft list set inet azazel v4ipmac
sudo nft list chain inet azazel prerouting

# Step 4: Test with real traffic, observe packet counters
sudo nft -s list chain inet azazel prerouting

# Step 5: If marking works, upgrade to verify mode
sudo MODE=verify bin/azazel-qos-apply.sh configs/network/privileged.csv

# Step 6: Monitor for dropped packets (privileged IPs with wrong MAC)
sudo nft -s list chain inet azazel prerouting | grep drop

# Step 7: If verify mode stable, optionally upgrade to lock mode
sudo MODE=lock bin/azazel-qos-apply.sh configs/network/privileged.csv

# Step 8: Verify static ARP entries
ip neigh show dev wlan0 nud permanent
```

#### Rollback Procedure
If issues occur:
```bash
# Remove tc shaping
sudo tc qdisc del dev eth0 root

# Remove nftables rules
sudo nft delete table inet azazel

# Remove static ARP (lock mode only)
sudo ip neigh flush dev wlan0
```

#### Priority Daemon Testing
After QoS infrastructure is stable:
```bash
# Create test scores file
cat > /tmp/scores.json <<EOF
{
  "172.16.0.10": 25,
  "172.16.0.11": 80
}
EOF

# Run daemon with test scores
sudo SCORE_FILE=/tmp/scores.json python3 services/azazel_priorityd.py
# Expected: Assignments printed, host 172.16.0.10 should get better class than 172.16.0.11
```

### Conclusion
DRY_RUN testing demonstrates that all QoS scripts generate correct commands with proper variable substitution, CSV parsing, and mode handling. The implementation is ready for controlled real-network testing in a maintenance window with rollback plan available.

**Status**: ✅ DRY_RUN verification complete, awaiting production deployment window.
