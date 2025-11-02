# Azazel-Pi - The Cyber Scapegoat Gateway

English | [日本語](README_ja.md)

![Azazel-Pi_image](images/azazel-pi-prototype.jpg)

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
- **Dynamic Traffic Control**: `tc` and `iptables/nftables` for tactical delay

#### Defensive Modes
- **Portal Mode** (Green): Normal operations with minimal restrictions
- **Shield Mode** (Yellow): Heightened monitoring with traffic shaping and QoS controls
- **Lockdown Mode** (Red): Full containment with strict firewall rules and allowlist-only communication

#### Status Display & Monitoring
- **E-Paper Display**: Real-time status visualization showing current defensive mode, threat score, network status, and alert counters
- **Rich CLI Interface**: Terminal-based status monitoring with color-coded mode indicators
- **Web Dashboard**: Mattermost integration for alerts and notifications

### Architecture Components

| Component | Purpose |
|-----------|---------|
| `azazel_pi/core/state_machine.py` | Governs transitions between defensive postures |
| `azazel_pi/core/actions/` | Models tc/nftables operations as idempotent plans |
| `azazel_pi/core/ingest/` | Parses Suricata EVE logs and OpenCanary events |
| `azazel_pi/core/display/` | E-Paper status visualization and rendering |
| `azctl/` | Command-line interface and daemon management |
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

### Portable Deployment
Lightweight configuration optimized for Raspberry Pi, enabling rapid deployment in disaster recovery, field operations, or temporary network setups.

## Technology Stack

- **Base OS**: Raspberry Pi OS (64-bit Lite)
- **IDS/IPS**: Suricata with custom rule sets
- **Honeypot**: OpenCanary for service deception
- **Log Processing**: Vector for centralized log collection
- **Traffic Control**: `tc` (Traffic Control) + `iptables/nftables`
- **Alerting**: Mattermost integration
- **Display**: Waveshare E-Paper with Python rendering
- **Languages**: Python 3.8+ with asyncio and rich libraries

## Installation

### Requirements
- Raspberry Pi 5 Model B (recommended) or compatible ARM64 device
- Raspberry Pi OS (64-bit Lite) or Debian-based distribution  
- Internet connection for dependency installation
- Administrator privileges (sudo access)
- Optional: Waveshare 2.13" E-Paper display for status visualization

### Quick Setup

After cloning the repository or downloading a release, run the automated installer as root:

```bash
cd Azazel-Pi
sudo scripts/install_azazel.sh
# To automatically start services after installation:
# sudo scripts/install_azazel.sh --start
```

The installer will:
- Install Suricata, Vector, OpenCanary, and other core components
- Deploy core modules and utilities to `/opt/azazel`
- Expand configuration templates to `/etc/azazel`
- Enable the `azctl.target` systemd service

Before starting services, edit `/etc/azazel/azazel.yaml` to configure interface names, QoS profiles, and defensive thresholds for your environment.

For complete installation instructions, troubleshooting, and E-Paper setup, see [`docs/INSTALLATION.md`](docs/INSTALLATION.md).

### E-Paper Display Setup (Optional)

If using a Waveshare E-Paper display:

```bash
# Install E-Paper dependencies
sudo scripts/install_epd.sh

# Test the display
sudo python3 -m azazel_pi.core.display.epd_daemon --mode test

# Enable the E-Paper service
sudo systemctl enable --now azazel-epd.service
```

See [`docs/EPD_SETUP.md`](docs/EPD_SETUP.md) for complete E-Paper configuration instructions.

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

### Configuration Workflow

1. **Edit Core Configuration**: Modify `/etc/azazel/azazel.yaml` to adjust delay values, bandwidth controls, and lockdown allowlists (template at `configs/network/azazel.yaml`)

2. **Generate Suricata Rules**: Use `scripts/suricata_generate.py` to render environment-specific IDS configurations

3. **Restart Services**: Apply changes with `sudo systemctl restart azctl.target`

4. **Health Check**: Verify service status using `scripts/sanity_check.sh`

5. **Monitor Operations**: Analyze scoring results in `decisions.log` and use `azctl` for manual mode switching during incidents

### Defensive Mode Operations

- **Portal Mode**: Baseline monitoring with minimal network impact
- **Shield Mode**: Activated by moderate threat scores; applies traffic shaping and enhanced logging
- **Lockdown Mode**: Triggered by high-severity alerts; restricts all traffic except medical/emergency FQDNs

Mode transitions are logged to `/var/log/azazel/decisions.log` with timestamps, scores, and triggering events.

## Documentation

- [`docs/INSTALLATION.md`](docs/INSTALLATION.md) — Complete installation and setup guide
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — Operational procedures and maintenance
- [`docs/NETWORK_SETUP.md`](docs/NETWORK_SETUP.md) — Network configuration and gateway setup
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — Comprehensive problem resolution guide
- [`docs/EPD_SETUP.md`](docs/EPD_SETUP.md) — E-Paper display configuration
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — System architecture and component relationships
- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) — Python modules and script reference

## Development Background

Modern cyber attacks are increasingly fast and automated, making traditional honeypots insufficient. This system is designed not merely for **observation or blocking, but for tactical delay**—turning time into a defensive asset.

The core philosophy recognizes that in asymmetric cyber warfare, defenders often cannot prevent initial compromise but can control the attacker's subsequent actions. By implementing strategic delays and misdirection, Azazel creates opportunities for detection, analysis, and response.

## What's New

- **E-Paper Display Integration** (inspired by Azazel-Zero): Real-time status visualization showing current defensive mode, threat score, network status, and alert counters with boot/shutdown animations
- **Rich CLI Interface**: Terminal-based monitoring with color-coded mode indicators and live updates
- **Modular Configuration**: Declarative configuration system with JSON schema validation
- **Portable Design**: Optimized for field deployment and temporary network protection
- **Automated Provisioning**: Single-script installation with dependency management

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