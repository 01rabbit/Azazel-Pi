# Changelog

All notable changes to this project will be documented in this file.

## [2.2.0] - 2025-11-07
### Added
- **Internal Network QoS Control**: Comprehensive privilege-based traffic shaping and security enforcement for LAN devices.
  - Mark-based traffic classification (premium, standard, best_effort, restricted) using nftables.
  - HTB (Hierarchical Token Bucket) traffic shaping with configurable per-class rate/ceil limits.
  - Three security modes: `none` (marking only), `verify` (MAC verification with drop), `lock` (verify + static ARP).
  - CSV-based privileged host registry (`configs/network/privileged.csv`) for IP/MAC whitelist management.
  - Dynamic priority daemon (`services/azazel_priorityd.py`) with score-based class adjustment.
  - Interactive TUI management tool (`bin/azazel-qos-menu.sh`) for privileged host operations.
  - New scripts: `bin/azazel-traffic-init.sh`, `bin/azazel-qos-apply.sh` with DRY_RUN mode for safe testing.
  - systemd units: `azazel-traffic-init.service`, `azazel-qos-apply.service`, `azazel-priorityd.service`.
  - Python module: `azazel_pi/core/network/internal_control.py` (InternalControlManager skeleton).
- Extended `configs/network/azazel.yaml` with QoS configuration keys (mark_map, classes, thresholds, dynamic_bias).
- Documentation: `docs/INTERNAL_NETWORK_CONTROL.md` (architecture), `docs/QOS_TESTING.md` (testing guide with DRY_RUN results).

### Changed
- QoS scripts support DRY_RUN mode (print commands without execution, no root required).
- All QoS scripts are idempotent (safe to re-run).

### Security
- MAC address verification prevents ARP spoofing for privileged devices.
- Static ARP entries in `lock` mode provide additional anti-spoofing protection.
- Gradual rollout path (none → verify → lock) allows safe deployment testing.

### Testing
- Syntax validation: All scripts pass `bash -n` checks.
- Python imports: All modules verified.
- Logic verification: Score-to-class mapping validated.
- DRY_RUN tests: Command generation confirmed for all modes (verify, lock).

### Notes
- Minor version bump (2.1.0 → 2.2.0) adds significant new QoS feature without breaking existing functionality.
- QoS features are opt-in via systemd service enablement.
- All changes maintain backward compatibility with existing configurations.

## [2.1.0] - 2025-11-07
### Added
- Optional E-Paper integration into `install_azazel_complete.sh` via `--enable-epd`, `--epd-emulate`, and `--epd-force` flags.
- Emulation support for E-Paper (no hardware required) using `EPD_OPTS=--emulate` and new systemd unit option passthrough.
- Documentation updates (EN/JA) reflecting integrated E-Paper flow and hardware-absent usage.
- Deprecation stubs for legacy scripts: `install_epd.sh`, wireless setup scripts, and Ollama split scripts.
- Unified wireless script `setup_wireless.sh` and unified Ollama script `setup_ollama_unified.sh` (created earlier, documented here).
- Integration reports and AI verification docs (Enhanced AI, Wireless, Ollama, Suricata) for transparency and reproducibility.

### Changed
- `systemd/azazel-epd.service` now supports extra daemon options via `EPD_OPTS` environment variable.
- Installer step numbering adjusted to include optional E-Paper integration block.
- README files updated to recommend new flags instead of deprecated standalone scripts.

### Deprecated
- Standalone `scripts/install_epd.sh` (now emits deprecation notice and exits).
- Legacy wireless scripts: `setup_wlan0_ap.sh`, `setup_suricata_wlan1.sh`.
- Legacy Ollama scripts: `setup_ollama.sh`, `setup_ollama_model.sh`.

### Notes
- Minor version bump (2.0.0 → 2.1.0) because changes add optional features without breaking existing workflows.
- Future removal of deprecated stubs planned for a subsequent minor or major release (target: ≥2.2.0).

## [2.0.0]
- Prior stable baseline with Suricata integration, AI threat evaluation pipeline, and initial E-Paper support (manual setup).

--
Semantic versioning: MAJOR.MINOR.PATCH. Deprecations queued for removal after at least one minor release grace period.
