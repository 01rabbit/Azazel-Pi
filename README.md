# AZ-01X Azazel-Pi - The Cyber Scapegoat Gateway

English | [日本語](README_ja.md)

![Azazel-Pi_image](images/Azazel-Pi_logo.png)  
![version](https://img.shields.io/github/v/tag/01rabbit/Azazel-Pi?label=Version)
![License](https://img.shields.io/github/license/01rabbit/Azazel-Pi)
![release-date](https://img.shields.io/github/release-date/01rabbit/Azazel-Pi)
![BSidesTokyo](https://img.shields.io/badge/BSidesTokyo-2025-lightgreen)
![BSidesLV](https://img.shields.io/badge/BSidesLV-2025-lightgreen)
![BHUSA](https://img.shields.io/badge/BlackHat%20USA%20Arsenal-2025-black)
![SecTor](https://img.shields.io/badge/SecTor%20Arsenal-2025-red)
![bluebox](https://img.shields.io/badge/CODE%20BLUE%20bluebox-2025-blue)

## Concept

Do you know the term **Delaying Action**? In military strategy, this refers to a defensive operation where defending forces continue to fight while avoiding decisive engagement, slowing the enemy's advance as much as possible to buy time. In today's cyber warfare, attacks are fast and automated, with assets potentially compromised within seconds. We believe this classical tactical concept should be reinterpreted and applied to modern cybersecurity.

Based on this philosophy, we developed the **Azazel System**. This tool implements a **scapegoat-style decoy** that absorbs attacks, misleads adversaries, and tactically delays their progress. Unlike traditional honeypots that merely observe, Azazel actively restrains attackers, realizing **delaying action in cyberspace**.

The system is designed as a **portable security gateway** that proactively protects users when connecting to **untrusted external networks** such as hotel Wi-Fi, event venues, or when defending **temporary lab environments**.

While the modern battlefield has shifted to cyberspace, the concept of "restraining the enemy to buy time" remains valid. **Azazel System** embodies one answer to tactical "cyber containment" in digital warfare.

## Design Principles

The defensive philosophy of **Azazel System** draws inspiration from two Japanese tactical concepts:

**Battlefield Containment**: Based on the Imperial Japanese Army's defensive principle of "binding the enemy to the battlefield." Rather than simply blocking attacks, this approach deliberately draws adversaries into a controlled environment, restricting their freedom of action while buying time for preparation and counteroffensives. Azazel similarly guides intruders into decoys and communication delays, constraining attack vectors and transferring initiative to the defender.

**Go no Sen (後の先)**: An advanced martial arts strategy of "taking initiative in response." Though appearing reactive, this technique uses the opponent's movement to gain control and create counterattack opportunities. Azazel implements this philosophy by triggering delay controls after Suricata detection, deliberately accepting, observing, and controlling attacks—embodying this tactical response pattern.

Thus, Azazel realizes the concept that "defense is not merely protection, but controlling enemy behavior and buying time"—a cyber deception tool rooted in Japanese strategic thinking.

## Implementation

### Base Platform

- **Raspberry Pi 5 Model B** (Portable Security Gateway)
- Optimized for field deployment and temporary network protection
- Low-cost solution for small-scale network defense

### Comparison with Azazel-Zero

- **Azazel-Pi**
  - Built on Raspberry Pi 5 as a Portable Security Gateway (Cyber Scapegoat Gateway)
  - Designed as a concept model to provide low-cost protection for small-scale networks temporarily constructed
  - Strongly experimental in nature, serving as a testbed for multiple technical elements

- **Azazel-Zero**  
  - A lightweight version, intended for real-world operation by limiting use cases and stripping away unnecessary features
  - Built as a portable physical barrier, prioritizing mobility and practicality
  - Unlike the concept-model Azazel-Pi, Azazel-Zero is positioned as a field-ready practical model

### Core Defense Functions

#### Real-Time Threat Detection & Response

- **Suricata IDS/IPS**: Intrusion detection and prevention system
- **OpenCanary**: Honeypot services for attacker misdirection
- **Dynamic Traffic Control**: `tc` and `iptables` for tactical delay
  - DNAT enforcement uses iptables NAT rules for transparent traffic redirection to honeypot services.

#### Defensive Modes

- **Portal Mode** (Green): Normal operations with minimal restrictions
- **Shield Mode** (Yellow): Heightened monitoring with traffic shaping and QoS controls
- **Lockdown Mode** (Red): Full containment with strict firewall rules and allowlist-only communication

#### Status Display & Monitoring

- **E-Paper Display**: Real-time status visualization showing current defensive mode, threat score, network status, and alert counters
- **Interactive TUI Menu**: Comprehensive terminal-based control interface with keyboard navigation and safety features
- **Rich CLI Interface**: Terminal-based status monitoring with color-coded mode indicators
- **Web Dashboard**: Mattermost integration for alerts and notifications

### Architecture Components

| Component | Purpose |
|-----------|---------|
| `azazel_pi/core/state_machine.py` | Governs transitions between defensive postures |
| `azazel_pi/core/actions/` | Models tc/iptables operations as idempotent plans |
| `azazel_pi/core/ingest/` | Parses Suricata EVE logs and OpenCanary events |
| `azazel_pi/core/display/` | E-Paper status visualization and rendering |
| `azctl/` | Command-line interface, daemon management, and interactive TUI menu |
| `configs/` | Declarative configuration with schema validation |
| `deploy/` | Third-party service deployment configurations |
| `scripts/install_azazel.sh` | Automated provisioning and setup |

## Features

### Tactical Delaying Implementation

Applies the military concept of "delaying action" to cyberspace—permitting intrusion while strategically controlling its progression through traffic shaping and misdirection.

### Scapegoat Decoy System

Leverages OpenCanary and custom services to mislead and isolate attackers rather than merely observing them, without affecting legitimate users.

### Adaptive Response System

- **Portal → Shield**: Activates traffic control and enhanced monitoring
- **Shield → Lockdown**: Implements strict firewall rules with medical FQDN allowlists
- **Dynamic Scoring**: Continuous threat assessment with automatic mode transitions

### Internal Network QoS Control (New in v2.2.0)

Privilege-based traffic shaping and security enforcement for LAN devices:

- **Mark-Based Classification**: Premium, standard, best effort, and restricted traffic classes with HTB bandwidth shaping
- **MAC Verification**: Three security modes (none/verify/lock) for preventing ARP spoofing and IP/MAC mismatch attacks
- **Dynamic Priority**: Optional score-based automatic class adjustment for adaptive bandwidth allocation
- **CSV Registry**: Simple CSV-based management of privileged hosts with IP/MAC whitelisting
- **Interactive TUI**: Command-line menu for privileged host management and mode switching
- **Safe Testing**: DRY_RUN mode for verifying configurations without network modification

See [`docs/INTERNAL_NETWORK_CONTROL.md`](docs/INTERNAL_NETWORK_CONTROL.md) for architecture and [`docs/QOS_TESTING.md`](docs/QOS_TESTING.md) for testing guide.

### Portable Deployment

Lightweight configuration optimized for Raspberry Pi, enabling rapid deployment in disaster recovery, field operations, or temporary network setups.

## Technology Stack

- **Base OS**: Raspberry Pi OS (64-bit Lite)
- **IDS/IPS**: Suricata with custom rule sets
- **Honeypot**: OpenCanary for service deception
- **Log Processing**: Vector for centralized log collection
- **Traffic Control**: `tc` (Traffic Control) + `iptables`
- **Alerting**: Mattermost integration
- **Display**: Waveshare E-Paper with Python rendering
- **Languages**: Python 3.8+ with asyncio, rich, and interactive TUI libraries

## Installation

### Requirements

- Raspberry Pi 5 Model B (recommended) or compatible ARM64 device
- Raspberry Pi OS (64-bit Lite) or Debian-based distribution  
- Internet connection for dependency installation
- Administrator privileges (sudo access)
- Optional: Waveshare 2.13" E-Paper display for status visualization

### Quick Setup

After cloning the repository or downloading a release, run the complete automated installer:

```bash
# Launch TUI menu. If you omit --wan-if the CLI will dynamically resolve the WAN
# interface using the WAN manager (recommended). You can also force an interface
# via the AZAZEL_WAN_IF / AZAZEL_LAN_IF environment variables.
# Example: prefer runtime selection — WAN will be resolved automatically when omitted.
# You can override the detected interfaces with environment variables:
#   export AZAZEL_LAN_IF=${AZAZEL_LAN_IF:-wlan0}
#   export AZAZEL_WAN_IF=${AZAZEL_WAN_IF:-wlan1}
# then run the CLI without the --wan-if flag if you want the runtime helper to pick the WAN.
python3 -m azctl.cli menu --lan-if ${AZAZEL_LAN_IF:-wlan0}
# or: omit --wan-if to let the system choose the active WAN interface
python3 -m azctl.cli menu --lan-if ${AZAZEL_LAN_IF:-wlan0}
```
sudo scripts/install_azazel_complete.sh --start

# Or step-by-step installation:
# 1. Base installation
sudo scripts/install_azazel.sh

# 2. Complete configuration setup (recommended)
sudo scripts/install_azazel_complete.sh --start

# 3. Ollama AI model setup
sudo scripts/setup_ollama_model.sh
```

**Complete installer (`install_azazel_complete.sh`) includes:**
- Base dependencies (Suricata, Vector, OpenCanary, Docker)
- E-Paper display support (Pillow, NumPy)
- PostgreSQL and Ollama containers
- All configuration files deployment
- Nginx reverse proxy setup
- Systemd service configuration
- Ollama model setup instructions

**Ollama model setup:**
The installer will prompt you to download the AI model file:
```bash
wget -O /opt/models/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf \
  https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf
```

Or use the automated model setup script:
```bash
sudo scripts/setup_ollama_model.sh
```

For complete installation instructions, troubleshooting, and E-Paper setup, see [`docs/en/INSTALLATION.md`](docs/en/INSTALLATION.md).

### E-Paper Display Setup (Optional)

If using a Waveshare E-Paper display:

```bash
# Enable E-Paper integration in the complete installer
sudo scripts/install_azazel_complete.sh --enable-epd --start

# If hardware isn't connected, use emulation
sudo scripts/install_azazel_complete.sh --enable-epd --epd-emulate --start

# Test the display (use --emulate if hardware not present)
sudo python3 -m azazel_pi.core.display.epd_daemon --mode test --emulate

# Enable the E-Paper service (if you didn't use --start)
sudo systemctl enable --now azazel-epd.service
```

See [`docs/en/EPD_SETUP.md`](docs/en/EPD_SETUP.md) for complete E-Paper configuration instructions.

## Running tests (developer)

This project uses a local virtual environment at `.venv` for development tests. To run the unit tests that exercise E-Paper rendering in emulation mode, do the following:

1. Activate or create the virtual environment (example):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements-dev.txt
```

2. Install optional dependencies used by E-Paper rendering (Pillow) if not included in `requirements-dev.txt`:

```bash
pip install pillow
```

3. Run tests (example):

```bash
.venv/bin/pytest tests/core/test_epd_daemon.py -q
```

Notes:
- The E-Paper renderer supports `--emulate` which avoids hardware access and writes a PNG file when run in `--mode test`.
- Use `--wan-state-path` to point the renderer/collector at a custom WAN state file for integration testing.

### Optional: Front Mattermost with Nginx

To serve Mattermost via Nginx reverse proxy (recommended), use the provided template and setup script:

```bash
sudo scripts/setup_nginx_mattermost.sh
```

This will:

- Install Nginx (if missing)
- Deploy the reverse proxy config from `deploy/nginx-site.conf`
- Enable the site and reload Nginx

Afterwards, Mattermost should be reachable at `http://<device-ip>/` (port 80) and proxied to `127.0.0.1:8065`.
For HTTPS, add your TLS server block or use Certbot.

### Modular TUI Menu System

The interactive Terminal User Interface (TUI) menu provides comprehensive system management through a modular architecture designed for maintainability and extensibility:

```bash
# Launch the TUI menu
python3 -m azctl.cli menu

# With specific interface configuration
python3 -m azctl.cli menu --lan-if ${AZAZEL_LAN_IF:-wlan0} --wan-if ${AZAZEL_WAN_IF:-wlan1}
```

**Modular Architecture:**

Azazel-Pi's menu system employs a modular design with functional separation for improved maintainability:

``` text
azctl/menu/
├── core.py          # Main framework
├── types.py         # Data type definitions
├── defense.py       # Defense control module
├── services.py      # Service management module
├── network.py       # Network information module
├── wifi.py          # WiFi management module
├── monitoring.py    # Log monitoring module
├── system.py        # System information module
└── emergency.py     # Emergency operations module
```

**Key Features:**

- **Modular Design**: Function-specific modules for enhanced maintainability
- **Rich UI**: Color-coded panels, tables, and progress bars
- **Safety-First**: Multi-stage confirmation for dangerous operations
- **Extensible**: Easy addition of new functionality through module system
- **Real-time Monitoring**: Live status displays with automatic updates

## Usage

### Command Line Interface

#### Status Monitoring

```bash
# Basic status (text output)
python3 -m azctl.cli status

# JSON output for scripting
python3 -m azctl.cli status --json

# Rich TUI with color-coded panels
python3 -m azctl.cli status --tui

# Continuous monitoring
python3 -m azctl.cli status --watch --interval 2
```

#### Mode Management

```bash
# Long-running daemon (automatic mode switching)
python3 -m azctl.cli serve

# Manual mode transitions
echo '{"mode": "shield"}' | azctl events --config -
echo '{"mode": "lockdown"}' | azctl events --config -
```

#### Interactive TUI Menu

The modular TUI menu provides comprehensive system management:

```bash
# Launch modular TUI menu. If --wan-if is omitted, azctl will consult the
# WAN manager to select the active WAN interface. To override selection use
# the CLI flags or environment variables described below.
python3 -m azctl.cli menu

# Specify custom interfaces (explicit override)
python3 -m azctl.cli menu --lan-if ${AZAZEL_LAN_IF:-wlan0} --wan-if ${AZAZEL_WAN_IF:-wlan1}

# Or let the system choose WAN automatically:
python3 -m azctl.cli menu --lan-if ${AZAZEL_LAN_IF:-wlan0}
```

**Menu Features:**

1. **Defense Control** (`defense.py`)
   - Current defense mode display (Portal/Shield/Lockdown)
   - Manual mode switching (emergency overrides)
   - Decision history and score trends
   - Real-time threat score monitoring

2. **Service Management** (`services.py`)
   - Azazel core service control (azctl-unified, suricata, opencanary, vector)
   - Service status overview
   - Real-time log file viewing
   - Service restart and health checks

3. **Network Information** (`network.py`)
   - WiFi management integration
   - Interface status and IP configuration
   - Active profiles and QoS settings
   - Network traffic statistics

4. **WiFi Management** (`wifi.py`)
   - Nearby WiFi network scanning
   - WPA/WPA2 network connection
   - Saved network management
   - Connection status and signal strength

5. **Log Monitoring** (`monitoring.py`)
   - Suricata alert real-time monitoring
   - OpenCanary honeypot events
   - System logs and daemon logs
   - Security event summaries

6. **System Information** (`system.py`)
   - CPU, memory, disk usage
   - Network interface statistics
   - System temperature monitoring
   - Process list and resource usage

7. **Emergency Operations** (`emergency.py`)
   - Emergency lockdown (immediate network isolation)
   - Complete network configuration reset
   - System status report generation
   - Factory reset (requires confirmation)

**Technical Features:**

- **Modular Design**: Each function implemented as independent module
- **Rich UI**: Color-coded panels, tables, progress bars
- **Error Handling**: Robust error processing and recovery
- **Security-Focused**: Multi-stage confirmation for dangerous operations
- **Extensible**: Easy addition of new functionality

**Safety Features:**

- Confirmation dialogs for dangerous operations
- Automatic root permission verification
- Automatic operation logging
- Error handling and automatic recovery procedures
- Emergency operations require multiple confirmations

**Keyboard Navigation:**

- `Number keys`: Select menu items
- `r`: Refresh screen
- `b`: Return to previous menu
- `q`: Exit
- `Ctrl+C`: Safe interruption anytime

**Safety Features:**

- Confirmation dialogs for dangerous operations
- Root permission validation for privileged actions
- Automatic operation logging
- Error handling and recovery procedures

**Navigation:**

- `Number keys`: Select menu items
- `r`: Refresh screen
- `b`: Back to previous menu
- `q`: Quit
- `Ctrl+C`: Interrupt at any time

### Configuration Workflow

1. **Edit Core Configuration**: Modify `/etc/azazel/azazel.yaml` to adjust delay values, bandwidth controls, and lockdown allowlists (template at `configs/network/azazel.yaml`).
   - Interface defaults: `${AZAZEL_LAN_IF:-wlan0}` is typically treated as the internal LAN (AP); `${AZAZEL_WAN_IF:-wlan1}` and `${AZAZEL_WAN_IF:-eth0}` are common external (WAN/uplink) candidates and are listed under `interfaces.external` in `configs/network/azazel.yaml`.
       Note: Azazel now prefers a runtime WAN selection produced by the WAN manager when `--wan-if` is not provided. To explicitly override the chosen interfaces, set the environment variables `AZAZEL_WAN_IF` and/or `AZAZEL_LAN_IF` before running commands or scripts.
   - Override options:
     - CLI: pass `--lan-if` and/or `--wan-if` to `azctl` commands to explicitly set interfaces.
     - Environment: set `AZAZEL_LAN_IF` or `AZAZEL_WAN_IF` to change defaults for scripts and services.
     - Dynamic: if `--wan-if` is omitted, `azctl` will query the WAN manager (recommended) to pick the active WAN interface based on runtime health checks.

2. **Generate Suricata Rules**: Use `scripts/suricata_generate.py` to render environment-specific IDS configurations

3. **Restart Services**: Apply changes with `sudo systemctl restart azctl-unified.service`

4. **Health Check**: Verify service status using `scripts/sanity_check.sh`

5. **Monitor Operations**: Analyze scoring results in `decisions.log` and use `azctl` for manual mode switching during incidents

### Dynamic WAN Selection (NEW)

- The `azctl wan-manager` service evaluates all candidate WAN interfaces (from `interfaces.external`) after boot and continuously during runtime.
- Health snapshots (link status, IP presence, estimated speed) are written to `runtime/wan_state.json` (or `/var/run/azazel/wan_state.json` on deployed systems) and surfaced on the E-Paper display. You can override the default path with the `AZAZEL_WAN_STATE_PATH` environment variable when testing or for non-standard deployments.
- The WAN manager reads candidate lists in order of precedence: explicit CLI `--candidate` arguments, the `AZAZEL_WAN_CANDIDATES` environment variable (comma-separated), values declared in `configs/network/azazel.yaml` (`interfaces.external` or `interfaces.wan`), then safe fallbacks. Use `AZAZEL_WAN_CANDIDATES` to force a specific candidate ordering without changing config files.
- When the active interface changes, the manager reapplies `bin/azazel-traffic-init.sh`, refreshes NAT (`iptables -t nat`), and restarts dependent services (Suricata and `azctl-unified`) so they immediately consume the new interface.
- Suricata now launches through `azazel_pi.core.network.suricata_wrapper`, which reads the same WAN state file, so restarting the service is sufficient to follow the latest selection.

Developer note — non-root testing and fallback behavior

- The WAN manager will attempt to write the runtime state file to a system runtime path (for example `/var/run/azazel/wan_state.json`) when running as a system service. On systems where the process does not have permission to create `/var/run/azazel`, the manager now falls back automatically to a repository-local path `runtime/wan_state.json` so developers can run and test `azctl wan-manager` without root.
- For explicit control in tests or non-standard deployments, set `AZAZEL_WAN_STATE_PATH` to a writable path before running the manager. Example (development):

```bash
# write state into the repository runtime directory (no root required)
AZAZEL_WAN_STATE_PATH=runtime/wan_state.json python3 -m azctl.cli wan-manager --once
```

- For production systems, run the WAN manager via systemd (root) so that traffic-init, iptables/nft, and service restarts run with the required privileges. Example (recommended for deployed systems):

```bash
sudo systemctl enable --now azazel-wan-manager.service
```

These options allow safe developer testing while preserving the intended privileged behavior in production.

### Defensive Mode Operations

- **Portal Mode**: Baseline monitoring with minimal network impact
- **Shield Mode**: Activated by moderate threat scores; applies traffic shaping and enhanced logging
- **Lockdown Mode**: Triggered by high-severity alerts; restricts all traffic except medical/emergency FQDNs

Mode transitions are logged to `/var/log/azazel/decisions.log` with timestamps, scores, and triggering events.

## Documentation

### English Documentation

- [`docs/en/INSTALLATION.md`](docs/en/INSTALLATION.md) — Complete installation and setup guide
- [`docs/en/OPERATIONS.md`](docs/en/OPERATIONS.md) — Operational procedures and maintenance
- [`docs/en/NETWORK_SETUP.md`](docs/en/NETWORK_SETUP.md) — Network configuration and gateway setup
- [`docs/en/TROUBLESHOOTING.md`](docs/en/TROUBLESHOOTING.md) — Comprehensive problem resolution guide
- [`docs/en/EPD_SETUP.md`](docs/en/EPD_SETUP.md) — E-Paper display configuration
- [`docs/en/ARCHITECTURE.md`](docs/en/ARCHITECTURE.md) — System architecture and component relationships
- [`docs/en/API_REFERENCE.md`](docs/en/API_REFERENCE.md) — Python modules and script reference

## Development Background

Modern cyber attacks are increasingly fast and automated, making traditional honeypots insufficient. This system is designed not merely for **observation or blocking, but for tactical delay**—turning time into a defensive asset.

The core philosophy recognizes that in asymmetric cyber warfare, defenders often cannot prevent initial compromise but can control the attacker's subsequent actions. By implementing strategic delays and misdirection, Azazel creates opportunities for detection, analysis, and response.

### Developer notes and helper API

The `TrafficControlEngine` exposes two helpers to make testing and development easier:

- `TrafficControlEngine.set_subprocess_runner(runner_callable)`
   - Inject a custom subprocess runner in tests to simulate `tc`/`nft` outputs without running system commands.
   - The runner should accept `(cmd, **kwargs)` and return an object with attributes `returncode`, `stdout`, and `stderr` (a `subprocess.CompletedProcess` is ideal).
   - Example usage in tests:

      ```py
      from azazel_pi.core.enforcer.traffic_control import get_traffic_control_engine, make_completed_process

      engine = get_traffic_control_engine()
      engine.set_subprocess_runner(lambda cmd, **kw: make_completed_process(cmd, 0, stdout='ok'))
      ```

- `make_completed_process(cmd, returncode=0, stdout='', stderr='')`
   - Convenience factory (available at module level in `traffic_control.py`) to produce CompletedProcess-like objects for tests.

These APIs make it simple to unit-test enforcer behavior without requiring root or modifying the host network stack.

## What's New

### Enhanced AI Integration (v3) - November 2024

- **Multi-Tier Threat Analysis**: 3-stage evaluation system (Exception Blocking → Mock LLM → Ollama Deep Analysis)
- **Ollama Deep Learning**: Unknown threat analysis with qwen2.5-threat-v3 model (3-8s detailed analysis)
- **Enhanced JSON Processing**: 100% reliable JSON extraction with intelligent fallback mechanisms
- **Performance Optimization**: 0.0-0.2ms for known threats, 3-8s for unknown threats requiring deep analysis
- **Specification Compliance**: 100% verified conformance to threat routing specifications (2024-11-06)

### System Features

- **E-Paper Display Integration** (inspired by Azazel-Zero): Real-time status visualization showing current defensive mode, threat score, network status, and alert counters with boot/shutdown animations
- **Rich CLI Interface**: Terminal-based monitoring with color-coded mode indicators and live updates
- **Modular Configuration**: Declarative configuration system with JSON schema validation
- **Portable Design**: Optimized for field deployment and temporary network protection
- **Automated Provisioning**: Single-script installation with dependency management

### AI-Powered Threat Intelligence

```
Alert Detection Flow:
Alert → Exception Blocking (0.0ms) → Mock LLM (0.2ms) → Ollama Analysis (3-8s) → Response

Known Threats:    Instant blocking (Exception Blocking)
General Attacks:  Fast analysis (Mock LLM) 
Unknown Threats:  Deep analysis (Ollama) with Enhanced Fallback guarantee
```

## Deployment Status

**Current Status**: **95% Combat Ready** 🚀

### ✅ Operational Components

- **Traffic Control System**: tc delay injection (100ms/200ms/300ms) with integrated DNAT+QoS
- **Threat Detection**: Suricata IDS with real-time OpenCanary traffic diversion
- **Network Services**: WiFi AP (Azazel_Internal), DHCP/DNS, external network connectivity
- **Core Services**: azctl-unified (AI control daemon), vector log processing, opencanary honeypot
- **Auto-startup**: All critical services automatically start on boot

### 🔧 Remaining Items

- E-Paper display functionality (hardware-dependent, tracked in issues)

The system is **field-deployable** and provides complete malicious traffic delay capabilities with automatic threat detection and response.

## Message

> Defense is the art of buying time.
> 
> 防御とは、時間を稼ぐことである。

## License

MIT License

## Contributing

We welcome contributions to the Azazel-Pi project. Please see our [contribution guidelines](CONTRIBUTING.md) and submit pull requests for review.

## Security Disclosure

For security-related issues, please use GitHub's private vulnerability reporting or contact the maintainers directly.

---

*Azazel-Pi: Tactical cyber defense through strategic delay and deception*
