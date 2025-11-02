#!/usr/bin/env python3
"""
Core Menu Framework

Provides the base menu system structure and data classes
for the Azazel TUI menu system.
"""

import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any, Callable

from rich.console import Console
from rich.text import Text
from rich.align import Align
from rich.panel import Panel
from rich.prompt import Prompt

# Import CLI functions
from ..cli import (
    _read_last_decision,
    _mode_style,
    _wlan_ap_status,
    _wlan_link_info,
    _active_profile,
)

# Import types
from .types import MenuAction, MenuCategory

# Import status collector
try:
    from ..core.ingest.status_collector import NetworkStatusCollector
except ImportError:
    NetworkStatusCollector = None


class AzazelTUIMenu:
    """Main TUI menu system for Azazel-Pi control interface."""
    
    def __init__(self, decisions_log: Optional[str] = None, lan_if: str = "wlan0", wan_if: str = "wlan1"):
        self.console = Console()
        self.decisions_log = decisions_log
        self.lan_if = lan_if
        self.wan_if = wan_if
        
        # Initialize status collector if available
        self.status_collector = None
        if NetworkStatusCollector:
            try:
                self.status_collector = NetworkStatusCollector()
            except Exception:
                pass
        
        # Initialize all modules (import here to avoid circular imports)
        from .network import NetworkModule
        from .defense import DefenseModule 
        from .services import ServicesModule
        from .monitoring import MonitoringModule
        from .system import SystemModule
        from .emergency import EmergencyModule
        
        self.network_module = NetworkModule(self.console, self.lan_if, self.wan_if)
        self.defense_module = DefenseModule(self.console)
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
            self._show_banner()
            
            while True:
                choice = self._display_main_menu()
                if choice == 'q':
                    self.console.print("\n[yellow]Exiting Azazel TUI Menu...[/yellow]")
                    break
                elif choice == 'r':
                    self.console.clear()
                    self._show_banner()
                    continue
                    
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
        banner_content = Text.assemble(
            ("🛡️  AZAZEL-PI CONTROL INTERFACE", "bold white"), ("\n\n", ""),
            ("The Cyber Scapegoat Gateway", "dim white")
        )
        
        banner_panel = Panel(
            Align.center(banner_content),
            border_style="cyan",
            padding=(1, 2),
            width=59
        )
        
        self.console.print(Align.center(banner_panel))
        self.console.print()
        
        # Show current status summary
        try:
            status = self._get_enhanced_status()
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
        self.console.print()
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
        # Get decision log status
        decision_paths = [
            Path(self.decisions_log) if self.decisions_log else None,
            Path("/var/log/azazel/decisions.log"),
            Path("decisions.log"),
        ]
        decision_paths = [p for p in decision_paths if p is not None]
        
        last_decision = _read_last_decision(decision_paths)
        mode = last_decision.get("mode") if last_decision else None
        
        # Count active services (simplified)
        services = ["suricata", "opencanary", "vector", "azctl"]
        services_active = 0
        for service in services:
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip() == "active":
                    services_active += 1
            except Exception:
                pass
        
        return {
            "mode": mode,
            "services_active": services_active,
            "services_total": len(services),
        }
    
    def _get_enhanced_status(self) -> Dict[str, Any]:
        """Get enhanced system status with network information."""
        # Get basic status
        basic_status = self._get_current_status()
        
        # Get network profile
        profile = _active_profile()
        
        # Get WLAN interface information
        wlan0_info = _wlan_ap_status(self.lan_if)
        wlan1_info = _wlan_link_info(self.wan_if)
        
        return {
            **basic_status,
            "profile": profile,
            "wlan0_info": wlan0_info,
            "wlan1_info": wlan1_info,
        }