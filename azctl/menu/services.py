#!/usr/bin/env python3
"""
Services Management Module

Provides system service control and monitoring functionality
for the Azazel TUI menu system.
"""

import subprocess
from typing import List, Tuple

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt, Confirm

from azctl.menu.types import MenuCategory, MenuAction


class ServicesModule:
    """System services management functionality."""
    
    def __init__(self, console: Console):
        self.console = console
    
    def get_category(self) -> MenuCategory:
        """Get the services management menu category."""
        return MenuCategory(
            title="Service Management",
            description="Control Azazel system services",
            actions=[
                MenuAction("Service Status Overview", "View all Azazel services status", self._service_status),
                MenuAction("Start/Stop Suricata 🔒", "Control Suricata IDS service", lambda: self._manage_service("suricata.service", "Suricata IDS"), requires_root=True),
                MenuAction("Start/Stop OpenCanary 🔒", "Control OpenCanary honeypot service", lambda: self._manage_service("opencanary.service", "OpenCanary Honeypot"), requires_root=True),
                MenuAction("Start/Stop Vector 🔒", "Control Vector log processing service", lambda: self._manage_service("vector.service", "Vector Log Processor"), requires_root=True),
                MenuAction("Restart All Services 🔒 ⚠️", "Restart all Azazel services", self._restart_all_services, requires_root=True, dangerous=True),
            ]
        )
    
    def _service_status(self) -> None:
        """Display comprehensive service status overview."""
        title = Text("Azazel Service Status Overview", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len("Azazel Service Status Overview"), style="dim"))
        
        # Define Azazel services to monitor
        azazel_services = [
            ("azctl-unified.service", "Azazel Unified Control Daemon"),
            ("suricata.service", "Suricata IDS/IPS"),
            ("opencanary.service", "OpenCanary Honeypot"),
            ("vector.service", "Vector Log Processor"),
            ("azazel-epd.service", "E-Paper Display"),
        ]
        
        # Create services table
        table = Table()
        table.add_column("Service", style="white", min_width=20)
        table.add_column("Description", style="dim", min_width=25)
        table.add_column("Status", justify="center", width=12)
        table.add_column("Active Since", style="cyan", width=15)
        table.add_column("Actions", style="yellow", width=15)
        
        for service_name, description in azazel_services:
            status, since, actions = self._get_service_info(service_name)
            table.add_row(service_name, description, status, since, actions)
        
        self.console.print(table)
        self.console.print()
        
        self.console.print("[bold]Available actions:[/bold]")
        self.console.print("• Individual service management: Select from Service Management menu")
        self.console.print("• Quick restart all: Use 'Restart All Services' action")
        
        self._pause()
    
    def _get_service_info(self, service_name: str) -> Tuple[str, str, str]:
        """Get service status information."""
        try:
            # Get service status
            status_result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True, text=True, timeout=5
            )
            
            if status_result.returncode == 0 and status_result.stdout.strip() == "active":
                status = "🟢 ACTIVE"
                
                # Get when service started
                since_result = subprocess.run(
                    ["systemctl", "show", service_name, "--property=ActiveEnterTimestamp", "--value"],
                    capture_output=True, text=True, timeout=5
                )
                
                if since_result.returncode == 0 and since_result.stdout.strip():
                    try:
                        from datetime import datetime
                        timestamp_str = since_result.stdout.strip()
                        # Parse systemd timestamp format
                        dt = datetime.strptime(timestamp_str.split()[0:3], '%a %Y-%m-%d %H:%M:%S')
                        since = dt.strftime('%a')  # Short day name
                    except Exception:
                        since = "Unknown"
                else:
                    since = "Unknown"
                
                actions = "stop | restart"
                
            else:
                status = "🔴 STOPPED"
                since = "─"
                actions = "start"
                
        except Exception:
            status = "❓ UNKNOWN"
            since = "─"
            actions = "check"
        
        return status, since, actions
    
    def _manage_service(self, service_name: str, display_name: str) -> None:
        """Generic service management interface."""
        self.console.clear()
        title = Text(f"{display_name} Management", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len(f"{display_name} Management"), style="dim"))
        
        # Get current status
        try:
            status_result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True, text=True, timeout=5
            )
            
            is_active = status_result.returncode == 0 and status_result.stdout.strip() == "active"
            
            if is_active:
                self.console.print(f"[green]✓ {display_name} is currently ACTIVE[/green]")
                self.console.print()
                
                self.console.print("[cyan]1.[/cyan] Stop Service")
                self.console.print("[cyan]2.[/cyan] Restart Service")
                self.console.print("[cyan]3.[/cyan] View Recent Logs")
                self.console.print("[cyan]4.[/cyan] View Service Status Details")
                
            else:
                self.console.print(f"[red]✗ {display_name} is currently STOPPED[/red]")
                self.console.print()
                
                self.console.print("[cyan]1.[/cyan] Start Service")
                self.console.print("[cyan]2.[/cyan] View Recent Logs")
                self.console.print("[cyan]3.[/cyan] View Service Status Details")
            
            self.console.print()
            self.console.print("[cyan]b.[/cyan] Back to Service Management")
            self.console.print()
            
            choice = Prompt.ask("Select action", default="b")
            
            if choice == 'b':
                return
            elif choice == '1':
                if is_active:
                    self._control_service(service_name, "stop", display_name)
                else:
                    self._control_service(service_name, "start", display_name)
            elif choice == '2':
                if is_active:
                    self._control_service(service_name, "restart", display_name)
                else:
                    self._show_service_logs(service_name, display_name)
            elif choice == '3':
                if is_active:
                    self._show_service_logs(service_name, display_name)
                else:
                    self._show_service_details(service_name, display_name)
            elif choice == '4' and is_active:
                self._show_service_details(service_name, display_name)
            
        except Exception as e:
            self.console.print(f"[red]Error checking service status: {e}[/red]")
            self._pause()
    
    def _control_service(self, service_name: str, action: str, display_name: str) -> None:
        """Control service (start/stop/restart)."""
        if action in ["stop", "restart"] and not Confirm.ask(f"{action.title()} {display_name}?", default=False):
            return
        
        self.console.print(f"[blue]{action.title()}ing {display_name}...[/blue]")
        
        try:
            result = subprocess.run(
                ["sudo", "systemctl", action, service_name],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                self.console.print(f"[green]✓ {display_name} {action}ed successfully[/green]")
            else:
                self.console.print(f"[red]✗ Failed to {action} {display_name}: {result.stderr.strip()}[/red]")
                
        except Exception as e:
            self.console.print(f"[red]Error {action}ing service: {e}[/red]")
        
        self._pause()
    
    def _show_service_logs(self, service_name: str, display_name: str) -> None:
        """Show recent service logs."""
        title = Text(f"{display_name} Recent Logs", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len(f"{display_name} Recent Logs"), style="dim"))
        
        try:
            result = subprocess.run(
                ["journalctl", "-u", service_name, "-n", "50", "--no-pager"],
                capture_output=True, text=True, timeout=15
            )
            
            if result.returncode == 0:
                logs = result.stdout.strip()
                if logs:
                    # Display logs with syntax highlighting for common patterns
                    for line in logs.split('\n')[-20:]:  # Show last 20 lines
                        if "ERROR" in line or "error" in line:
                            self.console.print(f"[red]{line}[/red]")
                        elif "WARN" in line or "warning" in line:
                            self.console.print(f"[yellow]{line}[/yellow]")
                        elif "INFO" in line or "info" in line:
                            self.console.print(f"[cyan]{line}[/cyan]")
                        else:
                            self.console.print(f"[dim]{line}[/dim]")
                else:
                    self.console.print("[yellow]No recent logs found.[/yellow]")
            else:
                self.console.print(f"[red]Failed to retrieve logs: {result.stderr.strip()}[/red]")
                
        except Exception as e:
            self.console.print(f"[red]Error retrieving logs: {e}[/red]")
        
        self._pause()
    
    def _show_service_details(self, service_name: str, display_name: str) -> None:
        """Show detailed service status."""
        title = Text(f"{display_name} Service Details", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len(f"{display_name} Service Details"), style="dim"))
        
        try:
            result = subprocess.run(
                ["systemctl", "status", service_name, "--no-pager", "-l"],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0 or result.stdout.strip():
                # Parse and display key information
                lines = result.stdout.split('\n')
                for line in lines[:15]:  # Show first 15 lines
                    if "Active:" in line:
                        if "active (running)" in line:
                            self.console.print(f"[green]{line}[/green]")
                        elif "inactive" in line or "failed" in line:
                            self.console.print(f"[red]{line}[/red]")
                        else:
                            self.console.print(f"[yellow]{line}[/yellow]")
                    elif "Loaded:" in line:
                        self.console.print(f"[cyan]{line}[/cyan]")
                    else:
                        self.console.print(f"[dim]{line}[/dim]")
            else:
                self.console.print(f"[red]Failed to get service details: {result.stderr.strip()}[/red]")
                
        except Exception as e:
            self.console.print(f"[red]Error getting service details: {e}[/red]")
        
        self._pause()
    
    def _restart_all_services(self) -> None:
        """Restart all Azazel services."""
        title = Text("Restarting All Azazel Services", style="bold red")
        self.console.print(title)
        self.console.print(Text("─" * len("Restarting All Azazel Services"), style="dim"))
        
        services = [
            "azctl-unified.service",
            "suricata.service",
            "opencanary.service",
            "vector.service",
        ]
        
        if not Confirm.ask("This will restart all Azazel services. Continue?", default=False):
            return
        
        for service in services:
            self.console.print(f"[blue]Restarting {service}...[/blue]")
            try:
                result = subprocess.run(
                    ["sudo", "systemctl", "restart", service],
                    capture_output=True, text=True, timeout=30
                )
                
                if result.returncode == 0:
                    self.console.print(f"[green]✓ {service} restarted successfully[/green]")
                else:
                    self.console.print(f"[red]✗ Failed to restart {service}: {result.stderr.strip()}[/red]")
                    
            except Exception as e:
                self.console.print(f"[red]✗ Error restarting {service}: {e}[/red]")
        
        self.console.print("\n[bold]All services restart attempts completed.[/bold]")
        self._pause()
    
    def _pause(self) -> None:
        """Pause for user input."""
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="", show_default=False)