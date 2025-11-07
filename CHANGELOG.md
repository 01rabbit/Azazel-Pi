# Changelog

All notable changes to this project will be documented in this file.

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
