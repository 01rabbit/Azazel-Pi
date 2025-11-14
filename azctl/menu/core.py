#!/usr/bin/env python3
"""
Core Menu Framework

Provides the base menu system structure and data classes
for the Azazel TUI menu system.
"""

import subprocess
from azazel_pi.utils.cmd_runner import run as run_cmd
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any, Callable
import os

from rich.console import Console
from rich.text import Text
from rich.align import Align
from rich.panel import Panel
from rich.prompt import Prompt

# Import CLI functions
from azctl.cli import (
    _read_last_decision,
    _mode_style,
)

# Import types
from azctl.menu.types import MenuAction, MenuCategory

# Import status collector
try:
    from azazel_pi.core.ingest.status_collector import NetworkStatusCollector
except ImportError:
    NetworkStatusCollector = None


class AzazelTUIMenu:
    """Main TUI menu system for Azazel-Pi control interface."""
    
    def __init__(self, decisions_log: Optional[str] = None, lan_if: Optional[str] = None, wan_if: Optional[str] = None):
        self.console = Console()
        self.decisions_log = decisions_log
        # LAN precedence: explicit arg -> AZAZEL_LAN_IF env -> default wlan0
        self.lan_if = lan_if or os.environ.get("AZAZEL_LAN_IF") or "wlan0"
        # Resolve WAN interface default from explicit arg -> env -> helper -> fallback
        try:
            from azazel_pi.utils.wan_state import get_active_wan_interface
            self.wan_if = wan_if or os.environ.get("AZAZEL_WAN_IF") or get_active_wan_interface()
        except Exception:
            # Fallback to previous hardcoded default if resolution fails
            self.wan_if = wan_if or os.environ.get("AZAZEL_WAN_IF") or "wlan1"
        
        # Initialize status collector if available
        self.status_collector = None
        if NetworkStatusCollector:
            try:
                self.status_collector = NetworkStatusCollector()
            except Exception:
                pass
        
        # Initialize all modules (import here to avoid circular imports)
        from azctl.menu.network import NetworkModule
        from azctl.menu.defense import DefenseModule
        from azctl.menu.services import ServicesModule
        from azctl.menu.monitoring import MonitoringModule
        from azctl.menu.system import SystemModule
        from azctl.menu.emergency import EmergencyModule

        self.network_module = NetworkModule(self.console, self.lan_if, self.wan_if, self.status_collector)
        self.defense_module = DefenseModule(self.console, decisions_log=self.decisions_log, lan_if=self.lan_if, wan_if=self.wan_if)
        self.services_module = ServicesModule(self.console)
        self.monitoring_module = MonitoringModule(self.console)
        self.system_module = SystemModule(self.console, self.status_collector)
        self.emergency_module = EmergencyModule(self.console, self.lan_if, self.wan_if)
        
        # Setup menu categories
        self._setup_menu_categories()
    
    def _setup_menu_categories(self) -> None:
        """Setup menu categories and actions using pre-initialized modules."""
        self.categories = [
            self.defense_module.get_category(),
            self.services_module.get_category(),
            self.network_module.get_category(),
            self.monitoring_module.get_category(),
            self.system_module.get_category(),
            self.emergency_module.get_category(),
        ]
    
    def run(self) -> None:
        """Main menu loop."""
        try:
            while True:
                choice = self._display_main_menu()
                if choice == 'q':
                    self.console.print("\n[yellow]Exiting Azazel TUI Menu...[/yellow]")
                    break
                elif choice == 'r':
                    continue  # _display_main_menu will handle screen clearing
                    
                try:
                    category_idx = int(choice) - 1
                    if 0 <= category_idx < len(self.categories):
                        self._handle_category(self.categories[category_idx])
                    else:
                        self.console.print(f"[red]Invalid choice: {choice}[/red]")
                        self._pause()
                except ValueError:
                    self.console.print(f"[red]Invalid input: {choice}[/red]")
                    self._pause()
                    
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Interrupted by user. Exiting...[/yellow]")
        except Exception as e:
            self.console.print(f"[red]Unexpected error: {e}[/red]")
    
    def _show_banner(self) -> None:
        """Display the application banner."""
        # バージョン取得
        version = None
        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            try:
                # まずtomlで試みる
                try:
                    import toml
                    pyproject = toml.load(pyproject_path)
                    # poetry用とPEP 621用両方対応
                    version = pyproject.get("tool", {}).get("poetry", {}).get("version")
                    if not version:
                        version = pyproject.get("project", {}).get("version")
                except ImportError:
                    # tomlがなければ正規表現で取得
                    import re
                    with open(pyproject_path, "r") as f:
                        content = f.read()
                        m = re.search(r"^version\s*=\s*['\"]([^'\"]+)['\"]", content, re.MULTILINE)
                        if m:
                            version = m.group(1)
            except Exception:
                pass
        version_str = f"v{version}" if version else ""

        # バナーを複数行で構築
        from rich.table import Table
        banner_table = Table.grid(padding=0)
        banner_table.add_column(justify="center", width=55)
        
        # 1行目: タイトル（センター）
        banner_table.add_row(Text("🛡️  AZ-01X Azazel-Pi CONTROL INTERFACE", style="bold white"))
        
        # 2行目: バージョン（右揃え）
        if version_str:
            banner_table.add_row(Align.right(Text(version_str, style="dim white")))
        
        # 3行目: 空行
        banner_table.add_row("")
        
        # 4行目: サブタイトル（センター）
        banner_table.add_row(Text("The Cyber Scapegoat Gateway", style="dim white"))

        banner_panel = Panel(
            banner_table,
            border_style="cyan",
            padding=(1, 2),
            width=59
        )

        self.console.print(Align.center(banner_panel))
        self.console.print()

        # Show current status summary
        try:
            status = self._get_enhanced_status()
            # Use custom mode_display if available, otherwise use _mode_style
            if status.get("mode_display"):
                mode_label = status["mode_display"]
                # Determine color based on mode type - User Override uses base mode colors
                if "USER_PORTAL" in mode_label:
                    color = "green"  # グリーン
                elif "USER_SHIELD" in mode_label:
                    color = "yellow"  # イエロー
                elif "USER_LOCKDOWN" in mode_label:
                    color = "red"  # レッド
                elif "PORTAL" in mode_label:
                    color = "green"  # グリーン
                elif "SHIELD" in mode_label:
                    color = "yellow"  # イエロー
                elif "LOCKDOWN" in mode_label:
                    color = "red"  # レッド
                else:
                    color = "white"
            else:
                mode_label, color = _mode_style(status.get("mode"))

            # Create multi-line status display
            status_lines = [
                f"Mode: [{color}]{mode_label}[/{color}] | Profile: [cyan]{status.get('profile', 'N/A')}[/cyan] | Services: {status.get('services_active', 0)}/{status.get('services_total', 0)} active"
            ]

            # Add network information if available
            if status.get('wlan0_info'):
                wlan0 = status['wlan0_info']
                if wlan0.get('is_ap') and wlan0.get('stations') is not None:
                    status_lines.append(f"AP ({self.lan_if}): [green]Active[/green] | Clients: {wlan0['stations']}")
                else:
                    status_lines.append(f"AP ({self.lan_if}): [red]Inactive[/red]")

            if status.get('wlan1_info'):
                wlan1 = status['wlan1_info']
                if wlan1.get('connected') and wlan1.get('ssid'):
                    signal_info = f"{wlan1.get('signal_dbm')} dBm" if wlan1.get('signal_dbm') else 'N/A'
                    ip_info = wlan1.get('ip4', 'No IP')
                    status_lines.append(f"WAN ({self.wan_if}): [green]{wlan1['ssid']}[/green] | IP: [cyan]{ip_info}[/cyan] | Signal: {signal_info}")
                else:
                    status_lines.append(f"WAN ({self.wan_if}): [red]Disconnected[/red]")

            status_lines.append(f"Updated: {datetime.now().strftime('%H:%M:%S')}")

            status_panel = Panel(
                "\n".join(status_lines),
                title="System Status",
                border_style=color,
                padding=(0, 1)
            )
            self.console.print(Align.center(status_panel))
            self.console.print()
        except Exception:
            # If status fails, continue without it
            pass
    
    def _display_main_menu(self) -> str:
        """Display the main menu and get user choice."""
        # Clear screen and show banner/status before menu
        self.console.clear()
        self._show_banner()
        
        title = Text("Main Menu", style="bold blue")
        self.console.print(title)
        self.console.print(Text("─" * len("Main Menu"), style="blue"))
        
        for i, category in enumerate(self.categories, 1):
            self.console.print(f"[cyan]{i}.[/cyan] {category.title}")
            self.console.print(f"   [dim]{category.description}[/dim]")
            
        self.console.print()
        self.console.print("[cyan]r.[/cyan] Refresh screen")
        self.console.print("[cyan]q.[/cyan] Quit")
        self.console.print()
        
        return Prompt.ask("Select option", default="1")
    
    def _handle_category(self, category: MenuCategory) -> None:
        """Handle selection of a menu category."""
        while True:
            self.console.clear()
            self._show_category_header(category)
            
            choice = self._display_category_menu(category)
            if choice == 'b':
                break
            elif choice == 'r':
                continue
                
            try:
                action_idx = int(choice) - 1
                if 0 <= action_idx < len(category.actions):
                    action = category.actions[action_idx]
                    self._execute_action(action)
                else:
                    self.console.print(f"[red]Invalid choice: {choice}[/red]")
                    self._pause()
            except ValueError:
                self.console.print(f"[red]Invalid input: {choice}[/red]")
                self._pause()
    
    def _show_category_header(self, category: MenuCategory) -> None:
        """Show header for a category."""
        header = Panel.fit(
            f"[bold]{category.title}[/bold]\n{category.description}",
            title="Category",
            border_style="blue"
        )
        self.console.print(header)
        self.console.print()
    
    def _display_category_menu(self, category: MenuCategory) -> str:
        """Display actions in a category and get user choice."""
        for i, action in enumerate(category.actions, 1):
            # Add indicators for special actions
            indicators = []
            if action.requires_root:
                indicators.append("[red]🔒[/red]")
            if action.dangerous:
                indicators.append("[red]⚠️[/red]")
            
            indicator_str = " ".join(indicators)
            if indicator_str:
                indicator_str = " " + indicator_str
            
            self.console.print(f"[cyan]{i}.[/cyan] {action.title}{indicator_str}")
            self.console.print(f"   [dim]{action.description}[/dim]")
            
        self.console.print()
        self.console.print("[cyan]r.[/cyan] Refresh")
        self.console.print("[cyan]b.[/cyan] Back to main menu")
        self.console.print()
        
        return Prompt.ask("Select option", default="b")
    
    def _execute_action(self, action: MenuAction) -> None:
        """Execute a menu action with safety checks."""
        # Root permission check
        if action.requires_root and not self._check_root():
            self.console.print("[red]This action requires root privileges. Please run with sudo.[/red]")
            self._pause()
            return
        
        # Dangerous action confirmation
        if action.dangerous:
            from rich.prompt import Confirm
            if not Confirm.ask(f"[red]Warning: {action.title} is a potentially dangerous operation. Continue?[/red]"):
                return
        
        try:
            self.console.print(f"[blue]Executing: {action.title}[/blue]")
            action.action()
        except Exception as e:
            self.console.print(f"[red]Error executing {action.title}: {e}[/red]")
            self._pause()
    
    def _check_root(self) -> bool:
        """Check if running with root privileges."""
        import os
        return os.geteuid() == 0
    
    def _pause(self) -> None:
        """Pause for user input."""
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="", show_default=False)
    
    def _print_section_header(self, title: str, style: str = "bold") -> None:
        """Print a consistent section header with underline."""
        title_text = Text(title, style=style)
        self.console.print(title_text)
        self.console.print(Text("─" * len(title), style="dim"))
    
    def _get_current_status(self) -> Dict[str, Any]:
        """Get current system status summary."""
        # Try to get real-time status from running daemon or state files
        mode = None
        mode_display = None
        
        # Check for state files or daemon status
        state_files = [
            "/tmp/azazel_state.json",
            "/var/run/azazel_state.json",
            "/tmp/azazel_user_command.yaml"
        ]
        
        for state_file in state_files:
            try:
                if Path(state_file).exists():
                    import json
                    import yaml
                    
                    if state_file.endswith('.json'):
                        with open(state_file, 'r') as f:
                            state_data = json.load(f)
                    else:
                        with open(state_file, 'r') as f:
                            state_data = yaml.safe_load(f)
                    
                    if state_data and isinstance(state_data, dict):
                        if 'command' in state_data and state_data['command'] == 'user_override':
                            # This is a user override command file
                            override_mode = state_data.get('mode', 'unknown')
                            duration = state_data.get('duration_minutes', 3)
                            timestamp = state_data.get('timestamp', 0)
                            
                            import time
                            elapsed = time.time() - timestamp
                            remaining = max(0, (duration * 60) - elapsed)
                            
                            if remaining > 0:
                                mode = f"user_{override_mode}"
                                mode_display = f"USER_{override_mode.upper()} ({remaining:.0f}s)"
                            break
                        elif 'state' in state_data and state_data.get('user_mode'):
                            # This is a state file with user mode info
                            mode = state_data['state']
                            base_mode = state_data.get('base_mode', 'unknown')
                            timeout_timestamp = state_data.get('timeout_timestamp', 0)
                            
                            import time
                            remaining = max(0, timeout_timestamp - time.time())
                            
                            if remaining > 0:
                                mode_display = f"USER_{base_mode.upper()} ({remaining:.0f}s)"
                            else:
                                # Timeout expired, clean up
                                try:
                                    import os
                                    os.unlink(state_file)
                                except:
                                    pass
                                mode = base_mode
                                mode_display = base_mode.upper()
                            break
                        elif 'state' in state_data:
                            mode = state_data['state']
                            mode_display = mode.upper()
                            break
            except Exception:
                continue
        
        # If no state file found, try to get from a new state machine instance
        if not mode:
            try:
                from azctl.cli import build_machine
                machine = build_machine()
                summary = machine.summary()
                current_mode = summary.get("state", "unknown")
                is_user_mode = summary.get("user_mode") == "true"
                
                if is_user_mode:
                    timeout_remaining = float(summary.get("user_timeout_remaining", "0"))
                    base_mode = machine.get_base_mode()
                    mode = f"user_{base_mode}"
                    mode_display = f"USER_{base_mode.upper()} ({timeout_remaining:.0f}s)"
                else:
                    mode = current_mode
                    mode_display = current_mode.upper()
                    
            except Exception:
                # Final fallback to decision log status
                decision_paths = [
                    Path(self.decisions_log) if self.decisions_log else None,
                    Path("/var/log/azazel/decisions.log"),
                    Path("decisions.log"),
                ]
                decision_paths = [p for p in decision_paths if p is not None]
                
                last_decision = _read_last_decision(decision_paths)
                mode = last_decision.get("mode") if last_decision else None
                mode_display = mode.upper() if mode else "UNKNOWN"
        
        # Count active services (simplified)
        systemd_services = ["suricata", "vector", "azctl"]
        services_active = 0
        for service in systemd_services:
            try:
                result = run_cmd(
                    ["systemctl", "is-active", service],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip() == "active":
                    services_active += 1
            except Exception:
                pass
        
        services_total = len(systemd_services) + 1  # include OpenCanary container
        if self._is_container_running("azazel_opencanary"):
            services_active += 1
            
        return {
            "mode": mode,
            "mode_display": mode_display if 'mode_display' in locals() else (mode.upper() if mode else "UNKNOWN"),
            "services_active": services_active,
            "services_total": services_total,
        }
    
    def _get_enhanced_status(self) -> Dict[str, Any]:
        """Get enhanced system status with network information."""
        # Get basic status
        basic_status = self._get_current_status()
        
        # Get network profile
        from azazel_pi.utils.network_utils import get_active_profile, get_wlan_ap_status, get_wlan_link_info
        profile = get_active_profile()
        
        # Get WLAN interface information
        wlan0_info = get_wlan_ap_status(self.lan_if)
        wlan1_info = get_wlan_link_info(self.wan_if)
        
        return {
            **basic_status,
            "profile": profile,
            "wlan0_info": wlan0_info,
            "wlan1_info": wlan1_info,
        }

    def _is_container_running(self, container_name: str) -> bool:
        """Check whether a Docker container is running."""
        try:
            result = run_cmd(
                ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0 and (result.stdout or "").strip().lower() == "true"
        except Exception:
            return False
