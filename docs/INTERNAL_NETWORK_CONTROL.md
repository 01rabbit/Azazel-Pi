# Internal Network Control Design (Draft)

## Objective
Implement fine-grained control inside the LAN (wlan0) for Azazel-Pi, enabling:
- Per-host segmentation (isolate suspicious clients without full lockdown)
- Micro-policies (rate limits, delay, block, redirect per internal IP/MAC)
- Tiered trust zones (trusted, guest, quarantined)
- Dynamic escalation based on threat score and Suricata/OpenCanary events

## Scope (Phase 1)
- Maintain allowlist/denylist of internal hosts (IPs + optional MAC)
- Apply delay/shape/block actions per internal host using existing Action framework
- Extend config (`azazel.yaml`) with new section `internal_control`:
```yaml
internal_control:
  zones:
    trusted: { default_action: portal }
    guest:   { default_action: shield }
    quarantined: { default_action: lockdown }
  hosts:
    # ip_or_cidr: zone
    172.16.0.10: trusted
    172.16.0.50: guest
  escalation:
    # score thresholds to move a host between zones
    guest_to_quarantine: 60
    quarantine_release_score: 30
    observation_window_secs: 900
```

## Data Flow
1. Ingest pipeline records events per internal source IP.
2. Scorer updates cumulative host score cache.
3. InternalControl module evaluates zone transitions and generates Action plans (block/delay/shape) through existing enforcer.
4. Enforcer executes nftables/tc operations using new per-host targets.

## Implementation Plan
- `azazel_pi/core/network/internal_control.py`
  - Class `InternalControlManager` with:
    - `load_config(cfg: dict)`
    - `update_host_score(ip: str, score: float)`
    - `evaluate_transitions()` -> list[ActionResult]
    - `current_zone(ip: str)`
  - Maintains in-memory host state with last scores + zone assignments.
- Extend state machine or add periodic hook in existing daemon loop to call `evaluate_transitions()`.
- Minimal persistence: start with in-memory; later optional JSON snapshot under `/var/lib/azazel/internal_state.json`.

## Actions Mapping
Zone -> action profile:
- trusted: normal / portal (low restriction)
- guest: shield (moderate delay + shaping)
- quarantined: lockdown (block or heavy shaping)

## Edge Cases
- Host without zone mapping: default to guest.
- Rapid oscillation: use hysteresis via `observation_window_secs` and release threshold.
- IP churn (DHCP reassignment): optionally flush state if MAC changes.

## Future (Phase 2)
- MAC-based enforcement sets.
- Lateral movement detection (internal to internal suspicious flows).
- VLAN tagging integration.
- Passive OS fingerprint risk weighting.

## Open Questions
- Should quarantine enforce complete block or aggressive shaping first? (Configurable.)
- Persist host historical scores across reboot? (Optional.)

## Next Steps
1. Add config schema updates (validation).
2. Implement module skeleton with zone resolution.
3. Integrate with scorer or create a host score aggregator.
4. Unit tests for transition logic.
5. Hook into main loop (azctl-unified service path).
