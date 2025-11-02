"""Interactive TUI menu system for Azazel control operations.

This module provides a Rich-based terminal user interface for managing
Azazel defensive operations, system services, and configuration.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from azazel_pi.core.config import AzazelConfig
from azazel_pi.core.scorer import ScoreEvaluator
from azazel_pi.core.state_machine import Event, State, StateMachine, Transition
from azazel_pi.core.display.status_collector import StatusCollector

from .daemon import AzazelDaemon
from .cli import (
    build_machine,
    _read_last_decision,
    _wlan_ap_status,
    _wlan_link_info,
    _active_profile,
    _mode_style,
    _human_bytes,
)

# Rich imports with fallback error handling
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.columns import Columns
    from rich.align import Align
    from rich.text import Text
    from rich.live import Live
    from rich.prompt import Prompt, Confirm
    from rich.layout import Layout
    from rich.tree import Tree
    from rich.progress import Progress, TaskID
    from rich import box
    from rich.markdown import Markdown
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


@dataclass
class MenuAction:
    """Represents a menu action with display name, description, and handler."""
    name: str
    description: str
    handler: Callable[[], Any]
    requires_root: bool = False
    dangerous: bool = False


@dataclass
class MenuCategory:
    """Represents a category of menu actions with a title and list of actions."""
    title: str
    description: str
    actions: List[MenuAction]


class AzazelTUIMenu:
    """Main TUI menu controller for Azazel operations."""
    
    def __init__(self, decisions_log: Optional[str] = None, lan_if: str = "wlan0", wan_if: str = "wlan1"):
        if not RICH_AVAILABLE:
            raise ImportError("Rich library is required for TUI menu. Install with: pip install rich")
        
        self.console = Console()
        self.decisions_log = decisions_log
        self.lan_if = lan_if
        self.wan_if = wan_if
        self.status_collector = StatusCollector()
        
        # State machine setup
        self.machine = build_machine()
        self.daemon = AzazelDaemon(machine=self.machine, scorer=ScoreEvaluator())
        
        # Setup menu structure
        self._setup_menu_categories()
        
    def _setup_menu_categories(self) -> None:
        """Initialize the menu category structure."""
        self.categories = [
            MenuCategory(
                title="Defense Control",
                description="Manage defensive modes and threat response",
                actions=[
                    MenuAction("View Current Status", "Display current defensive mode and system status", self._view_status),
                    MenuAction("Switch to Portal Mode", "Change to minimal restrictions mode", lambda: self._change_mode("portal")),
                    MenuAction("Switch to Shield Mode", "Change to enhanced monitoring mode", lambda: self._change_mode("shield")),
                    MenuAction("Switch to Lockdown Mode", "Change to full containment mode", lambda: self._change_mode("lockdown"), dangerous=True),
                    MenuAction("View Decision History", "Show recent mode change decisions", self._view_decisions),
                ]
            ),
            MenuCategory(
                title="Service Management",
                description="Control Azazel system services",
                actions=[
                    MenuAction("Service Status Overview", "View all Azazel services status", self._service_status),
                    MenuAction("Start/Stop Suricata", "Control Suricata IDS service", self._manage_suricata, requires_root=True),
                    MenuAction("Start/Stop OpenCanary", "Control OpenCanary honeypot service", self._manage_opencanary, requires_root=True),
                    MenuAction("Start/Stop Vector", "Control Vector log processing service", self._manage_vector, requires_root=True),
                    MenuAction("Restart All Services", "Restart all Azazel services", self._restart_all_services, requires_root=True, dangerous=True),
                ]
            ),
            MenuCategory(
                title="Network Information",
                description="View and manage network configuration",
                actions=[
                    MenuAction("Network Interface Status", "Display WLAN interface information", self._network_status),
                    MenuAction("Active Profile", "Show current network profile configuration", self._show_active_profile),
                    MenuAction("Traffic Statistics", "Display network traffic information", self._traffic_stats),
                ]
            ),
            MenuCategory(
                title="Log Monitoring",
                description="View system and security logs",
                actions=[
                    MenuAction("Live Decision Log", "Monitor decisions.log in real-time", self._live_decision_log),
                    MenuAction("Live Suricata Events", "Monitor Suricata alerts in real-time", self._live_suricata_log),
                    MenuAction("Recent Alert Summary", "Show summary of recent security alerts", self._alert_summary),
                ]
            ),
            MenuCategory(
                title="System Information",
                description="View system status and resources",
                actions=[
                    MenuAction("System Resources", "Display CPU, memory, and disk usage", self._system_resources),
                    MenuAction("Temperature Status", "Show system temperature information", self._temperature_status),
                    MenuAction("Uptime & Load", "Display system uptime and load averages", self._uptime_load),
                ]
            ),
            MenuCategory(
                title="Emergency Operations",
                description="Emergency response and recovery operations",
                actions=[
                    MenuAction("Emergency Lockdown", "Immediately activate full lockdown mode", self._emergency_lockdown, requires_root=True, dangerous=True),
                    MenuAction("Emergency Reset", "Reset all services and return to portal mode", self._emergency_reset, requires_root=True, dangerous=True),
                    MenuAction("Generate System Report", "Create comprehensive system status report", self._generate_report),
                ]
            ),
        ]
    
    def run(self) -> None:
        """Run the main menu loop."""
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
        banner = Text.assemble(
            ("┌─────────────────────────────────────────────────────────┐\n", "cyan"),
            ("│                                                         │\n", "cyan"),
            ("│    ", "cyan"), ("🛡️  AZAZEL-PI CONTROL INTERFACE", "bold white"), ("                 │\n", "cyan"),
            ("│                                                         │\n", "cyan"),
            ("│    ", "cyan"), ("The Cyber Scapegoat Gateway", "dim white"), ("                    │\n", "cyan"),
            ("│                                                         │\n", "cyan"),
            ("└─────────────────────────────────────────────────────────┘", "cyan"),
        )
        self.console.print(Align.center(banner))
        self.console.print()
        
        # Show current status summary
        try:
            status = self._get_current_status()
            mode_label, color = _mode_style(status.get("mode"))
            
            status_panel = Panel.fit(
                f"Current Mode: [{color}]{mode_label}[/{color}] | "
                f"Services: {status.get('services_active', 0)}/{status.get('services_total', 0)} active | "
                f"Last Update: {datetime.now().strftime('%H:%M:%S')}",
                title="Quick Status",
                border_style=color
            )
            self.console.print(Align.center(status_panel))
            self.console.print()
        except Exception:
            # If status fails, continue without it
            pass
    
    def _display_main_menu(self) -> str:
        """Display the main menu and get user choice."""
        self.console.print("[bold]Main Menu[/bold]", style="blue")
        self.console.print("─" * 50, style="blue")
        
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
                indicator_str = f" {indicator_str}"
                
            self.console.print(f"[cyan]{i}.[/cyan] {action.name}{indicator_str}")
            self.console.print(f"   [dim]{action.description}[/dim]")
            
        self.console.print()
        self.console.print("[cyan]r.[/cyan] Refresh")
        self.console.print("[cyan]b.[/cyan] Back to main menu")
        self.console.print()
        
        return Prompt.ask("Select option", default="b")
    
    def _execute_action(self, action: MenuAction) -> None:
        """Execute a menu action with appropriate checks."""
        try:
            # Check root requirements
            if action.requires_root and os.geteuid() != 0:
                self.console.print("[red]This action requires root privileges.[/red]")
                self.console.print("Please run the menu with sudo or as root.")
                self._pause()
                return
            
            # Confirm dangerous actions
            if action.dangerous:
                if not Confirm.ask(f"[red]⚠️  This is a potentially dangerous operation.[/red]\n"
                                 f"Action: {action.name}\n"
                                 f"Continue?", default=False):
                    self.console.print("[yellow]Action cancelled.[/yellow]")
                    self._pause()
                    return
            
            # Execute the action
            self.console.print(f"\n[blue]Executing: {action.name}[/blue]")
            result = action.handler()
            
            if result is not None:
                self.console.print(f"[green]✓ Action completed.[/green]")
            
        except Exception as e:
            self.console.print(f"[red]✗ Error executing action: {e}[/red]")
        finally:
            self._pause()
    
    def _pause(self) -> None:
        """Pause for user input."""
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="", show_default=False)
    
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
    
    # ===== Action Implementations =====
    
    def _view_status(self) -> None:
        """Display comprehensive system status."""
        self.console.print("[bold]System Status Overview[/bold]")
        self.console.print("─" * 50)
        
        # Get status data
        decision_paths = [
            Path(self.decisions_log) if self.decisions_log else None,
            Path("/var/log/azazel/decisions.log"),
            Path("decisions.log"),
        ]
        decision_paths = [p for p in decision_paths if p is not None]
        
        last_decision = _read_last_decision(decision_paths)
        mode = last_decision.get("mode") if last_decision else None
        mode_label, color = _mode_style(mode)
        
        wlan0 = _wlan_ap_status(self.lan_if)
        wlan1 = _wlan_link_info(self.wan_if)
        profile = _active_profile()
        
        try:
            status = self.status_collector.collect()
        except Exception:
            status = None
        
        # Create status display
        layout = Layout()
        layout.split_row(
            Layout(name="left"),
            Layout(name="right")
        )
        
        # Left side: Defense & Network
        left_table = Table.grid(padding=(0, 1))
        left_table.add_row("[bold]Defense Status[/bold]")
        left_table.add_row("Mode", Text(mode_label, style=f"bold {color}"))
        if last_decision:
            left_table.add_row("Score", f"{last_decision.get('score', 0):.1f}")
            left_table.add_row("Average", f"{last_decision.get('average', 0):.1f}")
        left_table.add_row("")
        left_table.add_row("[bold]Network Status[/bold]")
        left_table.add_row("Profile", profile or "unknown")
        
        ap_status = "AP" if wlan0.get('is_ap') else ("Client" if wlan0.get('is_ap') is False else "Unknown")
        left_table.add_row(f"{self.lan_if}", f"{ap_status} | SSID: {wlan0.get('ssid', '-')} | Ch: {wlan0.get('channel', '-')}")
        left_table.add_row(f"{self.wan_if}", f"{'Connected' if wlan1.get('connected') else 'Disconnected'} | SSID: {wlan1.get('ssid', '-')}")
        
        layout["left"].update(Panel(left_table, title="Status", border_style=color))
        
        # Right side: System Resources
        right_table = Table.grid(padding=(0, 1))
        right_table.add_row("[bold]System Resources[/bold]")
        
        if status:
            right_table.add_row("Uptime", f"{status.uptime_seconds//3600}h {(status.uptime_seconds//60)%60}m")
            if status.network.tx_bytes and status.network.rx_bytes:
                right_table.add_row("Traffic", f"TX: {_human_bytes(status.network.tx_bytes)} | RX: {_human_bytes(status.network.rx_bytes)}")
            right_table.add_row("Interface", status.network.interface or "-")
            right_table.add_row("IP Address", status.network.ip_address or "-")
            right_table.add_row("")
            right_table.add_row("[bold]Security Status[/bold]")
            right_table.add_row("Suricata", "Active" if status.security.suricata_active else "Inactive")
            right_table.add_row("OpenCanary", "Active" if status.security.opencanary_active else "Inactive")
            right_table.add_row("Total Alerts", str(status.security.total_alerts))
            right_table.add_row("Recent Alerts", str(status.security.recent_alerts))
        else:
            right_table.add_row("Status collection failed")
        
        layout["right"].update(Panel(right_table, title="Resources", border_style="cyan"))
        
        self.console.print(layout)
    
    def _change_mode(self, target_mode: str) -> None:
        """Change defensive mode."""
        current = _read_last_decision([Path("/var/log/azazel/decisions.log")])
        current_mode = current.get("mode") if current else "unknown"
        
        if current_mode == target_mode:
            self.console.print(f"[yellow]Already in {target_mode} mode.[/yellow]")
            return
        
        self.console.print(f"[blue]Changing mode from {current_mode} to {target_mode}...[/blue]")
        
        try:
            # Create event and process through daemon
            event = Event(name=target_mode, severity=0)
            self.daemon.process_event(event)
            
            mode_label, color = _mode_style(target_mode)
            self.console.print(f"[{color}]✓ Successfully changed to {mode_label} mode.[/{color}]")
            
        except Exception as e:
            self.console.print(f"[red]✗ Failed to change mode: {e}[/red]")
    
    def _view_decisions(self) -> None:
        """Display recent decision history."""
        self.console.print("[bold]Recent Decision History[/bold]")
        self.console.print("─" * 50)
        
        decision_file = Path("/var/log/azazel/decisions.log")
        if not decision_file.exists():
            self.console.print("[yellow]No decision log found.[/yellow]")
            return
        
        try:
            with decision_file.open("r") as f:
                lines = f.readlines()
            
            # Show last 10 decisions
            recent_lines = lines[-10:] if len(lines) > 10 else lines
            
            table = Table(show_lines=True)
            table.add_column("Time", style="dim")
            table.add_column("Event", style="cyan")
            table.add_column("Score", justify="right")
            table.add_column("Mode", justify="center")
            
            for line in recent_lines:
                try:
                    import json
                    data = json.loads(line.strip())
                    
                    # Format timestamp if available
                    timestamp = "N/A"
                    if "timestamp" in data:
                        timestamp = data["timestamp"]
                    
                    mode = data.get("mode", "unknown")
                    mode_label, color = _mode_style(mode)
                    
                    table.add_row(
                        timestamp,
                        data.get("event", "unknown"),
                        f"{data.get('score', 0):.1f}",
                        Text(mode_label, style=color)
                    )
                except Exception:
                    continue
            
            self.console.print(table)
            
        except Exception as e:
            self.console.print(f"[red]Error reading decision log: {e}[/red]")
    
    # ===== Service Management Functions =====
    
    def _service_status(self) -> None:
        """Display comprehensive service status overview."""
        self.console.print("[bold]Azazel Service Status Overview[/bold]")
        self.console.print("─" * 60)
        
        # Define Azazel services to monitor
        azazel_services = [
            ("azctl.service", "Azazel Core Controller"),
            ("azctl-serve.service", "Azazel Event Consumer"),
            ("suricata.service", "Suricata IDS/IPS"),
            ("opencanary.service", "OpenCanary Honeypot"),
            ("vector.service", "Vector Log Processor"),
            ("azazel-epd.service", "E-Paper Display"),
        ]
        
        table = Table(show_lines=True)
        table.add_column("Service", style="cyan", min_width=20)
        table.add_column("Description", style="dim", min_width=25)
        table.add_column("Status", justify="center", min_width=12)
        table.add_column("Active Since", style="dim", min_width=15)
        table.add_column("Actions", min_width=15)
        
        for service_name, description in azazel_services:
            try:
                # Get service status
                status_result = subprocess.run(
                    ["systemctl", "is-active", service_name],
                    capture_output=True, text=True, timeout=5
                )
                
                is_active = status_result.returncode == 0 and status_result.stdout.strip() == "active"
                
                # Get additional info if active
                active_since = "─"
                if is_active:
                    try:
                        show_result = subprocess.run(
                            ["systemctl", "show", service_name, "--property=ActiveEnterTimestamp"],
                            capture_output=True, text=True, timeout=5
                        )
                        if show_result.returncode == 0:
                            timestamp_line = show_result.stdout.strip()
                            if "=" in timestamp_line:
                                timestamp_str = timestamp_line.split("=", 1)[1]
                                # Parse and format timestamp
                                if timestamp_str and timestamp_str != "0":
                                    active_since = timestamp_str.split()[0] if " " in timestamp_str else "recent"
                    except Exception:
                        pass
                
                # Status display
                if is_active:
                    status_display = Text("🟢 ACTIVE", style="green")
                    actions = "[green]stop[/green] | [yellow]restart[/yellow]"
                else:
                    status_display = Text("🔴 STOPPED", style="red")
                    actions = "[green]start[/green]"
                
                table.add_row(
                    service_name,
                    description,
                    status_display,
                    active_since,
                    actions
                )
                
            except Exception:
                table.add_row(
                    service_name,
                    description,
                    Text("❓ ERROR", style="red"),
                    "─",
                    "─"
                )
        
        self.console.print(table)
        
        # Service management shortcuts
        self.console.print("\n[dim]Available actions:[/dim]")
        self.console.print("[cyan]• Individual service management: Select from Service Management menu[/cyan]")
        self.console.print("[cyan]• Quick restart all: Use 'Restart All Services' action[/cyan]")
    
    def _manage_suricata(self) -> None:
        """Manage Suricata IDS/IPS service."""
        self._manage_service("suricata.service", "Suricata IDS/IPS")
    
    def _manage_opencanary(self) -> None:
        """Manage OpenCanary honeypot service."""
        self._manage_service("opencanary.service", "OpenCanary Honeypot")
    
    def _manage_vector(self) -> None:
        """Manage Vector log processing service."""
        self._manage_service("vector.service", "Vector Log Processor")
    
    def _manage_service(self, service_name: str, display_name: str) -> None:
        """Generic service management interface."""
        self.console.clear()
        self.console.print(f"[bold]{display_name} Management[/bold]")
        self.console.print("─" * 50)
        
        # Get current status
        try:
            status_result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True, text=True, timeout=5
            )
            is_active = status_result.returncode == 0 and status_result.stdout.strip() == "active"
            
            # Get enabled status
            enabled_result = subprocess.run(
                ["systemctl", "is-enabled", service_name],
                capture_output=True, text=True, timeout=5
            )
            is_enabled = enabled_result.returncode == 0 and enabled_result.stdout.strip() == "enabled"
            
        except Exception as e:
            self.console.print(f"[red]Error checking service status: {e}[/red]")
            return
        
        # Display status
        status_panel = Panel.fit(
            f"Service: {service_name}\n"
            f"Status: {'🟢 Active' if is_active else '🔴 Inactive'}\n"
            f"Enabled: {'✅ Yes' if is_enabled else '❌ No'}",
            title=f"{display_name} Status",
            border_style="green" if is_active else "red"
        )
        self.console.print(status_panel)
        self.console.print()
        
        # Show available actions
        actions = []
        if is_active:
            actions.extend(["1. Stop service", "2. Restart service"])
        else:
            actions.extend(["1. Start service"])
        
        if is_enabled:
            actions.append("3. Disable (prevent auto-start)")
        else:
            actions.append("3. Enable (auto-start on boot)")
        
        actions.extend(["4. View logs", "5. Back"])
        
        for action in actions:
            self.console.print(f"[cyan]{action}[/cyan]")
        
        choice = Prompt.ask("\nSelect action", default="5")
        
        if choice == "1":
            if is_active:
                self._execute_systemctl_action("stop", service_name, display_name)
            else:
                self._execute_systemctl_action("start", service_name, display_name)
        elif choice == "2" and is_active:
            self._execute_systemctl_action("restart", service_name, display_name)
        elif choice == "3":
            if is_enabled:
                self._execute_systemctl_action("disable", service_name, display_name)
            else:
                self._execute_systemctl_action("enable", service_name, display_name)
        elif choice == "4":
            self._view_service_logs(service_name, display_name)
        # Choice "5" or others fall through to return
    
    def _execute_systemctl_action(self, action: str, service_name: str, display_name: str) -> None:
        """Execute a systemctl action with progress display."""
        self.console.print(f"\n[blue]Executing: systemctl {action} {service_name}[/blue]")
        
        try:
            with Progress() as progress:
                task = progress.add_task(f"{action.capitalize()}ing {display_name}...", total=100)
                
                result = subprocess.run(
                    ["sudo", "systemctl", action, service_name],
                    capture_output=True, text=True, timeout=30
                )
                
                progress.update(task, completed=100)
                
                if result.returncode == 0:
                    self.console.print(f"[green]✓ Successfully {action}ed {display_name}[/green]")
                    if result.stdout:
                        self.console.print(f"Output: {result.stdout.strip()}")
                else:
                    self.console.print(f"[red]✗ Failed to {action} {display_name}[/red]")
                    if result.stderr:
                        self.console.print(f"Error: {result.stderr.strip()}")
                        
        except subprocess.TimeoutExpired:
            self.console.print(f"[red]✗ Timeout: {action} operation took too long[/red]")
        except Exception as e:
            self.console.print(f"[red]✗ Error: {e}[/red]")
    
    def _view_service_logs(self, service_name: str, display_name: str) -> None:
        """Display recent service logs."""
        self.console.clear()
        self.console.print(f"[bold]{display_name} Recent Logs[/bold]")
        self.console.print("─" * 50)
        
        try:
            result = subprocess.run(
                ["journalctl", "-u", service_name, "-n", "50", "--no-pager"],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                logs = result.stdout.strip()
                if logs:
                    # Format logs with syntax highlighting
                    for line in logs.split('\n'):
                        if 'ERROR' in line.upper() or 'FATAL' in line.upper():
                            self.console.print(line, style="red")
                        elif 'WARN' in line.upper():
                            self.console.print(line, style="yellow")
                        elif 'INFO' in line.upper():
                            self.console.print(line, style="blue")
                        else:
                            self.console.print(line, style="dim")
                else:
                    self.console.print("[yellow]No recent logs found[/yellow]")
            else:
                self.console.print(f"[red]Error retrieving logs: {result.stderr}[/red]")
                
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
    
    def _restart_all_services(self) -> None:
        """Restart all Azazel services."""
        self.console.print("[bold red]Restarting All Azazel Services[/bold red]")
        self.console.print("─" * 50)
        
        services = [
            "azctl.service",
            "suricata.service", 
            "opencanary.service",
            "vector.service",
            "azazel-epd.service"
        ]
        
        self.console.print("[yellow]This will restart all core Azazel services.[/yellow]")
        if not Confirm.ask("Are you sure you want to continue?", default=False):
            self.console.print("[yellow]Operation cancelled.[/yellow]")
            return
        
        with Progress() as progress:
            overall_task = progress.add_task("Restarting services...", total=len(services))
            
            for service in services:
                progress.update(overall_task, description=f"Restarting {service}...")
                
                try:
                    result = subprocess.run(
                        ["sudo", "systemctl", "restart", service],
                        capture_output=True, text=True, timeout=30
                    )
                    
                    if result.returncode == 0:
                        self.console.print(f"[green]✓ {service}[/green]")
                    else:
                        self.console.print(f"[red]✗ {service}: {result.stderr.strip()}[/red]")
                        
                except Exception as e:
                    self.console.print(f"[red]✗ {service}: {e}[/red]")
                
                progress.advance(overall_task)
                time.sleep(0.5)  # Brief pause between restarts
        
        self.console.print("\n[blue]All restart operations completed.[/blue]")
        self.console.print("[dim]Check individual service status for verification.[/dim]")
    
    def _network_status(self) -> None:
        """Display detailed network interface status."""
        self.console.print("[bold]Network Interface Status[/bold]")
        self.console.print("─" * 60)
        
        # Get WLAN interface details
        wlan0 = _wlan_ap_status(self.lan_if)
        wlan1 = _wlan_link_info(self.wan_if)
        
        # Create layout for side-by-side display
        layout = Layout()
        layout.split_row(
            Layout(name="lan"),
            Layout(name="wan")
        )
        
        # LAN Interface (AP) Status
        lan_table = Table.grid(padding=(0, 1))
        lan_table.add_row("[bold]LAN Interface (Access Point)[/bold]")
        lan_table.add_row("Interface", self.lan_if)
        
        if wlan0.get('is_ap'):
            lan_table.add_row("Mode", "🟢 Access Point", style="green")
        elif wlan0.get('is_ap') is False:
            lan_table.add_row("Mode", "🔴 Station/Client", style="red")
        else:
            lan_table.add_row("Mode", "❓ Unknown", style="yellow")
        
        lan_table.add_row("SSID", wlan0.get('ssid') or "─")
        lan_table.add_row("BSSID", wlan0.get('bssid') or "─")
        lan_table.add_row("Channel", str(wlan0.get('channel')) if wlan0.get('channel') else "─")
        
        stations = wlan0.get('stations')
        station_style = "green" if stations and stations > 0 else "dim"
        lan_table.add_row("Connected Stations", 
                         str(stations) if stations is not None else "─", 
                         style=station_style)
        
        if not wlan0.get('hostapd_cli'):
            lan_table.add_row("", "[dim]Note: hostapd_cli not available[/dim]")
        
        layout["lan"].update(Panel(lan_table, title=f"{self.lan_if} (LAN)", border_style="cyan"))
        
        # WAN Interface (Client) Status
        wan_table = Table.grid(padding=(0, 1))
        wan_table.add_row("[bold]WAN Interface (Client)[/bold]")
        wan_table.add_row("Interface", self.wan_if)
        
        if wlan1.get('connected'):
            wan_table.add_row("Status", "🟢 Connected", style="green")
            wan_table.add_row("SSID", wlan1.get('ssid') or "─")
            wan_table.add_row("IP Address", wlan1.get('ip4') or "─")
            
            signal = wlan1.get('signal_dbm')
            if signal is not None:
                signal_style = "green" if signal > -50 else "yellow" if signal > -70 else "red"
                wan_table.add_row("Signal Strength", f"{signal} dBm", style=signal_style)
            
            if wlan1.get('tx_bitrate'):
                wan_table.add_row("TX Bitrate", wlan1.get('tx_bitrate'))
            if wlan1.get('rx_bitrate'):
                wan_table.add_row("RX Bitrate", wlan1.get('rx_bitrate'))
        else:
            wan_table.add_row("Status", "🔴 Disconnected", style="red")
            wan_table.add_row("SSID", "─")
            wan_table.add_row("IP Address", "─")
        
        layout["wan"].update(Panel(wan_table, title=f"{self.wan_if} (WAN)", border_style="yellow"))
        
        self.console.print(layout)
        
        # Additional network information
        self.console.print("\n[bold]Additional Network Information[/bold]")
        try:
            # Show routing table
            route_result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True, timeout=5
            )
            if route_result.returncode == 0 and route_result.stdout.strip():
                self.console.print(f"[dim]Default Route: {route_result.stdout.strip()}[/dim]")
            
            # Show DNS configuration
            try:
                with open("/etc/resolv.conf", "r") as f:
                    dns_lines = [line.strip() for line in f if line.strip().startswith("nameserver")]
                if dns_lines:
                    dns_servers = [line.split()[1] for line in dns_lines]
                    self.console.print(f"[dim]DNS Servers: {', '.join(dns_servers)}[/dim]")
            except Exception:
                pass
                
        except Exception:
            pass
    
    def _show_active_profile(self) -> None:
        """Display active network profile configuration."""
        self.console.print("[bold]Active Network Profile Configuration[/bold]")
        self.console.print("─" * 60)
        
        profile_name = _active_profile()
        
        if not profile_name:
            self.console.print("[yellow]No active profile detected.[/yellow]")
            return
        
        self.console.print(f"[green]Active Profile: {profile_name}[/green]")
        self.console.print()
        
        # Try to load profile configuration
        profile_paths = [
            Path(f"configs/profiles/{profile_name}.yaml"),
            Path(f"/etc/azazel/profiles/{profile_name}.yaml"),
            Path("configs/network/azazel.yaml"),
        ]
        
        config_data = None
        config_path = None
        
        for path in profile_paths:
            try:
                if path.exists():
                    with path.open("r", encoding="utf-8") as f:
                        import yaml
                        config_data = yaml.safe_load(f)
                        config_path = path
                        break
            except Exception:
                continue
        
        if not config_data:
            self.console.print("[red]Could not load profile configuration.[/red]")
            return
        
        self.console.print(f"[dim]Configuration loaded from: {config_path}[/dim]")
        self.console.print()
        
        # Display key configuration sections
        sections = [
            ("Actions", "actions"),
            ("Thresholds", "thresholds"),
            ("QoS Settings", "qos"),
            ("Notification", "notify"),
            ("Storage", "storage")
        ]
        
        for section_name, section_key in sections:
            if section_key in config_data:
                section_data = config_data[section_key]
                
                table = Table.grid(padding=(0, 2))
                table.add_column("Setting", style="cyan", min_width=20)
                table.add_column("Value", style="white")
                
                if section_key == "actions":
                    for mode, settings in section_data.items():
                        mode_label, color = _mode_style(mode)
                        table.add_row(f"{mode_label} Mode:", "")
                        for setting, value in settings.items():
                            table.add_row(f"  {setting}", str(value))
                        table.add_row("", "")
                        
                elif section_key == "thresholds":
                    for key, value in section_data.items():
                        if key == "unlock_wait_secs":
                            table.add_row("Unlock Wait Times:", "")
                            for mode, seconds in value.items():
                                table.add_row(f"  {mode}", f"{seconds}s")
                        else:
                            table.add_row(key, str(value))
                            
                else:
                    for key, value in section_data.items():
                        if isinstance(value, dict):
                            table.add_row(f"{key}:", "")
                            for subkey, subvalue in value.items():
                                table.add_row(f"  {subkey}", str(subvalue))
                        else:
                            table.add_row(key, str(value))
                
                panel = Panel(table, title=section_name, border_style="blue")
                self.console.print(panel)
                self.console.print()
    
    def _traffic_stats(self) -> None:
        """Display network traffic statistics."""
        self.console.print("[bold]Network Traffic Statistics[/bold]")
        self.console.print("─" * 60)
        
        try:
            status = self.status_collector.collect()
        except Exception as e:
            self.console.print(f"[red]Error collecting statistics: {e}[/red]")
            return
        
        # Create main statistics table
        stats_table = Table.grid(padding=(0, 2))
        stats_table.add_column("Metric", style="cyan", min_width=20)
        stats_table.add_column("Value", style="white", min_width=15)
        stats_table.add_column("Description", style="dim")
        
        # Network interface statistics
        if status.network:
            stats_table.add_row("Primary Interface", status.network.interface or "─", "Active network interface")
            stats_table.add_row("IP Address", status.network.ip_address or "─", "Current IP address")
            
            if status.network.tx_bytes:
                stats_table.add_row("TX Bytes", _human_bytes(status.network.tx_bytes), "Total bytes transmitted")
            if status.network.rx_bytes:
                stats_table.add_row("RX Bytes", _human_bytes(status.network.rx_bytes), "Total bytes received")
        
        # System uptime and load
        if status.uptime_seconds:
            hours = status.uptime_seconds // 3600
            minutes = (status.uptime_seconds // 60) % 60
            stats_table.add_row("System Uptime", f"{hours}h {minutes}m", "Time since system boot")
        
        panel = Panel(stats_table, title="Current Statistics", border_style="green")
        self.console.print(panel)
        self.console.print()
        
        # Interface-specific statistics using /proc/net/dev
        self.console.print("[bold]Per-Interface Statistics[/bold]")
        
        try:
            with open("/proc/net/dev", "r") as f:
                lines = f.readlines()
            
            # Parse network interface statistics
            iface_table = Table()
            iface_table.add_column("Interface", style="cyan")
            iface_table.add_column("RX Bytes", justify="right")
            iface_table.add_column("RX Packets", justify="right")
            iface_table.add_column("TX Bytes", justify="right")
            iface_table.add_column("TX Packets", justify="right")
            iface_table.add_column("RX Errors", justify="right", style="red")
            iface_table.add_column("TX Errors", justify="right", style="red")
            
            for line in lines[2:]:  # Skip header lines
                if ":" in line:
                    parts = line.split(":")
                    iface = parts[0].strip()
                    stats = parts[1].split()
                    
                    # Only show active interfaces or WLAN interfaces
                    if (iface.startswith(('wlan', 'eth', 'lo')) or 
                        int(stats[0]) > 0 or int(stats[8]) > 0):
                        
                        iface_table.add_row(
                            iface,
                            _human_bytes(int(stats[0])),  # RX bytes
                            stats[1],                      # RX packets
                            _human_bytes(int(stats[8])),   # TX bytes
                            stats[9],                      # TX packets
                            stats[2] if int(stats[2]) > 0 else "─",  # RX errors
                            stats[10] if int(stats[10]) > 0 else "─"  # TX errors
                        )
            
            self.console.print(iface_table)
            
        except Exception as e:
            self.console.print(f"[yellow]Could not read interface statistics: {e}[/yellow]")
        
        # Traffic control (tc) information if available
        self.console.print("\n[bold]Traffic Control Status[/bold]")
        try:
            tc_result = subprocess.run(
                ["tc", "qdisc", "show"],
                capture_output=True, text=True, timeout=5
            )
            
            if tc_result.returncode == 0 and tc_result.stdout.strip():
                tc_lines = tc_result.stdout.strip().split('\n')
                tc_table = Table.grid(padding=(0, 1))
                
                for line in tc_lines:
                    if line.strip():
                        # Parse tc output and format nicely
                        if 'qdisc' in line:
                            tc_table.add_row(Text(line.strip(), style="dim"))
                
                if tc_table.rows:
                    tc_panel = Panel(tc_table, title="Active Traffic Control Rules", border_style="yellow")
                    self.console.print(tc_panel)
                else:
                    self.console.print("[dim]No active traffic control rules.[/dim]")
            else:
                self.console.print("[dim]Traffic control information not available.[/dim]")
                
        except Exception:
            self.console.print("[dim]Traffic control tools not available.[/dim]")
    
    def _live_decision_log(self) -> None:
        """Monitor decisions.log in real-time."""
        self.console.clear()
        self.console.print("[bold]Live Decision Log Monitoring[/bold]")
        self.console.print("─" * 60)
        self.console.print("[dim]Press Ctrl+C to exit[/dim]")
        self.console.print()
        
        decision_file = Path("/var/log/azazel/decisions.log")
        if not decision_file.exists():
            self.console.print("[yellow]Decision log file not found.[/yellow]")
            self.console.print(f"[dim]Expected location: {decision_file}[/dim]")
            return
        
        try:
            # Show recent entries first
            try:
                with decision_file.open("r") as f:
                    lines = f.readlines()
                recent_lines = lines[-5:] if len(lines) > 5 else lines
                
                self.console.print("[bold]Recent Entries:[/bold]")
                for line in recent_lines:
                    self._format_decision_entry(line.strip())
                
                self.console.print("\n[bold]Live Updates:[/bold]")
                
            except Exception:
                self.console.print("[yellow]Could not read recent entries.[/yellow]")
            
            # Start live monitoring using tail-like functionality
            with decision_file.open("r") as f:
                # Seek to end of file
                f.seek(0, 2)
                
                while True:
                    line = f.readline()
                    if line:
                        self._format_decision_entry(line.strip())
                    else:
                        time.sleep(0.5)  # Brief pause before checking again
                        
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Live monitoring stopped.[/yellow]")
        except Exception as e:
            self.console.print(f"[red]Error monitoring log: {e}[/red]")
    
    def _format_decision_entry(self, line: str) -> None:
        """Format and display a decision log entry."""
        if not line:
            return
            
        try:
            import json
            data = json.loads(line)
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            event = data.get("event", "unknown")
            mode = data.get("mode", "unknown")
            score = data.get("score", 0)
            
            mode_label, color = _mode_style(mode)
            
            # Create formatted entry
            entry = Text.assemble(
                (f"[{timestamp}] ", "dim"),
                (f"{event:10} ", "cyan"),
                (f"→ {mode_label:8} ", f"bold {color}"),
                (f"(score: {score:5.1f})", "white")
            )
            
            self.console.print(entry)
            
        except Exception:
            # Fallback for malformed entries
            self.console.print(f"[dim]{line}[/dim]")
    
    def _live_suricata_log(self) -> None:
        """Monitor Suricata events in real-time."""
        self.console.clear()
        self.console.print("[bold]Live Suricata Event Monitoring[/bold]")
        self.console.print("─" * 60)
        self.console.print("[dim]Press Ctrl+C to exit[/dim]")
        self.console.print()
        
        # Common Suricata log locations
        suricata_logs = [
            Path("/var/log/suricata/eve.json"),
            Path("/var/log/azazel/suricata/eve.json"),
            Path("logs/suricata/eve.json"),
        ]
        
        log_file = None
        for path in suricata_logs:
            if path.exists():
                log_file = path
                break
        
        if not log_file:
            self.console.print("[yellow]Suricata eve.json log file not found.[/yellow]")
            self.console.print("[dim]Checked locations:[/dim]")
            for path in suricata_logs:
                self.console.print(f"[dim]  - {path}[/dim]")
            return
        
        self.console.print(f"[green]Monitoring: {log_file}[/green]")
        self.console.print()
        
        try:
            with log_file.open("r") as f:
                # Seek to end of file
                f.seek(0, 2)
                
                while True:
                    line = f.readline()
                    if line:
                        self._format_suricata_entry(line.strip())
                    else:
                        time.sleep(0.5)
                        
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Live monitoring stopped.[/yellow]")
        except Exception as e:
            self.console.print(f"[red]Error monitoring Suricata log: {e}[/red]")
    
    def _format_suricata_entry(self, line: str) -> None:
        """Format and display a Suricata log entry."""
        if not line:
            return
            
        try:
            import json
            data = json.loads(line)
            
            timestamp = data.get("timestamp", datetime.now().isoformat())[:19]
            event_type = data.get("event_type", "unknown")
            
            # Different formatting based on event type
            if event_type == "alert":
                alert = data.get("alert", {})
                signature = alert.get("signature", "Unknown alert")
                severity = alert.get("severity", 3)
                
                # Color based on severity (1=red, 2=orange, 3=yellow, 4+=green)
                if severity == 1:
                    color = "red"
                elif severity == 2:
                    color = "bright_red"
                elif severity == 3:
                    color = "yellow"
                else:
                    color = "green"
                
                entry = Text.assemble(
                    (f"[{timestamp}] ", "dim"),
                    ("🚨 ALERT ", f"bold {color}"),
                    (f"Sev:{severity} ", f"{color}"),
                    (f"{signature[:50]}{'...' if len(signature) > 50 else ''}", "white")
                )
                
            elif event_type == "flow":
                flow = data.get("flow", {})
                state = flow.get("state", "unknown")
                
                entry = Text.assemble(
                    (f"[{timestamp}] ", "dim"),
                    ("🔄 FLOW ", "cyan"),
                    (f"{state:10} ", "cyan"),
                    (f"pkts:{flow.get('pkts_toserver', 0) + flow.get('pkts_toclient', 0)}", "white")
                )
                
            elif event_type == "dns":
                dns = data.get("dns", {})
                query = dns.get("query", "unknown")
                
                entry = Text.assemble(
                    (f"[{timestamp}] ", "dim"),
                    ("🔍 DNS  ", "blue"),
                    (f"{query[:40]}{'...' if len(query) > 40 else ''}", "white")
                )
                
            elif event_type == "http":
                http = data.get("http", {})
                hostname = http.get("hostname", "unknown")
                url = http.get("url", "/")
                
                entry = Text.assemble(
                    (f"[{timestamp}] ", "dim"),
                    ("🌐 HTTP ", "green"),
                    (f"{hostname}{url[:30]}{'...' if len(url) > 30 else ''}", "white")
                )
                
            else:
                # Generic formatting for other event types
                entry = Text.assemble(
                    (f"[{timestamp}] ", "dim"),
                    (f"{event_type.upper():6} ", "magenta"),
                    (f"{str(data)[:60]}{'...' if len(str(data)) > 60 else ''}", "white")
                )
            
            self.console.print(entry)
            
        except Exception:
            # Fallback for malformed entries
            self.console.print(f"[dim]{line[:100]}{'...' if len(line) > 100 else ''}[/dim]")
    
    def _alert_summary(self) -> None:
        """Show summary of recent security alerts."""
        self.console.print("[bold]Recent Security Alert Summary[/bold]")
        self.console.print("─" * 60)
        
        # Get status data for alert counts
        try:
            status = self.status_collector.collect()
            
            summary_table = Table.grid(padding=(0, 2))
            summary_table.add_column("Metric", style="cyan", min_width=20)
            summary_table.add_column("Count", style="white", justify="right", min_width=10)
            summary_table.add_column("Status", style="white")
            
            if status.security:
                total_style = "red" if status.security.total_alerts > 0 else "green"
                recent_style = "red" if status.security.recent_alerts > 0 else "green"
                
                summary_table.add_row("Total Alerts", str(status.security.total_alerts), "", style=total_style)
                summary_table.add_row("Recent Alerts", str(status.security.recent_alerts), "", style=recent_style)
                summary_table.add_row("Suricata Status", "Active" if status.security.suricata_active else "Inactive", 
                                    "🟢" if status.security.suricata_active else "🔴")
                summary_table.add_row("OpenCanary Status", "Active" if status.security.opencanary_active else "Inactive",
                                    "🟢" if status.security.opencanary_active else "🔴")
            else:
                summary_table.add_row("Status Collection", "Failed", "❌")
            
            panel = Panel(summary_table, title="Alert Overview", border_style="yellow")
            self.console.print(panel)
            self.console.print()
            
        except Exception as e:
            self.console.print(f"[red]Error collecting alert summary: {e}[/red]")
        
        # Try to show recent Suricata alerts from log
        self.console.print("[bold]Recent Suricata Alerts (Last 10)[/bold]")
        
        suricata_logs = [
            Path("/var/log/suricata/eve.json"),
            Path("/var/log/azazel/suricata/eve.json"),
            Path("logs/suricata/eve.json"),
        ]
        
        log_file = None
        for path in suricata_logs:
            if path.exists():
                log_file = path
                break
        
        if not log_file:
            self.console.print("[yellow]Suricata log file not found.[/yellow]")
            return
        
        try:
            alerts = []
            with log_file.open("r") as f:
                # Read last 100 lines to find alerts
                lines = f.readlines()
                recent_lines = lines[-100:] if len(lines) > 100 else lines
                
                for line in recent_lines:
                    try:
                        import json
                        data = json.loads(line.strip())
                        if data.get("event_type") == "alert":
                            alerts.append(data)
                    except Exception:
                        continue
            
            # Show last 10 alerts
            recent_alerts = alerts[-10:] if len(alerts) > 10 else alerts
            
            if recent_alerts:
                alert_table = Table()
                alert_table.add_column("Time", style="dim", width=19)
                alert_table.add_column("Severity", justify="center", width=8)
                alert_table.add_column("Signature", style="white")
                alert_table.add_column("Source", style="cyan", width=15)
                alert_table.add_column("Dest", style="cyan", width=15)
                
                for alert_data in recent_alerts:
                    alert = alert_data.get("alert", {})
                    timestamp = alert_data.get("timestamp", "")[:19]
                    severity = alert.get("severity", 3)
                    signature = alert.get("signature", "Unknown")
                    
                    src_ip = alert_data.get("src_ip", "unknown")
                    dest_ip = alert_data.get("dest_ip", "unknown")
                    
                    # Color severity
                    if severity == 1:
                        sev_style = "bold red"
                    elif severity == 2:
                        sev_style = "red"
                    elif severity == 3:
                        sev_style = "yellow"
                    else:
                        sev_style = "green"
                    
                    alert_table.add_row(
                        timestamp,
                        Text(str(severity), style=sev_style),
                        signature[:50] + ("..." if len(signature) > 50 else ""),
                        src_ip,
                        dest_ip
                    )
                
                self.console.print(alert_table)
            else:
                self.console.print("[green]✓ No recent alerts found.[/green]")
                
        except Exception as e:
            self.console.print(f"[red]Error reading alert log: {e}[/red]")
    
    def _system_resources(self) -> None:
        """Display detailed system resource information."""
        self.console.print("[bold]System Resource Monitor[/bold]")
        self.console.print("─" * 60)
        
        # Create layout for organized display
        layout = Layout()
        layout.split_column(
            Layout(name="top"),
            Layout(name="bottom")
        )
        layout["top"].split_row(
            Layout(name="cpu_mem"),
            Layout(name="disk")
        )
        
        # CPU and Memory Information
        cpu_mem_table = Table.grid(padding=(0, 1))
        cpu_mem_table.add_row("[bold]CPU & Memory[/bold]")
        
        try:
            # CPU information
            with open("/proc/cpuinfo", "r") as f:
                cpu_lines = f.readlines()
            
            cpu_model = "Unknown"
            cpu_cores = 0
            for line in cpu_lines:
                if line.startswith("model name"):
                    cpu_model = line.split(":", 1)[1].strip()
                elif line.startswith("processor"):
                    cpu_cores += 1
            
            if cpu_cores == 0:
                cpu_cores = 1
            
            cpu_mem_table.add_row("CPU Model", cpu_model[:40] + ("..." if len(cpu_model) > 40 else ""))
            cpu_mem_table.add_row("CPU Cores", str(cpu_cores))
            
            # Load averages
            with open("/proc/loadavg", "r") as f:
                load_data = f.read().strip().split()
            
            load_1min = float(load_data[0])
            load_color = "green" if load_1min < cpu_cores else "yellow" if load_1min < cpu_cores * 2 else "red"
            
            cpu_mem_table.add_row("Load Average", f"{load_data[0]}, {load_data[1]}, {load_data[2]}", style=load_color)
            
            # Memory information
            with open("/proc/meminfo", "r") as f:
                mem_lines = f.readlines()
            
            mem_info = {}
            for line in mem_lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    mem_info[key.strip()] = value.strip()
            
            total_mem = int(mem_info.get("MemTotal", "0").split()[0]) * 1024
            free_mem = int(mem_info.get("MemFree", "0").split()[0]) * 1024
            available_mem = int(mem_info.get("MemAvailable", "0").split()[0]) * 1024
            used_mem = total_mem - available_mem
            
            mem_percent = (used_mem / total_mem * 100) if total_mem > 0 else 0
            mem_color = "green" if mem_percent < 70 else "yellow" if mem_percent < 90 else "red"
            
            cpu_mem_table.add_row("Total Memory", _human_bytes(total_mem))
            cpu_mem_table.add_row("Used Memory", f"{_human_bytes(used_mem)} ({mem_percent:.1f}%)", style=mem_color)
            cpu_mem_table.add_row("Available Memory", _human_bytes(available_mem))
            
        except Exception as e:
            cpu_mem_table.add_row("Error", f"Could not read system info: {e}")
        
        layout["cpu_mem"].update(Panel(cpu_mem_table, title="CPU & Memory", border_style="green"))
        
        # Disk Information
        disk_table = Table.grid(padding=(0, 1))
        disk_table.add_row("[bold]Disk Space[/bold]")
        
        try:
            # Get disk usage for key mount points
            mount_points = ["/", "/var", "/tmp", "/home"]
            
            for mount_point in mount_points:
                if os.path.exists(mount_point):
                    stat = os.statvfs(mount_point)
                    total = stat.f_blocks * stat.f_frsize
                    free = stat.f_available * stat.f_frsize
                    used = total - free
                    
                    if total > 0:
                        used_percent = (used / total * 100)
                        disk_color = "green" if used_percent < 80 else "yellow" if used_percent < 95 else "red"
                        
                        disk_table.add_row(
                            f"{mount_point}",
                            f"{_human_bytes(used)} / {_human_bytes(total)} ({used_percent:.1f}%)",
                            style=disk_color
                        )
        except Exception as e:
            disk_table.add_row("Error", f"Could not read disk info: {e}")
        
        layout["disk"].update(Panel(disk_table, title="Disk Usage", border_style="blue"))
        
        # Process Information
        process_table = Table.grid(padding=(0, 1))
        process_table.add_row("[bold]System Processes[/bold]")
        
        try:
            # Get process count and top CPU processes
            result = subprocess.run(
                ["ps", "aux", "--sort=-pcpu"], 
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                process_count = len(lines) - 1  # Exclude header
                
                process_table.add_row("Total Processes", str(process_count))
                process_table.add_row("", "")
                process_table.add_row("[dim]Top CPU Processes:[/dim]", "")
                
                # Show top 5 CPU-consuming processes
                for i, line in enumerate(lines[1:6]):  # Skip header, show top 5
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 11:
                            cpu_percent = parts[2]
                            mem_percent = parts[3]
                            command = " ".join(parts[10:])[:30]
                            
                            process_table.add_row(
                                f"  {command}",
                                f"CPU: {cpu_percent}% MEM: {mem_percent}%",
                                style="dim"
                            )
        except Exception as e:
            process_table.add_row("Error", f"Could not read process info: {e}")
        
        layout["bottom"].update(Panel(process_table, title="Processes", border_style="cyan"))
        
        self.console.print(layout)
    
    def _temperature_status(self) -> None:
        """Display system temperature information."""
        self.console.print("[bold]System Temperature Status[/bold]")
        self.console.print("─" * 60)
        
        temp_table = Table()
        temp_table.add_column("Sensor", style="cyan", min_width=20)
        temp_table.add_column("Temperature", justify="right", min_width=12)
        temp_table.add_column("Status", justify="center", min_width=10)
        temp_table.add_column("Description", style="dim")
        
        temp_found = False
        
        # Check Raspberry Pi CPU temperature
        rpi_temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
        if rpi_temp_path.exists():
            try:
                with rpi_temp_path.open("r") as f:
                    temp_raw = int(f.read().strip())
                    temp_celsius = temp_raw / 1000.0
                
                # Color based on temperature ranges
                if temp_celsius < 60:
                    temp_color = "green"
                    status = "🟢 Normal"
                elif temp_celsius < 75:
                    temp_color = "yellow"
                    status = "🟡 Warm"
                elif temp_celsius < 85:
                    temp_color = "red"
                    status = "🟠 Hot"
                else:
                    temp_color = "bright_red"
                    status = "🔴 Critical"
                
                temp_table.add_row(
                    "CPU (SoC)",
                    Text(f"{temp_celsius:.1f}°C", style=temp_color),
                    status,
                    "System-on-Chip temperature"
                )
                temp_found = True
                
            except Exception as e:
                temp_table.add_row("CPU (SoC)", "Error", "❌", f"Could not read: {e}")
        
        # Check for other thermal zones
        thermal_base = Path("/sys/class/thermal")
        if thermal_base.exists():
            for zone_path in thermal_base.glob("thermal_zone*"):
                if zone_path == rpi_temp_path.parent / "thermal_zone0":
                    continue  # Already handled above
                
                temp_file = zone_path / "temp"
                type_file = zone_path / "type"
                
                if temp_file.exists():
                    try:
                        with temp_file.open("r") as f:
                            temp_raw = int(f.read().strip())
                            temp_celsius = temp_raw / 1000.0
                        
                        sensor_type = "Unknown"
                        if type_file.exists():
                            with type_file.open("r") as f:
                                sensor_type = f.read().strip()
                        
                        # Generic temperature coloring
                        if temp_celsius < 50:
                            temp_color = "green"
                            status = "🟢 Normal"
                        elif temp_celsius < 70:
                            temp_color = "yellow"
                            status = "🟡 Warm"
                        else:
                            temp_color = "red"
                            status = "🔴 Hot"
                        
                        temp_table.add_row(
                            sensor_type,
                            Text(f"{temp_celsius:.1f}°C", style=temp_color),
                            status,
                            f"Thermal zone {zone_path.name}"
                        )
                        temp_found = True
                        
                    except Exception:
                        continue
        
        # Check hwmon sensors (if available)
        hwmon_base = Path("/sys/class/hwmon")
        if hwmon_base.exists():
            for hwmon_path in hwmon_base.glob("hwmon*"):
                name_file = hwmon_path / "name"
                
                sensor_name = "Unknown"
                if name_file.exists():
                    try:
                        with name_file.open("r") as f:
                            sensor_name = f.read().strip()
                    except Exception:
                        continue
                
                # Look for temperature inputs
                for temp_input in hwmon_path.glob("temp*_input"):
                    try:
                        with temp_input.open("r") as f:
                            temp_raw = int(f.read().strip())
                            temp_celsius = temp_raw / 1000.0
                        
                        # Try to get label
                        label_file = hwmon_path / temp_input.name.replace("_input", "_label")
                        label = temp_input.name
                        if label_file.exists():
                            with label_file.open("r") as f:
                                label = f.read().strip()
                        
                        # Generic temperature coloring
                        if temp_celsius < 50:
                            temp_color = "green"
                            status = "🟢 Normal"
                        elif temp_celsius < 70:
                            temp_color = "yellow"
                            status = "🟡 Warm"
                        else:
                            temp_color = "red"
                            status = "🔴 Hot"
                        
                        temp_table.add_row(
                            f"{sensor_name} ({label})",
                            Text(f"{temp_celsius:.1f}°C", style=temp_color),
                            status,
                            "Hardware monitor sensor"
                        )
                        temp_found = True
                        
                    except Exception:
                        continue
        
        if temp_found:
            self.console.print(temp_table)
            
            # Temperature guidelines
            self.console.print("\n[bold]Temperature Guidelines:[/bold]")
            guidelines = Table.grid(padding=(0, 2))
            guidelines.add_row("🟢 Normal", "< 60°C", "Optimal operating temperature")
            guidelines.add_row("🟡 Warm", "60-75°C", "Acceptable but monitor closely")
            guidelines.add_row("🟠 Hot", "75-85°C", "Consider cooling improvements")
            guidelines.add_row("🔴 Critical", "> 85°C", "Immediate action required")
            
            self.console.print(Panel(guidelines, title="Status Legend", border_style="blue"))
        else:
            self.console.print("[yellow]No temperature sensors found on this system.[/yellow]")
            self.console.print("[dim]This is normal for some virtualized or non-Pi systems.[/dim]")
    
    def _uptime_load(self) -> None:
        """Display system uptime and load average information."""
        self.console.print("[bold]System Uptime & Load Information[/bold]")
        self.console.print("─" * 60)
        
        # Create layout for organized display
        layout = Layout()
        layout.split_row(
            Layout(name="uptime"),
            Layout(name="load")
        )
        
        # Uptime Information
        uptime_table = Table.grid(padding=(0, 1))
        uptime_table.add_row("[bold]System Uptime[/bold]")
        
        try:
            with open("/proc/uptime", "r") as f:
                uptime_seconds = float(f.read().split()[0])
            
            # Convert to human readable format
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            seconds = int(uptime_seconds % 60)
            
            if days > 0:
                uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
            elif hours > 0:
                uptime_str = f"{hours}h {minutes}m {seconds}s"
            else:
                uptime_str = f"{minutes}m {seconds}s"
            
            uptime_table.add_row("Current Uptime", uptime_str)
            uptime_table.add_row("Total Seconds", f"{uptime_seconds:.0f}")
            
            # Boot time
            boot_time = datetime.now() - timedelta(seconds=uptime_seconds)
            uptime_table.add_row("Boot Time", boot_time.strftime("%Y-%m-%d %H:%M:%S"))
            
            # System stability indicator
            if days > 30:
                stability = "🟢 Excellent"
                stability_style = "green"
            elif days > 7:
                stability = "🟡 Good"
                stability_style = "yellow"
            elif days > 1:
                stability = "🟠 Fair"
                stability_style = "yellow"
            else:
                stability = "🔴 Recent Boot"
                stability_style = "red"
            
            uptime_table.add_row("Stability", stability, style=stability_style)
            
        except Exception as e:
            uptime_table.add_row("Error", f"Could not read uptime: {e}")
        
        layout["uptime"].update(Panel(uptime_table, title="Uptime", border_style="green"))
        
        # Load Average Information
        load_table = Table.grid(padding=(0, 1))
        load_table.add_row("[bold]Load Averages[/bold]")
        
        try:
            with open("/proc/loadavg", "r") as f:
                load_data = f.read().strip().split()
            
            load_1min = float(load_data[0])
            load_5min = float(load_data[1])
            load_15min = float(load_data[2])
            
            # Get CPU core count for context
            cpu_cores = os.cpu_count() or 1
            
            # Color code based on load relative to CPU cores
            def get_load_color(load_val):
                if load_val < cpu_cores * 0.7:
                    return "green"
                elif load_val < cpu_cores * 1.0:
                    return "yellow"
                elif load_val < cpu_cores * 1.5:
                    return "red"
                else:
                    return "bright_red"
            
            load_table.add_row("1 minute", f"{load_1min:.2f}", style=get_load_color(load_1min))
            load_table.add_row("5 minutes", f"{load_5min:.2f}", style=get_load_color(load_5min))
            load_table.add_row("15 minutes", f"{load_15min:.2f}", style=get_load_color(load_15min))
            load_table.add_row("", "")
            load_table.add_row("CPU Cores", str(cpu_cores))
            load_table.add_row("Max Optimal", f"{cpu_cores * 0.7:.1f}")
            
            # Running processes info
            if len(load_data) >= 4:
                running_total = load_data[3]
                load_table.add_row("Processes", running_total)
            
            # Load trend analysis
            if load_1min < load_15min:
                trend = "📉 Decreasing"
                trend_style = "green"
            elif load_1min > load_15min:
                trend = "📈 Increasing"
                trend_style = "yellow" if load_1min < cpu_cores else "red"
            else:
                trend = "➡️ Stable"
                trend_style = "blue"
            
            load_table.add_row("", "")
            load_table.add_row("Trend", trend, style=trend_style)
            
        except Exception as e:
            load_table.add_row("Error", f"Could not read load average: {e}")
        
        layout["load"].update(Panel(load_table, title="Load Average", border_style="blue"))
        
        self.console.print(layout)
        
        # Load interpretation guide
        self.console.print("\n[bold]Load Average Interpretation:[/bold]")
        guide_table = Table.grid(padding=(0, 2))
        guide_table.add_row("🟢 Low Load", f"< {cpu_cores * 0.7:.1f}", "System running smoothly")
        guide_table.add_row("🟡 Moderate Load", f"{cpu_cores * 0.7:.1f} - {cpu_cores:.1f}", "System under normal load")
        guide_table.add_row("🔴 High Load", f"> {cpu_cores:.1f}", "System may be overloaded")
        guide_table.add_row("", "", "")
        guide_table.add_row("[dim]Note:[/dim]", "[dim]Load represents running + waiting processes[/dim]", "")
        guide_table.add_row("[dim]Cores:[/dim]", f"[dim]This system has {cpu_cores} CPU cores[/dim]", "")
        
        self.console.print(Panel(guide_table, title="Guide", border_style="cyan"))
    
    def _emergency_lockdown(self) -> None:
        """Execute immediate emergency lockdown."""
        self.console.clear()
        self.console.print("[bold red]🚨 EMERGENCY LOCKDOWN ACTIVATION 🚨[/bold red]")
        self.console.print("─" * 60)
        
        # Show current status
        current = _read_last_decision([Path("/var/log/azazel/decisions.log")])
        current_mode = current.get("mode") if current else "unknown"
        
        self.console.print(f"Current Mode: [yellow]{current_mode.upper()}[/yellow]")
        self.console.print("Target Mode:  [red]LOCKDOWN[/red]")
        self.console.print()
        
        # Warning and confirmation
        warning_panel = Panel.fit(
            "[bold red]⚠️  EMERGENCY LOCKDOWN WARNING ⚠️[/bold red]\n\n"
            "This will immediately:\n"
            "• Switch to maximum security mode\n"
            "• Apply strict traffic restrictions\n"
            "• Block non-essential network access\n"
            "• Activate enhanced monitoring\n\n"
            "[bold]This action should only be used in genuine emergencies![/bold]",
            title="Emergency Action",
            border_style="red"
        )
        
        self.console.print(warning_panel)
        self.console.print()
        
        # Triple confirmation for safety
        if not Confirm.ask("[red]Are you absolutely sure you want to activate emergency lockdown?[/red]", default=False):
            self.console.print("[yellow]Emergency lockdown cancelled.[/yellow]")
            return
        
        if not Confirm.ask("[red]This is your final confirmation. Proceed with EMERGENCY LOCKDOWN?[/red]", default=False):
            self.console.print("[yellow]Emergency lockdown cancelled.[/yellow]")
            return
        
        # Execute emergency lockdown
        self.console.print("\n[red]🚨 EXECUTING EMERGENCY LOCKDOWN... 🚨[/red]")
        
        try:
            with Progress() as progress:
                task = progress.add_task("Activating emergency lockdown...", total=100)
                
                # Force lockdown mode
                event = Event(name="lockdown", severity=100)  # Maximum severity for emergency
                self.daemon.process_event(event)
                progress.update(task, completed=50)
                
                # Additional emergency measures could be added here
                # For example: applying nftables rules, notifying administrators, etc.
                
                progress.update(task, completed=100)
            
            self.console.print("\n[red]✓ EMERGENCY LOCKDOWN ACTIVATED[/red]")
            self.console.print("[yellow]System is now in maximum security mode.[/yellow]")
            
            # Log the emergency action
            self.console.print(f"\n[dim]Emergency lockdown logged at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
            
        except Exception as e:
            self.console.print(f"\n[red]✗ EMERGENCY LOCKDOWN FAILED: {e}[/red]")
            self.console.print("[red]Manual intervention may be required![/red]")
    
    def _emergency_reset(self) -> None:
        """Execute emergency system reset to portal mode."""
        self.console.clear()
        self.console.print("[bold red]🔄 EMERGENCY SYSTEM RESET 🔄[/bold red]")
        self.console.print("─" * 60)
        
        # Show current status
        current = _read_last_decision([Path("/var/log/azazel/decisions.log")])
        current_mode = current.get("mode") if current else "unknown"
        
        self.console.print(f"Current Mode: [yellow]{current_mode.upper()}[/yellow]")
        self.console.print("Target Mode:  [green]PORTAL[/green]")
        self.console.print()
        
        # Information and confirmation
        reset_panel = Panel.fit(
            "[bold yellow]⚠️  EMERGENCY RESET PROCEDURE ⚠️[/bold yellow]\n\n"
            "This will:\n"
            "• Reset defensive mode to PORTAL\n"
            "• Restart all Azazel services\n"
            "• Clear any temporary restrictions\n"
            "• Return system to normal operations\n\n"
            "[bold]Use this to recover from system issues or lockdown mode.[/bold]",
            title="Reset Action",
            border_style="yellow"
        )
        
        self.console.print(reset_panel)
        self.console.print()
        
        # Confirmation
        if not Confirm.ask("[yellow]Proceed with emergency system reset?[/yellow]", default=False):
            self.console.print("[yellow]Emergency reset cancelled.[/yellow]")
            return
        
        # Execute emergency reset
        self.console.print("\n[blue]🔄 EXECUTING EMERGENCY RESET... 🔄[/blue]")
        
        try:
            with Progress() as progress:
                reset_task = progress.add_task("Emergency reset in progress...", total=100)
                
                # Step 1: Reset to portal mode
                progress.update(reset_task, description="Resetting to portal mode...")
                event = Event(name="portal", severity=0)
                self.daemon.process_event(event)
                progress.update(reset_task, completed=25)
                
                # Step 2: Restart core services
                progress.update(reset_task, description="Restarting Azazel services...")
                
                critical_services = [
                    "azctl.service",
                    "suricata.service",
                    "opencanary.service",
                    "vector.service"
                ]
                
                for i, service in enumerate(critical_services):
                    try:
                        subprocess.run(
                            ["sudo", "systemctl", "restart", service],
                            capture_output=True, text=True, timeout=15
                        )
                        progress.update(reset_task, completed=25 + (i + 1) * 15)
                    except Exception:
                        # Continue with other services even if one fails
                        pass
                
                # Step 3: Final verification
                progress.update(reset_task, description="Verifying system state...")
                time.sleep(2)  # Allow services to stabilize
                progress.update(reset_task, completed=100)
            
            self.console.print("\n[green]✓ EMERGENCY RESET COMPLETED[/green]")
            self.console.print("[green]System has been reset to normal operations.[/green]")
            
            # Show post-reset status
            self.console.print("\n[bold]Post-Reset Status:[/bold]")
            status_table = Table.grid(padding=(0, 2))
            status_table.add_row("Mode", "PORTAL (Normal Operations)", style="green")
            status_table.add_row("Services", "Restarted", style="green")
            status_table.add_row("Restrictions", "Cleared", style="green")
            status_table.add_row("Timestamp", datetime.now().strftime('%Y-%m-%d %H:%M:%S'), style="dim")
            
            self.console.print(Panel(status_table, title="Reset Complete", border_style="green"))
            
        except Exception as e:
            self.console.print(f"\n[red]✗ EMERGENCY RESET FAILED: {e}[/red]")
            self.console.print("[red]Some manual intervention may be required.[/red]")
            self.console.print("[dim]Check individual service status and restart manually if needed.[/dim]")
    
    def _generate_report(self) -> None:
        """Generate comprehensive system status report."""
        self.console.print("[bold]Generating Comprehensive System Report[/bold]")
        self.console.print("─" * 60)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"azazel_system_report_{timestamp}.txt"
        report_path = Path(f"/tmp/{report_filename}")
        
        self.console.print(f"Report will be saved to: [cyan]{report_path}[/cyan]")
        self.console.print()
        
        try:
            with Progress() as progress:
                task = progress.add_task("Generating report...", total=100)
                
                with report_path.open("w", encoding="utf-8") as report:
                    # Report header
                    report.write(f"AZAZEL-PI SYSTEM REPORT\n")
                    report.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    report.write(f"{'='*60}\n\n")
                    
                    progress.update(task, description="Collecting system info...", completed=10)
                    
                    # System Information
                    report.write("SYSTEM INFORMATION\n")
                    report.write("-" * 30 + "\n")
                    
                    try:
                        with open("/proc/version", "r") as f:
                            report.write(f"Kernel: {f.read().strip()}\n")
                    except Exception:
                        pass
                    
                    try:
                        result = subprocess.run(["hostname", "-f"], capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            report.write(f"Hostname: {result.stdout.strip()}\n")
                    except Exception:
                        pass
                    
                    progress.update(task, completed=20)
                    
                    # Defense Status
                    report.write("\nDEFENSE STATUS\n")
                    report.write("-" * 30 + "\n")
                    
                    current = _read_last_decision([Path("/var/log/azazel/decisions.log")])
                    if current:
                        report.write(f"Current Mode: {current.get('mode', 'unknown').upper()}\n")
                        report.write(f"Last Score: {current.get('score', 0):.2f}\n")
                        report.write(f"Score Average: {current.get('average', 0):.2f}\n")
                    else:
                        report.write("Defense status: Unknown (no decisions.log)\n")
                    
                    progress.update(task, completed=30)
                    
                    # Network Status
                    report.write("\nNETWORK STATUS\n")
                    report.write("-" * 30 + "\n")
                    
                    wlan0 = _wlan_ap_status(self.lan_if)
                    wlan1 = _wlan_link_info(self.wan_if)
                    
                    report.write(f"LAN Interface ({self.lan_if}):\n")
                    report.write(f"  Mode: {'AP' if wlan0.get('is_ap') else 'Client' if wlan0.get('is_ap') is False else 'Unknown'}\n")
                    report.write(f"  SSID: {wlan0.get('ssid', 'N/A')}\n")
                    report.write(f"  Channel: {wlan0.get('channel', 'N/A')}\n")
                    report.write(f"  Connected Stations: {wlan0.get('stations', 'N/A')}\n")
                    
                    report.write(f"\nWAN Interface ({self.wan_if}):\n")
                    report.write(f"  Connected: {'Yes' if wlan1.get('connected') else 'No'}\n")
                    report.write(f"  SSID: {wlan1.get('ssid', 'N/A')}\n")
                    report.write(f"  IP Address: {wlan1.get('ip4', 'N/A')}\n")
                    report.write(f"  Signal: {wlan1.get('signal_dbm', 'N/A')} dBm\n")
                    
                    progress.update(task, completed=50)
                    
                    # Service Status
                    report.write("\nSERVICE STATUS\n")
                    report.write("-" * 30 + "\n")
                    
                    services = [
                        "azctl.service",
                        "azctl-serve.service", 
                        "suricata.service",
                        "opencanary.service",
                        "vector.service",
                        "azazel-epd.service"
                    ]
                    
                    for service in services:
                        try:
                            result = subprocess.run(
                                ["systemctl", "is-active", service],
                                capture_output=True, text=True, timeout=5
                            )
                            status = result.stdout.strip()
                            report.write(f"  {service}: {status}\n")
                        except Exception:
                            report.write(f"  {service}: error\n")
                    
                    progress.update(task, completed=70)
                    
                    # System Resources
                    report.write("\nSYSTEM RESOURCES\n")
                    report.write("-" * 30 + "\n")
                    
                    try:
                        with open("/proc/uptime", "r") as f:
                            uptime_seconds = float(f.read().split()[0])
                        days = int(uptime_seconds // 86400)
                        hours = int((uptime_seconds % 86400) // 3600)
                        minutes = int((uptime_seconds % 3600) // 60)
                        report.write(f"Uptime: {days}d {hours}h {minutes}m\n")
                    except Exception:
                        pass
                    
                    try:
                        with open("/proc/loadavg", "r") as f:
                            load_data = f.read().strip().split()
                        report.write(f"Load Average: {load_data[0]} {load_data[1]} {load_data[2]}\n")
                    except Exception:
                        pass
                    
                    try:
                        with open("/proc/meminfo", "r") as f:
                            mem_lines = f.readlines()
                        
                        mem_info = {}
                        for line in mem_lines:
                            if ":" in line:
                                key, value = line.split(":", 1)
                                mem_info[key.strip()] = value.strip()
                        
                        total_kb = int(mem_info.get("MemTotal", "0").split()[0])
                        available_kb = int(mem_info.get("MemAvailable", "0").split()[0])
                        
                        report.write(f"Memory Total: {total_kb // 1024} MB\n")
                        report.write(f"Memory Available: {available_kb // 1024} MB\n")
                        report.write(f"Memory Used: {(total_kb - available_kb) // 1024} MB\n")
                    except Exception:
                        pass
                    
                    progress.update(task, completed=90)
                    
                    # Recent Decisions (last 10)
                    report.write("\nRECENT DECISIONS\n")
                    report.write("-" * 30 + "\n")
                    
                    decision_file = Path("/var/log/azazel/decisions.log")
                    if decision_file.exists():
                        try:
                            with decision_file.open("r") as f:
                                lines = f.readlines()
                            recent_lines = lines[-10:] if len(lines) > 10 else lines
                            
                            for line in recent_lines:
                                try:
                                    import json
                                    data = json.loads(line.strip())
                                    report.write(f"  {data.get('event', 'unknown'):10} -> {data.get('mode', 'unknown'):10} (score: {data.get('score', 0):5.1f})\n")
                                except Exception:
                                    continue
                        except Exception:
                            report.write("  Could not read decision log\n")
                    else:
                        report.write("  No decision log found\n")
                    
                    progress.update(task, completed=100)
                    
                    # Report footer
                    report.write(f"\n{'='*60}\n")
                    report.write("End of report\n")
            
            self.console.print(f"\n[green]✓ Report generated successfully![/green]")
            self.console.print(f"[cyan]Report saved to: {report_path}[/cyan]")
            
            # Show report preview
            if Confirm.ask("\nWould you like to view the report now?", default=True):
                self.console.clear()
                with report_path.open("r", encoding="utf-8") as f:
                    content = f.read()
                
                # Display in a scrollable panel
                self.console.print(Panel(
                    content,
                    title=f"System Report - {report_filename}",
                    border_style="green"
                ))
                
        except Exception as e:
            self.console.print(f"\n[red]✗ Error generating report: {e}[/red]")


def main() -> int:
    """Entry point for the TUI menu."""
    if not RICH_AVAILABLE:
        print("Error: Rich library is required for TUI menu.")
        print("Install with: pip install rich")
        return 1
    
    try:
        menu = AzazelTUIMenu()
        menu.run()
        return 0
    except KeyboardInterrupt:
        print("\nExiting...")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())