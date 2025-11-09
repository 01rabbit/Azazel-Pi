# Changelog

All notable changes to this project will be documented in this file.

## [3.1.0] - 2025-11-09
### Added
- Display: clear and force a full E-Paper refresh when the active WAN interface changes (e.g. eth0 -> wlan1) to avoid ghosting and show the updated interface/IP immediately. (commit 478b8ee)
- Status collection: prefer kernel default route when runtime WAN state is missing and provide a `wan_state_path` injection point for testing/overrides.
- Renderer: improve network line formatting by removing the redundant "WAN" prefix and suppressing non-actionable "[WAN] unknown" messages; reserve footer area to prevent text overlap.

### Changed
- Backwards-compatible `StatusCollector` initialization handling in `epd_daemon` — older installs without the new `wan_state_path` parameter are tolerated.

### Notes
- These are backward-compatible improvements (minor release). See commit 478b8ee for details and files changed: `azazel_pi/core/display/status_collector.py`, `epd_daemon.py`, `renderer.py`.
  - Suricata integration for network threat detection
  - AI-based threat evaluation pipeline and scoring
  - Basic TUI and CLI utilities for status and control
  - Initial installer and documentation to deploy core services

## [3.0.0] - 2025-11-09
### Added
- Dynamic WAN selection and runtime orchestration via `azctl wan-manager`:
  - Evaluates candidate uplink interfaces and selects the healthiest WAN at boot and runtime.
  - Writes health snapshots to `runtime/wan_state.json` (production path `/var/run/azazel/wan_state.json`); path can be overridden with `AZAZEL_WAN_STATE_PATH`.
  - Candidate precedence: explicit CLI `--candidate` → `AZAZEL_WAN_CANDIDATES` env var (comma-separated) → `configs/network/azazel.yaml` (`interfaces.external`/`interfaces.wan`) → safe fallbacks.
  - On WAN change, the manager reapplies traffic control (`bin/azazel-traffic-init.sh`), refreshes NAT, and restarts dependent services (Suricata, `azctl-unified`).

- Universal runtime interface resolution for consumers:
  - CLI/TUI, scripts, and services now prefer explicit CLI args → environment variables (`AZAZEL_WAN_IF` / `AZAZEL_LAN_IF`) → WAN manager state → configuration values → final fallback.
  - Added `AZAZEL_WAN_CANDIDATES` and `AZAZEL_WAN_STATE_PATH` environment variables for operational control and testing.

### Changed
- Scripts and documentation updated to use parameterized interface references (`${AZAZEL_WAN_IF:-<fallback>}` and `${AZAZEL_LAN_IF:-<fallback>}`) in help text and examples. Where safe, runtime resolution now uses the WAN manager helper instead of hard-coded interface names.

### Notes
- Backwards-compatible: explicit CLI flags and environment variables still override runtime selection. Existing deployments should continue to work; review scripts that assume literal interface names before automating deployment.
- Tests and shell syntax checks were run after edits; no regressions detected in the unit test suite.
- QoS features are opt-in via systemd service enablement.
- All changes maintain backward compatibility with existing configurations.

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
 - Dynamic WAN selection: `wan-manager` now determines the active WAN interface at runtime and writes runtime/wan_state.json. Consumers (CLI, TUI, scripts) will use that selection by default when `--wan-if` is omitted. Environment variables `AZAZEL_WAN_IF` and `AZAZEL_LAN_IF` may be used to override defaults where needed.

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

## [1.5.0] - 2025-11-05
### Added
- Nginx reverse proxy configuration and setup scripts to front-end Mattermost and other services.
- Mattermost full-reset script and Docker/Postgres integration for easy environment refresh.
- Configuration schema updates to support external interfaces and updated defaults in `azazel.yaml`.
- Suricata can monitor multiple interfaces (wlan1 and eth0) for broader visibility.
- Documentation updates (EN/JA) covering Nginx setup and network configuration notes.

### Changed
- Adjusted Nginx recommended headers and client/body limits.
- Cleaned up legacy service files and removed deprecated references.

### Notes
- Version bump to 1.5.0; this release focuses on deployability and documentation improvements.

## [1.0.0] - 2025-10-05
### Initial release
- Initial public baseline of Azazel-Pi with core features:
