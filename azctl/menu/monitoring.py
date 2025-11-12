#!/usr/bin/env python3
"""
Log Monitoring Module

Provides log viewing and monitoring functionality for the Azazel TUI menu system.
"""

import subprocess
from azazel_pi.utils.cmd_runner import run as run_cmd
from typing import Optional

from rich.console import Console
from rich.text import Text
from rich.prompt import Prompt

from azctl.menu.types import MenuCategory, MenuAction


class MonitoringModule:
    """Log monitoring and viewing functionality."""
    
    def __init__(self, console: Console):
        self.console = console
    
    def get_category(self) -> MenuCategory:
        """Get the log monitoring menu category."""
        return MenuCategory(
            title="Log Monitoring",
            description="View system and security logs",
            actions=[
                MenuAction("View Live Decision Log", "Monitor defensive decision changes in real-time", self._live_decision_log),
                MenuAction("View Suricata Alerts", "Display recent Suricata IDS alerts", self._suricata_alerts),
                MenuAction("View System Logs", "Display recent system messages", self._system_logs),
                MenuAction("View Security Logs", "Display security-related log entries", self._security_logs),
            ]
        )
    
    def _live_decision_log(self) -> None:
        """Display live decision log updates."""
        title = Text("Live Decision Log Monitor", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len("Live Decision Log Monitor"), style="dim"))
        
        self.console.print("[blue]Press Ctrl+C to stop monitoring[/blue]")
        self.console.print()
        
        try:
            result = run_cmd(
                ["tail", "-f", "/var/log/azazel/decisions.log"],
                timeout=30
            )
        except subprocess.TimeoutExpired:
            self.console.print("[yellow]Monitoring stopped.[/yellow]")
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Monitoring interrupted by user.[/yellow]")
        except Exception as e:
            self.console.print(f"[red]Error monitoring logs: {e}[/red]")
        
        self._pause()
    
    def _suricata_alerts(self) -> None:
        """Display recent Suricata alerts."""
        title = Text("Recent Suricata Alerts", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len("Recent Suricata Alerts"), style="dim"))
        
        try:
            result = run_cmd(
                ["journalctl", "-u", "suricata", "-n", "50", "--no-pager"],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                logs = result.stdout.strip()
                if logs:
                    for line in logs.split('\n')[-20:]:
                        if "ALERT" in line or "alert" in line:
                            self.console.print(f"[red]{line}[/red]")
                        elif "DROP" in line or "drop" in line:
                            self.console.print(f"[yellow]{line}[/yellow]")
                        else:
                            self.console.print(f"[dim]{line}[/dim]")
                else:
                    self.console.print("[yellow]No recent alerts found.[/yellow]")
            else:
                self.console.print(f"[red]Failed to retrieve alerts: {result.stderr.strip()}[/red]")
        
        except Exception as e:
            self.console.print(f"[red]Error retrieving alerts: {e}[/red]")
        
        self._pause()
    
    def _system_logs(self) -> None:
        """Display recent system logs."""
        title = Text("Recent System Messages", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len("Recent System Messages"), style="dim"))
        
        try:
            result = run_cmd(
                ["journalctl", "-n", "30", "--no-pager"],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                logs = result.stdout.strip()
                if logs:
                    for line in logs.split('\n')[-20:]:
                        if "error" in line.lower() or "failed" in line.lower():
                            self.console.print(f"[red]{line}[/red]")
                        elif "warning" in line.lower() or "warn" in line.lower():
                            self.console.print(f"[yellow]{line}[/yellow]")
                        else:
                            self.console.print(f"[dim]{line}[/dim]")
                else:
                    self.console.print("[yellow]No recent logs found.[/yellow]")
            else:
                self.console.print(f"[red]Failed to retrieve logs: {result.stderr.strip()}[/red]")
        
        except Exception as e:
            self.console.print(f"[red]Error retrieving logs: {e}[/red]")
        
        self._pause()
    
    def _security_logs(self) -> None:
        """Display security-related logs."""
        title = Text("Security Log Entries", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len("Security Log Entries"), style="dim"))
        
        try:
            # Check multiple security-related logs
            commands = [
                (["journalctl", "_COMM=sshd", "-n", "20", "--no-pager"], "SSH"),
                (["journalctl", "_COMM=sudo", "-n", "10", "--no-pager"], "Sudo"),
                (["tail", "-20", "/var/log/auth.log"], "Auth"),
            ]
            
            for cmd, label in commands:
                self.console.print(f"\n[bold cyan]{label} Events:[/bold cyan]")
                try:
                    result = run_cmd(cmd, capture_output=True, text=True, timeout=5)
                    if result.returncode == 0 and result.stdout.strip():
                        for line in result.stdout.split('\n')[-10:]:
                            if line.strip():
                                if "failed" in line.lower() or "invalid" in line.lower():
                                    self.console.print(f"[red]{line}[/red]")
                                else:
                                    self.console.print(f"[dim]{line}[/dim]")
                    else:
                        self.console.print("[dim]No recent events[/dim]")
                except Exception:
                    self.console.print("[dim]Unable to retrieve logs[/dim]")
        
        except Exception as e:
            self.console.print(f"[red]Error retrieving security logs: {e}[/red]")
        
        self._pause()
    
    def _pause(self) -> None:
        """Pause for user input."""
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="", show_default=False)