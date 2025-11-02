#!/usr/bin/env python3
"""
Defense Control Module

Provides defensive mode management and threat response functionality
for the Azazel TUI menu system.
"""

import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

from rich.console import Console
from rich.layout import Layout
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.text import Text

from .types import MenuCategory, MenuAction
from ..cli import _read_last_decision, _mode_style, _wlan_ap_status, _wlan_link_info, _active_profile

try:
    from ..core.ingest.status_collector import NetworkStatusCollector
except ImportError:
    NetworkStatusCollector = None


class DefenseModule:
    """Defense control and mode management functionality."""
    
    def __init__(self, console: Console, decisions_log: Optional[str] = None):
        self.console = console
        self.decisions_log = decisions_log
        
        # Initialize status collector if available
        try:
            self.status_collector = NetworkStatusCollector()
        except Exception:
            self.status_collector = None
    
    def get_category(self) -> MenuCategory:
        """Get the defense control menu category."""
        return MenuCategory(
            title="Defense Control",
            description="Manage defensive modes and threat response",
            actions=[
                MenuAction("View Current Status", "Display current defensive mode and system status", self._view_status),
                MenuAction("Switch to Portal Mode", "Change to minimal restrictions mode", self._switch_to_portal),
                MenuAction("Switch to Shield Mode", "Change to enhanced monitoring mode", self._switch_to_shield),
                MenuAction("Switch to Lockdown Mode ⚠️", "Change to full containment mode", self._switch_to_lockdown, dangerous=True),
                MenuAction("View Decision History", "Show recent mode change decisions", self._view_decisions),
            ]
        )
    
    def _view_status(self) -> None:
        """Display comprehensive system status."""
        title = Text("System Status Overview", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len("System Status Overview"), style="dim"))
        
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
        
        wlan0 = _wlan_ap_status("wlan0")
        wlan1 = _wlan_link_info("wlan1")
        profile = _active_profile()
        
        try:
            status = self.status_collector.collect()
        except Exception:
            status = None
        
        # Create layout
        layout = Layout()
        layout.split_row(
            Layout(name="left"),
            Layout(name="right")
        )
        
        # Left panel - Status information
        left_table = Table(show_header=False, box=None)
        left_table.add_column("Category", style="bold", min_width=15)
        left_table.add_column("Details", style="white")
        
        # Defense status
        left_table.add_row("Defense Status", "")
        left_table.add_row("Mode", f"[{color}]{mode_label}[/{color}]")
        
        if status and 'threat_score' in status:
            left_table.add_row("Score", f"{status['threat_score']:.1f}")
            left_table.add_row("Average", f"{status.get('avg_score', 0):.1f}")
        
        left_table.add_row("", "")
        
        # Network status
        left_table.add_row("Network Status", "")
        left_table.add_row("Profile", profile or "Unknown")
        
        if wlan0.get('is_ap'):
            ap_info = f"AP | SSID: {wlan0.get('ssid', 'None')} | Ch: {wlan0.get('channel', 'None')}"
        else:
            ap_info = "Inactive"
        left_table.add_row("wlan0", ap_info)
        
        if wlan1.get('connected'):
            wan_info = f"Connected | SSID: {wlan1.get('ssid', 'Unknown')}"
        else:
            wan_info = "Disconnected"
        left_table.add_row("wlan1", wan_info)
        
        layout["left"].update(Panel(left_table, title="Status", border_style=color))
        
        # Right panel - Resources and security
        right_table = Table(show_header=False, box=None)
        right_table.add_column("Category", style="bold", min_width=15)
        right_table.add_column("Details", style="white")
        
        # System resources
        right_table.add_row("System Resources", "")
        
        if status:
            uptime = status.get('uptime', 'Unknown')
            right_table.add_row("Uptime", str(uptime))
            
            # Network interface info
            eth0_info = status.get('interfaces', {}).get('eth0', {})
            if eth0_info:
                right_table.add_row("Interface", "eth0")
                right_table.add_row("IP Address", eth0_info.get('ip', '-'))
            
            right_table.add_row("", "")
            
            # Security status
            right_table.add_row("Security Status", "")
            
            # Check service status
            services = ["suricata", "opencanary"]
            for service in services:
                try:
                    result = subprocess.run(
                        ["systemctl", "is-active", service],
                        capture_output=True, text=True, timeout=3
                    )
                    if result.returncode == 0 and result.stdout.strip() == "active":
                        right_table.add_row(service.title(), "[green]Active[/green]")
                    else:
                        right_table.add_row(service.title(), "[red]Inactive[/red]")
                except Exception:
                    right_table.add_row(service.title(), "[yellow]Unknown[/yellow]")
            
            # Alert information
            alerts = status.get('recent_alerts', 0)
            total_alerts = status.get('total_alerts', 0)
            right_table.add_row("Total Alerts", str(total_alerts))
            right_table.add_row("Recent Alerts", str(alerts))
        
        layout["right"].update(Panel(right_table, title="Resources", border_style="cyan"))
        
        self.console.print(layout)
        self._pause()
    
    def _switch_to_portal(self) -> None:
        """Switch to Portal mode."""
        self._switch_mode("portal", "Portal mode provides minimal restrictions and monitoring.")
    
    def _switch_to_shield(self) -> None:
        """Switch to Shield mode."""
        self._switch_mode("shield", "Shield mode provides enhanced monitoring and moderate restrictions.")
    
    def _switch_to_lockdown(self) -> None:
        """Switch to Lockdown mode."""
        if not Confirm.ask("[red]Warning: Lockdown mode will block all traffic except essential services. Continue?[/red]"):
            return
        self._switch_mode("lockdown", "Lockdown mode provides maximum security with strict traffic filtering.")
    
    def _switch_mode(self, mode: str, description: str) -> None:
        """Generic mode switching function."""
        self.console.print(f"[blue]Switching to {mode.upper()} mode...[/blue]")
        self.console.print(f"[dim]{description}[/dim]")
        
        try:
            # Use azctl CLI to switch mode
            result = subprocess.run(
                ["python3", "-m", "azctl", "events", "--mode", mode],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                self.console.print(f"[green]✓ Successfully switched to {mode.upper()} mode[/green]")
            else:
                self.console.print(f"[red]✗ Failed to switch mode: {result.stderr.strip()}[/red]")
                
        except Exception as e:
            self.console.print(f"[red]✗ Failed to change mode: {e}[/red]")
        
        self._pause()
    
    def _view_decisions(self) -> None:
        """Display recent decision history."""
        title = Text("Recent Decision History", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len("Recent Decision History"), style="dim"))
        
        decision_file = Path("/var/log/azazel/decisions.log")
        if not decision_file.exists():
            self.console.print("[yellow]No decision log found.[/yellow]")
            self._pause()
            return
        
        try:
            # Read last 10 decisions
            with open(decision_file, 'r') as f:
                lines = f.readlines()
            
            recent_lines = lines[-10:] if len(lines) >= 10 else lines
            
            table = Table()
            table.add_column("Timestamp", style="cyan", width=20)
            table.add_column("Mode", style="bold", width=10)
            table.add_column("Reason", style="white")
            table.add_column("Score", justify="right", width=8)
            
            for line in recent_lines:
                try:
                    import json
                    decision = json.loads(line.strip())
                    
                    timestamp = decision.get('timestamp', 'Unknown')
                    mode = decision.get('mode', 'Unknown')
                    reason = decision.get('reason', 'No reason provided')
                    score = decision.get('score', 'N/A')
                    
                    # Format timestamp
                    if timestamp and timestamp != 'Unknown':
                        from datetime import datetime
                        try:
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
                        except Exception:
                            pass
                    
                    # Color code mode
                    mode_label, color = _mode_style(mode)
                    mode_colored = f"[{color}]{mode_label}[/{color}]"
                    
                    table.add_row(
                        timestamp,
                        mode_colored,
                        reason[:50] + "..." if len(reason) > 50 else reason,
                        str(score) if score != 'N/A' else score
                    )
                    
                except Exception:
                    continue
            
            if table.row_count == 0:
                self.console.print("[yellow]No valid decisions found in log.[/yellow]")
            else:
                self.console.print(table)
                
        except Exception as e:
            self.console.print(f"[red]Error reading decision log: {e}[/red]")
        
        self._pause()
    
    def _pause(self) -> None:
        """Pause for user input."""
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="", show_default=False)