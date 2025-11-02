# Azazel Architecture

Azazel packages the SOC/NOC control plane into a self-contained repository. The
solution is designed so a clean Raspberry Pi image can pull a tagged release and
become operational without ad-hoc configuration.

## Core services

| Component | Purpose |
|-----------|---------|
| `azazel_core/state_machine.py` | Governs transitions between posture states. |
| `azazel_core/actions/` | Models tc/nftables operations as idempotent plans. |
| `azazel_core/ingest/` | Parses Suricata EVE logs and OpenCanary events. |
| `azazel_core/qos/` | Maps profiles to QoS enforcement classes. |
| `azctl/` | Thin CLI/daemon interface used by systemd. |
| `azctl/menu/` | Modular TUI menu system for comprehensive system management. |
| `configs/` | Declarative configuration set including schema validation. |
| `scripts/install_azazel.sh` | Provisioning script that stages the runtime and dependencies. |
| `systemd/` | Units and targets that compose the Azazel service stack. |

## State machine overview

The state machine promotes or demotes the defensive posture based on the score
calculated from incoming alerts. Three stages are modelled:

1. **Idle** – default, minimal restrictions.
2. **Shield** – elevated monitoring, tc shaping applied.
3. **Lockdown** – optional stage triggered by high scores where nftables rules
   restrict ingress to trusted ranges.

The scoring logic lives in `azazel_core/scorer.py` and is exercised by the unit
tests under `tests/unit`.

## Configuration

All runtime parameters are stored inside `configs/azazel.yaml`. A JSON Schema is
published in `configs/azazel.schema.json` and enforced in CI. Vendor
applications—Suricata, Vector, OpenCanary, nftables and tc—are provided with
opinionated defaults that can be adapted per deployment.

## TUI Menu System Architecture

### Modular Design

Azazel-Pi employs a modular TUI menu system designed for maintainability and extensibility:

```
azctl/menu/
├── __init__.py       # Entry point
├── types.py          # Common data types (MenuAction, MenuCategory)
├── core.py           # Main framework (AzazelTUIMenu)
├── defense.py        # Defense control module
├── services.py       # Service management module
├── network.py        # Network information integration module
├── wifi.py           # WiFi management specialized module
├── monitoring.py     # Log monitoring module
├── system.py         # System information module
└── emergency.py      # Emergency operations module
```

### Design Principles

#### 1. Separation of Concerns
Each module has a clearly defined single responsibility:

```python
# Example: WiFi management module
class WiFiManager:
    """Specialized for WiFi network management"""
    def scan_networks(self) -> List[Network]: pass
    def connect_to_network(self, ssid: str, password: str): pass
    def get_saved_networks(self) -> List[Network]: pass
```

#### 2. Type Safety
Common data types are defined in `types.py` to avoid circular imports:

```python
@dataclass
class MenuAction:
    title: str
    description: str
    action: Callable
    requires_root: bool = False
    dangerous: bool = False

@dataclass 
class MenuCategory:
    title: str
    description: str
    actions: list[MenuAction]
```

#### 3. Dependency Injection
Each module receives Console objects as injection, making them independently testable:

```python
class DefenseModule:
    def __init__(self, console: Console):
        self.console = console
        
    def get_category(self) -> MenuCategory:
        return MenuCategory(
            title="Defense Control",
            description="Defense system monitoring and control",
            actions=self._build_actions()
        )
```

### TUI Menu Execution Flow

```
User Launch → Main Menu → Category Selection → Action Execution → Result Display
     ↓              ↓            ↓            ↓            ↓
┌─────────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐
│azctl.cli    │ │AzazelTUI │ │Module    │ │Action   │ │Rich      │
│menu command │ │Menu.run()│ │Category  │ │Function │ │Console   │
└─────────────┘ └──────────┘ └──────────┘ └─────────┘ └──────────┘
```

### Menu Rendering Architecture

Consistent UI display using Rich library:

```python
# Unified section header display
def _print_section_header(self, title: str, subtitle: str = ""):
    panel = Panel(
        Align.center(f"[bold]{title}[/bold]\n{subtitle}"),
        border_style="blue",
        padding=(1, 2)
    )
    self.console.print(panel)
```

### Extension System

Adding new menu modules is straightforward:

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

# Integration in core system
# Add to azctl/menu/core.py:
from .custom import CustomModule

class AzazelTUIMenu:
    def __init__(self, ...):
        # ...
        self.custom_module = CustomModule(self.console)
    
    def _setup_menu_categories(self):
        self.categories.append(self.custom_module.get_category())
```

## Packaging goal

`install_azazel.sh` installs Azazel onto `/opt/azazel`, copies configuration
and systemd units into place, and ensures Debian dependencies are present. The
repository layout mirrors the staged filesystem, ensuring releases are
reproducible. Tagging a commit triggers the release workflow that builds
`azazel-installer-<tag>.tar.gz` containing the entire payload required for
air-gapped installs.
