#!/usr/bin/env python3
"""
System Information Module

Provides system monitoring and resource information for the Azazel TUI menu system.
"""

import subprocess
from typing import Optional, Any

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt

from azctl.menu.types import MenuCategory, MenuAction

try:
    from azazel_pi.core.ingest.status_collector import NetworkStatusCollector
except ImportError:
    NetworkStatusCollector = None


class SystemModule:
    """System information and monitoring functionality."""
    
    def __init__(self, console: Console, status_collector: Optional[Any] = None):
        self.console = console
        self.status_collector = status_collector
    
    def get_category(self) -> MenuCategory:
        """Get the system information menu category."""
        return MenuCategory(
            title="System Information",
            description="View system status and resources",
            actions=[
                MenuAction("System Resource Monitor", "Display CPU, memory, and disk usage", self._system_resources),
                MenuAction("Network Statistics", "Show detailed network interface statistics", self._network_stats),
                MenuAction("Temperature Monitor", "Display system temperature readings", self._temperature_monitor),
                MenuAction("Process List", "Show running processes", self._process_list),
            ]
        )
    
    def _system_resources(self) -> None:
        """Display system resource information."""
        title = Text("System Resource Monitor", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len("System Resource Monitor"), style="dim"))
        
        try:
            if self.status_collector:
                status = self.status_collector.collect()
            else:
                status = {}
            
            # CPU Information
            self.console.print("[bold cyan]CPU Information:[/bold cyan]")
            cpu_table = Table(show_header=False, box=None)
            cpu_table.add_column("Metric", style="cyan", min_width=15)
            cpu_table.add_column("Value", style="white")
            
            # Get CPU info
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    cpuinfo = f.read()
                    
                model_name = "Unknown"
                cpu_cores = 0
                for line in cpuinfo.split('\n'):
                    if line.startswith('model name'):
                        model_name = line.split(':', 1)[1].strip()
                    elif line.startswith('processor'):
                        cpu_cores += 1
                
                cpu_table.add_row("Model", model_name)
                cpu_table.add_row("Cores", str(cpu_cores))
                
            except Exception:
                cpu_table.add_row("CPU Info", "Unable to retrieve")
            
            # Load average
            try:
                with open('/proc/loadavg', 'r') as f:
                    load = f.read().strip().split()[:3]
                    cpu_table.add_row("Load Average", f"{load[0]} {load[1]} {load[2]}")
            except Exception:
                cpu_table.add_row("Load Average", "Unknown")
            
            self.console.print(cpu_table)
            self.console.print()
            
            # Memory Information
            self.console.print("[bold cyan]Memory Information:[/bold cyan]")
            mem_table = Table(show_header=False, box=None)
            mem_table.add_column("Type", style="cyan", min_width=15)
            mem_table.add_column("Total", justify="right", style="white")
            mem_table.add_column("Used", justify="right", style="yellow")
            mem_table.add_column("Free", justify="right", style="green")
            mem_table.add_column("Usage", justify="right", style="white")
            
            try:
                with open('/proc/meminfo', 'r') as f:
                    meminfo = {}
                    for line in f:
                        key, value = line.split(':', 1)
                        meminfo[key.strip()] = int(value.strip().split()[0]) * 1024  # Convert to bytes
                
                total_mem = meminfo.get('MemTotal', 0)
                free_mem = meminfo.get('MemFree', 0) + meminfo.get('Buffers', 0) + meminfo.get('Cached', 0)
                used_mem = total_mem - free_mem
                mem_usage = (used_mem / total_mem * 100) if total_mem > 0 else 0
                
                mem_table.add_row(
                    "RAM",
                    self._format_bytes(total_mem),
                    self._format_bytes(used_mem),
                    self._format_bytes(free_mem),
                    f"{mem_usage:.1f}%"
                )
                
            except Exception:
                mem_table.add_row("RAM", "Unknown", "Unknown", "Unknown", "Unknown")
            
            self.console.print(mem_table)
            self.console.print()
            
            # Disk Information
            self.console.print("[bold cyan]Disk Usage:[/bold cyan]")
            try:
                result = subprocess.run(['df', '-h', '/'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) >= 2:
                        disk_info = lines[1].split()
                        if len(disk_info) >= 5:
                            disk_table = Table(show_header=False, box=None)
                            disk_table.add_column("Filesystem", style="cyan", min_width=15)
                            disk_table.add_column("Size", justify="right", style="white")
                            disk_table.add_column("Used", justify="right", style="yellow")
                            disk_table.add_column("Available", justify="right", style="green")
                            disk_table.add_column("Usage", justify="right", style="white")
                            
                            disk_table.add_row(
                                "Root (/)",
                                disk_info[1],
                                disk_info[2], 
                                disk_info[3],
                                disk_info[4]
                            )
                            
                            self.console.print(disk_table)
                        else:
                            self.console.print("[yellow]Unable to parse disk usage[/yellow]")
                    else:
                        self.console.print("[yellow]No disk usage data available[/yellow]")
                else:
                    self.console.print("[red]Failed to get disk usage[/red]")
            except Exception as e:
                self.console.print(f"[red]Error getting disk usage: {e}[/red]")
            
        except Exception as e:
            self.console.print(f"[red]Error collecting system resources: {e}[/red]")
        
        self._pause()
    
    def _network_stats(self) -> None:
        """Show detailed network statistics."""
        title = Text("Network Interface Statistics", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len("Network Interface Statistics"), style="dim"))
        
        try:
            if self.status_collector:
                status = self.status_collector.collect()
                interfaces = status.get('interfaces', {})
                
                if interfaces:
                    table = Table()
                    table.add_column("Interface", style="cyan")
                    table.add_column("RX Bytes", justify="right", style="green")
                    table.add_column("TX Bytes", justify="right", style="blue")
                    table.add_column("RX Packets", justify="right", style="green")
                    table.add_column("TX Packets", justify="right", style="blue")
                    table.add_column("Errors", justify="right", style="red")
                    table.add_column("Drops", justify="right", style="yellow")
                    
                    for iface, stats in interfaces.items():
                        table.add_row(
                            iface,
                            self._format_bytes(stats.get('rx_bytes', 0)),
                            self._format_bytes(stats.get('tx_bytes', 0)),
                            f"{stats.get('rx_packets', 0):,}",
                            f"{stats.get('tx_packets', 0):,}",
                            str(stats.get('rx_errors', 0) + stats.get('tx_errors', 0)),
                            str(stats.get('rx_dropped', 0) + stats.get('tx_dropped', 0))
                        )
                    
                    self.console.print(table)
                else:
                    self.console.print("[yellow]No network interface data available[/yellow]")
            else:
                self.console.print("[yellow]Network status collector not available[/yellow]")
        
        except Exception as e:
            self.console.print(f"[red]Error collecting network statistics: {e}[/red]")
        
        self._pause()
    
    def _temperature_monitor(self) -> None:
        """Display system temperature readings."""
        title = Text("System Temperature Monitor", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len("System Temperature Monitor"), style="dim"))
        
        try:
            # Try to read Raspberry Pi temperature
            temp_paths = [
                '/sys/class/thermal/thermal_zone0/temp',
                '/sys/devices/virtual/thermal/thermal_zone0/temp'
            ]
            
            temp_found = False
            for temp_path in temp_paths:
                try:
                    with open(temp_path, 'r') as f:
                        temp_raw = int(f.read().strip())
                        temp_c = temp_raw / 1000.0
                        temp_f = (temp_c * 9/5) + 32
                        
                        # Color code temperature
                        if temp_c < 50:
                            temp_color = "green"
                        elif temp_c < 70:
                            temp_color = "yellow"
                        else:
                            temp_color = "red"
                        
                        temp_table = Table(show_header=False, box=None)
                        temp_table.add_column("Sensor", style="cyan", min_width=15)
                        temp_table.add_column("Temperature", style="white")
                        temp_table.add_column("Status", style="white")
                        
                        status = "Normal" if temp_c < 70 else "High" if temp_c < 80 else "Critical"
                        status_color = "green" if temp_c < 70 else "yellow" if temp_c < 80 else "red"
                        
                        temp_table.add_row(
                            "CPU",
                            f"[{temp_color}]{temp_c:.1f}°C ({temp_f:.1f}°F)[/{temp_color}]",
                            f"[{status_color}]{status}[/{status_color}]"
                        )
                        
                        self.console.print(temp_table)
                        temp_found = True
                        break
                        
                except Exception:
                    continue
            
            if not temp_found:
                self.console.print("[yellow]Temperature sensors not available[/yellow]")
        
        except Exception as e:
            self.console.print(f"[red]Error reading temperature: {e}[/red]")
        
        self._pause()
    
    def _process_list(self) -> None:
        """Show running processes."""
        title = Text("Running Processes", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len("Running Processes"), style="dim"))
        
        try:
            result = subprocess.run(
                ['ps', 'aux', '--sort=-pcpu'], 
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                
                if len(lines) > 1:
                    # Parse header
                    header = lines[0].split()
                    
                    # Create table
                    table = Table()
                    table.add_column("PID", style="cyan", width=8)
                    table.add_column("User", style="white", width=10)
                    table.add_column("CPU%", justify="right", style="yellow", width=6)
                    table.add_column("MEM%", justify="right", style="green", width=6)
                    table.add_column("Command", style="white")
                    
                    # Show top 15 processes
                    for line in lines[1:16]:
                        parts = line.split(None, 10)
                        if len(parts) >= 11:
                            table.add_row(
                                parts[1],  # PID
                                parts[0][:10],  # User (truncated)
                                parts[2],  # CPU%
                                parts[3],  # MEM%
                                parts[10][:50] + "..." if len(parts[10]) > 50 else parts[10]  # Command (truncated)
                            )
                    
                    self.console.print(table)
                else:
                    self.console.print("[yellow]No process information available[/yellow]")
            else:
                self.console.print(f"[red]Failed to get process list: {result.stderr.strip()}[/red]")
        
        except Exception as e:
            self.console.print(f"[red]Error getting process list: {e}[/red]")
        
        self._pause()
    
    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes value with appropriate units."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} PB"
    
    def _pause(self) -> None:
        """Pause for user input."""
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="", show_default=False)