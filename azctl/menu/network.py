#!/usr/bin/env python3
"""
Network Management Module

Provides network interface status, Wi-Fi management, and traffic monitoring
functionality for the Azazel TUI menu system.
"""

from typing import Optional, Any

from rich.console import Console

from .types import MenuCategory, MenuAction
from .wifi import WiFiManager
from ..cli import _wlan_ap_status, _wlan_link_info, _active_profile

try:
    from ..core.ingest.status_collector import NetworkStatusCollector
except ImportError:
    NetworkStatusCollector = None


class NetworkModule:
    """Network information and management functionality."""
    
    def __init__(self, console: Console, lan_if: str = "wlan0", wan_if: str = "wlan1", 
                 status_collector: Optional[Any] = None):
        self.console = console
        self.lan_if = lan_if
        self.wan_if = wan_if
        self.status_collector = status_collector
        
        # Initialize Wi-Fi manager
        self.wifi_manager = WiFiManager(console)
    
    def get_category(self) -> MenuCategory:
        """Get the network management menu category."""
        return MenuCategory(
            title="Network Information",
            description="View and manage network configuration",
            actions=[
                MenuAction("Network Interface Status", "Display WLAN interface information", self._show_interface_status),
                MenuAction("Wi-Fi Connection Manager 🔒", "Scan and connect to available Wi-Fi networks", self._manage_wifi, requires_root=True),
                MenuAction("Active Profile", "Show current network profile configuration", self._show_active_profile),
                MenuAction("Traffic Statistics", "Display network traffic information", self._traffic_stats),
            ]
        )
    
    def _show_interface_status(self) -> None:
        """Display detailed network interface status."""
        self._print_section_header("Network Interface Status")
        
        wlan0 = _wlan_ap_status(self.lan_if)
        wlan1 = _wlan_link_info(self.wan_if)
        
        # Create layout for both interfaces
        from rich.layout import Layout
        from rich.table import Table
        
        layout = Layout()
        layout.split_row(
            Layout(name="lan"),
            Layout(name="wan")
        )
        
        # LAN interface (AP) table
        lan_table = Table(show_header=False, box=None)
        lan_table.add_column("Property", style="cyan", min_width=15)
        lan_table.add_column("Value", style="white")
        
        lan_table.add_row("Mode", "Access Point" if wlan0.get('is_ap') else "Station")
        lan_table.add_row("Status", "[green]Active[/green]" if wlan0.get('is_ap') else "[red]Inactive[/red]")
        
        if wlan0.get('ssid'):
            lan_table.add_row("SSID", wlan0['ssid'])
        if wlan0.get('channel'):
            lan_table.add_row("Channel", str(wlan0['channel']))
        if wlan0.get('stations') is not None:
            lan_table.add_row("Connected Clients", str(wlan0['stations']))
        
        from rich.panel import Panel
        layout["lan"].update(Panel(lan_table, title=f"{self.lan_if} (LAN)", border_style="cyan"))
        
        # WAN interface table
        wan_table = Table(show_header=False, box=None)
        wan_table.add_column("Property", style="cyan", min_width=15)
        wan_table.add_column("Value", style="white")
        
        if wlan1.get('connected'):
            wan_table.add_row("Status", "[green]Connected[/green]")
            wan_table.add_row("SSID", wlan1.get('ssid', 'N/A'))
            wan_table.add_row("IP Address", wlan1.get('ip4', 'N/A'))
            if wlan1.get('signal_dbm'):
                signal_color = "green" if wlan1['signal_dbm'] > -50 else "yellow" if wlan1['signal_dbm'] > -70 else "red"
                wan_table.add_row("Signal", f"[{signal_color}]{wlan1['signal_dbm']} dBm[/{signal_color}]")
            if wlan1.get('tx_bitrate'):
                wan_table.add_row("TX Bitrate", wlan1['tx_bitrate'])
            if wlan1.get('rx_bitrate'):
                wan_table.add_row("RX Bitrate", wlan1['rx_bitrate'])
        else:
            wan_table.add_row("Status", "[red]Disconnected[/red]")
            wan_table.add_row("SSID", "N/A")
            wan_table.add_row("IP Address", "N/A")
        
        layout["wan"].update(Panel(wan_table, title=f"{self.wan_if} (WAN)", border_style="yellow"))
        
        self.console.print(layout)
        self._pause()
    
    def _manage_wifi(self) -> None:
        """Launch Wi-Fi connection manager."""
        self.wifi_manager.manage_wifi(self.wan_if)
    
    def _show_active_profile(self) -> None:
        """Display active network profile configuration."""
        self._print_section_header("Active Network Profile Configuration")
        
        profile_name = _active_profile()
        
        if not profile_name:
            self.console.print("[yellow]No active profile detected.[/yellow]")
            self._pause()
            return
        
        self.console.print(f"[green]Active Profile: {profile_name}[/green]")
        
        # Try to read profile configuration
        from pathlib import Path
        import yaml
        
        profile_path = Path(f"/etc/azazel/profiles/{profile_name}.yaml")
        if not profile_path.exists():
            profile_path = Path(f"configs/profiles/{profile_name}.yaml")
        
        if profile_path.exists():
            try:
                with open(profile_path, 'r') as f:
                    config = yaml.safe_load(f)
                
                from rich.table import Table
                
                for section_name, section_data in config.items():
                    if isinstance(section_data, dict):
                        table = Table(show_header=False, title=section_name.replace('_', ' ').title())
                        table.add_column("Setting", style="cyan", min_width=20)
                        table.add_column("Value", style="white")
                        
                        for key, value in section_data.items():
                            if isinstance(value, (list, dict)):
                                value = str(value)
                            table.add_row(key.replace('_', ' ').title(), str(value))
                        
                        from rich.panel import Panel
                        panel = Panel(table, title=section_name, border_style="blue")
                        self.console.print(panel)
                        self.console.print()
                
            except Exception as e:
                self.console.print(f"[red]Error reading profile: {e}[/red]")
        else:
            self.console.print(f"[yellow]Profile configuration file not found: {profile_path}[/yellow]")
        
        self._pause()
    
    def _traffic_stats(self) -> None:
        """Display network traffic statistics."""
        self._print_section_header("Network Traffic Statistics")
        
        if self.status_collector is None:
            self.console.print("[yellow]Status collector not available. Attempting to collect basic statistics...[/yellow]")
            self._show_basic_traffic_stats()
            return
        
        try:
            status = self.status_collector.collect()
        except Exception as e:
            self.console.print(f"[red]Error collecting statistics: {e}[/red]")
            self.console.print("[yellow]Falling back to basic statistics...[/yellow]")
            self._show_basic_traffic_stats()
            return
        
        # Create main statistics table
        from rich.table import Table
        
        stats_table = Table()
        stats_table.add_column("Interface", style="cyan")
        stats_table.add_column("RX Bytes", justify="right", style="green")
        stats_table.add_column("TX Bytes", justify="right", style="blue")
        stats_table.add_column("RX Packets", justify="right", style="green")
        stats_table.add_column("TX Packets", justify="right", style="blue")
        stats_table.add_column("Errors", justify="right", style="red")
        
        # Add interface statistics
        for interface, stats in status.get('interfaces', {}).items():
            if interface in [self.lan_if, self.wan_if, 'eth0']:
                rx_bytes = self._format_bytes(stats.get('rx_bytes', 0))
                tx_bytes = self._format_bytes(stats.get('tx_bytes', 0))
                rx_packets = f"{stats.get('rx_packets', 0):,}"
                tx_packets = f"{stats.get('tx_packets', 0):,}"
                errors = stats.get('rx_errors', 0) + stats.get('tx_errors', 0)
                
                stats_table.add_row(
                    interface,
                    rx_bytes,
                    tx_bytes,
                    rx_packets,
                    tx_packets,
                    str(errors) if errors > 0 else "0"
                )
        
        from rich.panel import Panel
        panel = Panel(stats_table, title="Current Statistics", border_style="green")
        self.console.print(panel)
        
        self._pause()
    
    def _show_basic_traffic_stats(self) -> None:
        """Display basic network traffic statistics using /proc/net/dev."""
        try:
            import subprocess
            from rich.table import Table
            from rich.panel import Panel
            
            # Read network statistics from /proc/net/dev
            with open('/proc/net/dev', 'r') as f:
                lines = f.readlines()
            
            stats_table = Table()
            stats_table.add_column("Interface", style="cyan")
            stats_table.add_column("RX Bytes", justify="right", style="green")
            stats_table.add_column("TX Bytes", justify="right", style="blue")
            stats_table.add_column("RX Packets", justify="right", style="green")
            stats_table.add_column("TX Packets", justify="right", style="blue")
            stats_table.add_column("Errors", justify="right", style="red")
            
            for line in lines[2:]:  # Skip header lines
                fields = line.split()
                if len(fields) >= 17:
                    interface = fields[0].rstrip(':')
                    
                    # Only show relevant interfaces
                    if interface in [self.lan_if, self.wan_if, 'eth0', 'lo']:
                        rx_bytes = int(fields[1])
                        rx_packets = int(fields[2])
                        rx_errors = int(fields[3])
                        tx_bytes = int(fields[9])
                        tx_packets = int(fields[10])
                        tx_errors = int(fields[11])
                        
                        total_errors = rx_errors + tx_errors
                        
                        stats_table.add_row(
                            interface,
                            self._format_bytes(rx_bytes),
                            self._format_bytes(tx_bytes),
                            f"{rx_packets:,}",
                            f"{tx_packets:,}",
                            str(total_errors) if total_errors > 0 else "0"
                        )
            
            panel = Panel(stats_table, title="Network Interface Statistics", border_style="green")
            self.console.print(panel)
            
        except Exception as e:
            self.console.print(f"[red]Error reading basic statistics: {e}[/red]")
        
        self._pause()
    
    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes value with appropriate units."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} PB"
    
    def _print_section_header(self, title: str, style: str = "bold") -> None:
        """Print a consistent section header with underline."""
        from rich.text import Text
        title_text = Text(title, style=style)
        self.console.print(title_text)
        self.console.print(Text("─" * len(title), style="dim"))
    
    def _pause(self) -> None:
        """Pause for user input."""
        from rich.prompt import Prompt
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="", show_default=False)