# API Reference

This reference documents the Python modules that make up the Azazel control
plane. The intent is to provide enough context for operators to extend or mock
the behaviour during testing.

## `azctl.menu` - Modular TUI Menu System

Azazel-Pi provides a modular Terminal User Interface designed for maintainability and extensibility.

### Architecture

```
azctl/menu/
├── __init__.py      # Module entry point
├── types.py         # Common data class definitions
├── core.py          # Main framework
├── defense.py       # Defense control module
├── services.py      # Service management module
├── network.py       # Network information module
├── wifi.py          # WiFi management module
├── monitoring.py    # Log monitoring module
├── system.py        # System information module
└── emergency.py     # Emergency operations module
```

### Basic Data Types (`types.py`)

#### `MenuAction`
Data class representing a menu action item.

**Properties:**
- `title: str` - Display title
- `description: str` - Detailed description
- `action: Callable` - Function to execute
- `requires_root: bool` - Whether root privileges required (default: False)
- `dangerous: bool` - Whether operation is dangerous (default: False)

**Usage Example:**
```python
from azctl.menu.types import MenuAction

action = MenuAction(
    title="Mode Switch",
    description="Manually change defense mode",
    action=lambda: switch_mode("shield"),
    requires_root=True,
    dangerous=True
)
```

#### `MenuCategory`
Data class representing a menu category containing multiple actions.

**Properties:**
- `title: str` - Category title
- `description: str` - Category description
- `actions: list[MenuAction]` - List of contained actions

**Usage Example:**
```python
from azctl.menu.types import MenuCategory, MenuAction

category = MenuCategory(
    title="Defense Control",
    description="Defense system monitoring and control",
    actions=[
        MenuAction("Show Status", "Display system status", show_status),
        MenuAction("Switch Mode", "Change defense mode", switch_mode)
    ]
)
```

### Core Framework (`core.py`)

#### `AzazelTUIMenu`
Main TUI menu system class.

**Initialization:**
```python
AzazelTUIMenu(
    decisions_log: Optional[str] = None,
    lan_if: str = "wlan0", 
    wan_if: str = "wlan1"
)
```

**Parameters:**
- `decisions_log` - Path to decision log file
- `lan_if` - LAN interface name
- `wan_if` - WAN interface name

**Methods:**

##### `run()`
Start the main TUI loop.

**Usage Example:**
```python
from azctl.menu import AzazelTUIMenu

menu = AzazelTUIMenu(lan_if="wlan0", wan_if="wlan1")
menu.run()
```

### Functional Modules

#### Defense Control Module (`defense.py`)

##### `DefenseModule`
Provides defense system monitoring and control.

**Features:**
- Current defense mode display
- Manual mode switching
- Decision history display
- Real-time threat score monitoring

**Usage Example:**
```python
from azctl.menu.defense import DefenseModule
from rich.console import Console

module = DefenseModule(Console())
category = module.get_category()
```

#### Service Management Module (`services.py`)

##### `ServicesModule`
Manages Azazel system services.

**Managed Services:**
- `azctl-unified.service` - Unified control daemon
- `azctl-unified.service` - HTTP server
- `suricata.service` - IDS/IPS
- `opencanary.service` - Honeypot
- `vector.service` - Log collection
- `azazel-epd.service` - E-Paper display

**Features:**
- Service status listing
- Service start/stop/restart
- Real-time log viewing
- System-wide health checks

#### Network Information Module (`network.py`)

##### `NetworkModule`
Provides network status and WiFi management integration.

**Features:**
- Interface status display
- Active profile confirmation
- WiFi management integration
- Network traffic statistics

#### WiFi Management Module (`wifi.py`)

##### `WiFiManager`
Comprehensive WiFi network management.

**Features:**
- Nearby WiFi network scanning
- WPA/WPA2 network connection
- Saved network management
- Connection status and signal strength display
- Interactive SSID selection and password input

**Technical Specifications:**
- Uses `iw scan` for network discovery
- Uses `wpa_cli` for connection management
- Rich UI with tabular display
- Automatic security type detection

#### Log Monitoring Module (`monitoring.py`)

##### `MonitoringModule`
Security and system log monitoring.

**Monitored Sources:**
- Suricata alert logs (`/var/log/suricata/eve.json`)
- OpenCanary event logs
- Azazel decision logs (`/var/log/azazel/decisions.log`)
- System journal

**Features:**
- Real-time log monitoring
- Alert summary and counting
- Log file history display
- Security event analysis

#### System Information Module (`system.py`)

##### `SystemModule`
System resource and hardware status monitoring.

**Monitored Items:**
- CPU usage and processor information
- Memory usage (physical/swap)
- Disk usage
- Network interface statistics
- System temperature (Raspberry Pi)
- Running process list

#### Emergency Operations Module (`emergency.py`)

##### `EmergencyModule`
Emergency response operations.

**Features:**
- **Emergency Lockdown**: Immediately block network access
- **Network Configuration Reset**: Reset WiFi settings to defaults
- **System Report Generation**: Create comprehensive status report
- **Factory Reset**: Reset entire system to initial state

**Safety Features:**
- Multi-stage confirmation dialogs
- Danger level-based warnings
- Automatic operation logging
- Interruptible operation flows

### Custom Module Creation

Example of adding a new functional module:

```python
# azctl/menu/custom.py
from rich.console import Console
from .types import MenuCategory, MenuAction

class CustomModule:
    def __init__(self, console: Console):
        self.console = console
    
    def get_category(self) -> MenuCategory:
        return MenuCategory(
            title="Custom Features",
            description="Custom feature management",
            actions=[
                MenuAction(
                    title="Custom Operation",
                    description="Execute custom operation",
                    action=self._custom_action
                )
            ]
        )
    
    def _custom_action(self):
        self.console.print("[green]Executing custom operation...[/green]")
```

### Integration and Testing

```python
# Integrate new module into core system
# Add to azctl/menu/core.py _setup_menu_categories()

from .custom import CustomModule

# In __init__ method
self.custom_module = CustomModule(self.console)

# In _setup_menu_categories method
self.categories.append(self.custom_module.get_category())
```

## `azazel_core.state_machine`

- `State(name: str, description: str = "")`
- `Event(name: str, severity: int = 0)`
- `Transition(source, target, condition, action=None)`
- `StateMachine(initial_state, config_path=None, window_size=5)` provides:
  - `add_transition(transition)` – register a new transition.
  - `dispatch(event)` – evaluate transitions from the current state.
  - `reset()` – return to the initial state and clear score history.
  - `summary()` – dictionary suitable for API responses.
  - `get_thresholds()` – read shield/lockdown thresholds and unlock timers
    from `azazel.yaml`.
  - `get_actions_preset()` – fetch the delay/shape/block preset for the
    current mode.
  - `apply_score(severity)` – update the moving-average score window,
    transition to the correct mode, and return evaluation metadata.

## `azazel_core.scorer`

`ScoreEvaluator` computes cumulative severity and provides `classify(score)`
which returns `normal`, `guarded`, `elevated`, or `critical`.

## `azazel_core.actions`

`DelayAction`, `ShapeAction`, `BlockAction`, and `RedirectAction` derive from the
common `Action` interface and expose `plan(target)` iterators. Each yields
`ActionResult` objects that describe tc/nftables commands without executing
side-effects.

## `azazel_core.ingest`

`SuricataTail` and `CanaryTail` read JSON logs from disk and emit `Event`
instances. They are intentionally deterministic, easing unit test coverage.

## `azazel_core.api`

`APIServer` is a minimal dispatcher used by future HTTP front-ends. The bundled
handler `add_health_route(version)` returns a `HealthResponse` dataclass.

## `azctl.cli`

`build_machine()` wires the portal/shield/lockdown states. `load_events(path)`
loads YAML describing synthetic events. `main(argv)` powers the systemd service
by feeding events into `AzazelDaemon`, which applies score-based decisions and
writes `decisions.log` entries containing the chosen mode and action presets.

## HTTP endpoints

### `POST /v1/mode`

The controller exposes a minimal HTTP interface for supervised overrides. A
`POST` request to `/v1/mode` with a JSON body such as `{ "mode": "shield" }`
will transition the daemon to the requested state. The handler immediately
applies the corresponding preset from `azazel.yaml` (delay, shaping rate, and
block flag) and records the outcome to `decisions.log` alongside operator
metadata. Preset values are documented in the operations guide's
[mode action table](OPERATIONS.md#mode-presets).

## Scripts

- `scripts/suricata_generate.py` renders the Suricata YAML template.
- `scripts/nft_apply.sh` and `scripts/tc_reset.sh` manage enforcement tools.
- `scripts/sanity_check.sh` prints warnings if dependent services are inactive.
- `scripts/rollback.sh` removes installed assets.
- `scripts/resolve_allowlist.py` resolves medical FQDNs to CIDRs and writes the
  lockdown nftables allowlist used by the generated template.
