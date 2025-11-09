#!/usr/bin/env python3
"""
Wi-Fi Management Module

Provides Wi-Fi network scanning, connection, and management functionality
for the Azazel TUI menu system.
"""

import re
import subprocess
import time
from typing import List, Dict, Optional, Tuple, Any

from rich.console import Console
from rich.progress import Progress
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text


class WiFiManager:
    """Wi-Fi connection and network management."""
    
    def __init__(self, console: Console):
        self.console = console
    
    def manage_wifi(self, wan_if: Optional[str] = None) -> None:
        """Wi-Fi connection manager entry point.

        If wan_if is not provided, resolve it using the WANManager active
        interface accessor so callers get the WANManager-driven default.
        """
        self.console.clear()
        self._print_section_header("Wi-Fi Connection Manager")

        # Resolve default WAN interface from WANManager if not provided
        if wan_if is None:
            try:
                from azazel_pi.utils.wan_state import get_active_wan_interface
                wan_if = get_active_wan_interface()
            except Exception:
                wan_if = "wlan1"

        # Check if required tools are available
        if not self._check_wifi_tools():
            return
        
        # Get available interfaces
        interfaces = self._get_wifi_interfaces()
        if not interfaces:
            self.console.print("[red]No Wi-Fi interfaces found.[/red]")
            return
        
        # Select interface if multiple available
        if len(interfaces) > 1:
            interface = self._select_wifi_interface(interfaces)
            if not interface:
                return
        else:
            interface = interfaces[0]
        
        self.console.print(f"[green]Using interface: {interface}[/green]")
        self.console.print()
        
        while True:
            choice = self._wifi_main_menu(interface)
            if choice == 'b':
                break
            elif choice == '1':
                self._wifi_scan_and_connect(interface)
            elif choice == '2':
                self._wifi_show_current_connection(interface)
            elif choice == '3':
                self._wifi_disconnect(interface)
            elif choice == '4':
                self._wifi_saved_networks(interface)
    
    def _print_section_header(self, title: str, style: str = "bold") -> None:
        """Print a consistent section header with underline."""
        title_text = Text(title, style=style)
        self.console.print(title_text)
        self.console.print(Text("─" * len(title), style="dim"))
    
    def _pause(self) -> None:
        """Pause for user input."""
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="", show_default=False)
    
    def _check_wifi_tools(self) -> bool:
        """Check if required Wi-Fi tools are available."""
        required_tools = ['iw', 'wpa_cli', 'dhcpcd']
        missing_tools = []
        
        for tool in required_tools:
            result = subprocess.run(['which', tool], capture_output=True, text=True)
            if result.returncode != 0:
                missing_tools.append(tool)
        
        if missing_tools:
            self.console.print(f"[red]Missing required tools: {', '.join(missing_tools)}[/red]")
            self.console.print("[yellow]Please install missing tools and try again.[/yellow]")
            self._pause()
            return False
        return True
    
    def _get_wifi_interfaces(self) -> List[str]:
        """Get list of available Wi-Fi interfaces."""
        try:
            result = subprocess.run(['iw', 'dev'], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return []
            
            interfaces = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith('Interface '):
                    interface = line.split()[1]
                    interfaces.append(interface)
            
            return interfaces
        except Exception:
            return []
    
    def _select_wifi_interface(self, interfaces: List[str]) -> Optional[str]:
        """Let user select Wi-Fi interface."""
        self.console.print("[bold]Available Wi-Fi Interfaces:[/bold]")
        for i, iface in enumerate(interfaces, 1):
            self.console.print(f"[cyan]{i}.[/cyan] {iface}")
        
        choice = Prompt.ask("Select interface", choices=[str(i) for i in range(1, len(interfaces) + 1)], default="1")
        return interfaces[int(choice) - 1]
    
    def _wifi_main_menu(self, interface: str) -> str:
        """Display Wi-Fi management main menu."""
        title_text = f"Wi-Fi Management - {interface}"
        title = Text(title_text, style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len(title_text), style="dim"))
        
        self.console.print("[cyan]1.[/cyan] Scan and Connect to Network")
        self.console.print("[cyan]2.[/cyan] Show Current Connection")  
        self.console.print("[cyan]3.[/cyan] Disconnect")
        self.console.print("[cyan]4.[/cyan] Manage Saved Networks")
        self.console.print()
        self.console.print("[cyan]b.[/cyan] Back to Network Information menu")
        self.console.print()
        
        return Prompt.ask("Select option", default="b")
    
    def _wifi_scan_and_connect(self, interface: str) -> None:
        """Scan for networks and connect to selected one."""
        self.console.print(f"[blue]Scanning for Wi-Fi networks on {interface}...[/blue]")
        
        try:
            with Progress() as progress:
                scan_task = progress.add_task("Scanning networks...", total=100)
                
                # Perform scan
                result = subprocess.run(
                    ['sudo', 'iw', 'dev', interface, 'scan'],
                    capture_output=True, text=True, timeout=15
                )
                progress.update(scan_task, completed=100)
                
                if result.returncode != 0:
                    self.console.print(f"[red]Scan failed: {result.stderr.strip()}[/red]")
                    self._pause()
                    return
            
            # Parse scan results
            networks = self._parse_wifi_scan(result.stdout)
            if not networks:
                self.console.print("[yellow]No networks found.[/yellow]")
                self._pause()
                return
            
            # Display networks and let user select
            selected_network = self._select_wifi_network(networks)
            if not selected_network:
                return
            
            # Connect to selected network
            self._connect_to_wifi_network(interface, selected_network)
            
        except subprocess.TimeoutExpired:
            self.console.print("[red]Scan timeout. Try again.[/red]")
            self._pause()
        except Exception as e:
            self.console.print(f"[red]Scan error: {e}[/red]")
            self._pause()
    
    def _parse_wifi_scan(self, scan_output: str) -> List[Dict[str, Any]]:
        """Parse iw scan output into network list."""
        networks = []
        current_network = None
        rsn_block = False
        wpa_block = False
        
        for line in scan_output.splitlines():
            line = line.rstrip()
            
            # New BSS entry
            bss_match = re.match(r"^BSS\s+([0-9a-f:]{17})", line)
            if bss_match:
                if current_network:
                    networks.append(current_network)
                current_network = {
                    "bssid": bss_match.group(1),
                    "ssid": "",
                    "freq": None,
                    "channel": None,
                    "signal": None,
                    "security": "OPEN",
                    "rsn": False,
                    "wpa": False,
                    "wpa3": False
                }
                rsn_block = False
                wpa_block = False
                continue
            
            if not current_network:
                continue
            
            # Parse network properties
            if line.strip().startswith("SSID:"):
                current_network["ssid"] = line.split("SSID:", 1)[1].strip()
            elif line.strip().startswith("freq:"):
                try:
                    freq = int(line.split("freq:", 1)[1].strip())
                    current_network["freq"] = freq
                    # Calculate channel from frequency
                    if 2412 <= freq <= 2472:
                        current_network["channel"] = (freq - 2407) // 5
                    elif freq == 2484:
                        current_network["channel"] = 14
                    elif 5000 <= freq <= 5900:
                        current_network["channel"] = (freq - 5000) // 5
                except Exception:
                    pass
            elif line.strip().startswith("signal:"):
                try:
                    signal_str = line.split("signal:", 1)[1].split("dBm")[0].strip()
                    current_network["signal"] = float(signal_str)
                except Exception:
                    pass
            elif line.strip().startswith("RSN:"):
                current_network["rsn"] = True
                current_network["security"] = "WPA2/WPA3"
                rsn_block = True
                wpa_block = False
            elif line.strip().startswith("WPA:"):
                current_network["wpa"] = True
                if current_network["security"] == "OPEN":
                    current_network["security"] = "WPA/WPA2"
                wpa_block = True
                rsn_block = False
            elif (rsn_block or wpa_block) and "SAE" in line:
                current_network["wpa3"] = True
                current_network["security"] = "WPA3/WPA2"
        
        # Add the last network
        if current_network:
            networks.append(current_network)
        
        # Remove duplicates and sort by signal strength
        unique_networks = {}
        for network in networks:
            ssid = network["ssid"] or f"<hidden:{network['bssid']}>"
            if ssid not in unique_networks or (
                network["signal"] is not None and 
                (unique_networks[ssid]["signal"] is None or 
                 network["signal"] > unique_networks[ssid]["signal"])
            ):
                unique_networks[ssid] = network
        
        result = list(unique_networks.values())
        result.sort(key=lambda x: x["signal"] if x["signal"] is not None else -999, reverse=True)
        
        return result
    
    def _select_wifi_network(self, networks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Display networks and let user select one."""
        self.console.clear()
        self._print_section_header("Available Wi-Fi Networks")
        
        # Create table
        table = Table()
        table.add_column("#", style="cyan", width=3)
        table.add_column("SSID", style="white", min_width=20)
        table.add_column("Security", style="yellow", width=15)
        table.add_column("Signal", justify="right", width=8)
        table.add_column("Channel", justify="center", width=7)
        table.add_column("BSSID", style="dim", width=17)
        
        for i, network in enumerate(networks[:20], 1):  # Limit to 20 networks
            ssid = network["ssid"] or f"<hidden>"
            signal = f"{int(network['signal'])} dBm" if network["signal"] is not None else "N/A"
            channel = str(network["channel"]) if network["channel"] else "N/A"
            
            # Color code signal strength
            if network["signal"] is not None:
                if network["signal"] > -50:
                    signal_style = "green"
                elif network["signal"] > -70:
                    signal_style = "yellow"
                else:
                    signal_style = "red"
            else:
                signal_style = "dim"
            
            table.add_row(
                str(i),
                ssid[:32],
                network["security"],
                Text(signal, style=signal_style),
                channel,
                network["bssid"]
            )
        
        self.console.print(table)
        self.console.print()
        
        if len(networks) > 20:
            self.console.print(f"[dim]Showing top 20 of {len(networks)} networks[/dim]")
        
        self.console.print("[cyan]r.[/cyan] Refresh scan")
        self.console.print("[cyan]b.[/cyan] Back")
        self.console.print()
        
        choice = Prompt.ask("Select network (number) or action", default="b")
        
        if choice == 'r':
            return self._wifi_scan_and_connect(networks[0]["bssid"].split(':')[0])  # Trigger rescan
        elif choice == 'b':
            return None
        
        try:
            network_idx = int(choice) - 1
            if 0 <= network_idx < min(len(networks), 20):
                return networks[network_idx]
        except ValueError:
            pass
        
        self.console.print("[red]Invalid selection.[/red]")
        self._pause()
        return None
    
    def _connect_to_wifi_network(self, interface: str, network: Dict[str, Any]) -> None:
        """Connect to selected Wi-Fi network."""
        ssid = network["ssid"] or f"<hidden:{network['bssid']}>"
        is_open = network["security"] == "OPEN"
        
        self.console.print(f"[blue]Connecting to: {ssid}[/blue]")
        self.console.print(f"Security: {network['security']}")
        
        if not is_open:
            # Need passphrase
            passphrase = Prompt.ask(f"Enter passphrase for '{ssid}'", password=True)
            if not passphrase:
                self.console.print("[yellow]Connection cancelled.[/yellow]")
                self._pause()
                return
        
        try:
            # Get current connection for rollback
            current_id, current_ssid, _ = self._get_current_wifi_connection(interface)
            
            # Check if network already exists
            network_id = self._find_wifi_network_id(ssid, interface)
            created_new = False
            
            if network_id is None:
                # Create new network
                result = subprocess.run(
                    ['sudo', 'wpa_cli', '-i', interface, 'add_network'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode != 0 or not result.stdout.strip().isdigit():
                    self.console.print("[red]Failed to add network configuration.[/red]")
                    self._pause()
                    return
                
                network_id = result.stdout.strip()
                created_new = True
                
                # Configure network
                subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'set_network', network_id, 'ssid', f'"{ssid}"'], 
                             capture_output=True, timeout=10)
                
                if is_open:
                    subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'set_network', network_id, 'key_mgmt', 'NONE'], 
                                 capture_output=True, timeout=10)
                else:
                    subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'set_network', network_id, 'psk', f'"{passphrase}"'], 
                                 capture_output=True, timeout=10)
            
            # Attempt connection
            with Progress() as progress:
                connect_task = progress.add_task("Connecting...", total=100)
                
                subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'enable_network', network_id], 
                             capture_output=True, timeout=10)
                subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'select_network', network_id], 
                             capture_output=True, timeout=10)
                
                # Wait for connection with timeout
                connected = False
                for i in range(20):  # 10 seconds
                    progress.update(connect_task, completed=(i + 1) * 5)
                    
                    result = subprocess.run(['wpa_cli', '-i', interface, 'status'], 
                                          capture_output=True, text=True, timeout=5)
                    
                    if result.returncode == 0:
                        status = result.stdout
                        if "wpa_state=COMPLETED" in status and f"ssid={ssid}" in status:
                            connected = True
                            break
                    
                    time.sleep(0.5)
                
                progress.update(connect_task, completed=100)
            
            if connected:
                # Get IP address
                subprocess.run(['sudo', 'dhcpcd', '-n', interface], capture_output=True, timeout=10)
                # Save configuration
                subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'save_config'], capture_output=True, timeout=10)
                
                self.console.print(f"[green]✓ Successfully connected to {ssid}[/green]")
                
                # Show connection info
                self._wifi_show_current_connection(interface)
                
            else:
                self.console.print("[red]✗ Connection failed[/red]")
                
                # Rollback
                if created_new and network_id:
                    subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'remove_network', network_id], 
                                 capture_output=True, timeout=10)
                
                if current_id:
                    subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'select_network', current_id], 
                                 capture_output=True, timeout=10)
                    subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'reassociate'], 
                                 capture_output=True, timeout=10)
        
        except Exception as e:
            self.console.print(f"[red]Connection error: {e}[/red]")
        
        self._pause()
    
    def _find_wifi_network_id(self, ssid: str, interface: str) -> Optional[str]:
        """Find network ID for given SSID."""
        try:
            result = subprocess.run(['wpa_cli', '-i', interface, 'list_networks'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return None
            
            for line in result.stdout.splitlines()[1:]:  # Skip header
                parts = line.split('\t')
                if len(parts) >= 2 and parts[1] == ssid:
                    return parts[0]
            
            return None
        except Exception:
            return None
    
    def _get_current_wifi_connection(self, interface: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Get current Wi-Fi connection info."""
        try:
            result = subprocess.run(['wpa_cli', '-i', interface, 'status'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return None, None, None
            
            current_id = None
            current_ssid = None
            current_bssid = None
            
            for line in result.stdout.splitlines():
                if line.startswith("id="):
                    current_id = line.split("=", 1)[1]
                elif line.startswith("ssid="):
                    current_ssid = line.split("=", 1)[1]
                elif line.startswith("bssid="):
                    current_bssid = line.split("=", 1)[1]
            
            return current_id, current_ssid, current_bssid
        except Exception:
            return None, None, None
    
    def _wifi_show_current_connection(self, interface: str) -> None:
        """Show current Wi-Fi connection details."""
        self._print_section_header(f"Current Wi-Fi Connection - {interface}")
        
        try:
            # Get wpa_cli status
            result = subprocess.run(['wpa_cli', '-i', interface, 'status'], 
                                  capture_output=True, text=True, timeout=5)
            
            if result.returncode != 0:
                self.console.print("[red]Failed to get connection status.[/red]")
                self._pause()
                return
            
            # Parse status
            status_info = {}
            for line in result.stdout.splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    status_info[key] = value
            
            # Get IP information
            ip_result = subprocess.run(['ip', '-4', 'addr', 'show', interface], 
                                     capture_output=True, text=True, timeout=5)
            
            ip_addr = "Not assigned"
            if ip_result.returncode == 0:
                for line in ip_result.stdout.splitlines():
                    if 'inet ' in line and 'scope global' in line:
                        ip_addr = line.strip().split()[1]
                        break
            
            # Display connection info
            from rich.panel import Panel
            table = Table.grid(padding=(0, 2))
            table.add_column("Property", style="cyan", min_width=15)
            table.add_column("Value", style="white")
            
            wpa_state = status_info.get('wpa_state', 'UNKNOWN')
            if wpa_state == 'COMPLETED':
                state_display = Text("Connected", style="green")
            elif wpa_state in ['ASSOCIATING', 'ASSOCIATED', 'AUTHENTICATING']:
                state_display = Text("Connecting", style="yellow")
            else:
                state_display = Text("Disconnected", style="red")
            
            table.add_row("Status", state_display)
            table.add_row("SSID", status_info.get('ssid', 'N/A'))
            table.add_row("BSSID", status_info.get('bssid', 'N/A'))
            table.add_row("IP Address", ip_addr)
            table.add_row("Frequency", f"{status_info.get('freq', 'N/A')} MHz")
            
            if 'key_mgmt' in status_info:
                table.add_row("Security", status_info['key_mgmt'])
            
            self.console.print(Panel(table, title="Connection Details", border_style="green"))
            
        except Exception as e:
            self.console.print(f"[red]Error getting connection info: {e}[/red]")
        
        self._pause()
    
    def _wifi_disconnect(self, interface: str) -> None:
        """Disconnect from current Wi-Fi network."""
        if not Confirm.ask(f"Disconnect from current network on {interface}?", default=False):
            return
        
        try:
            result = subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'disconnect'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                self.console.print("[green]✓ Disconnected successfully[/green]")
            else:
                self.console.print(f"[red]✗ Disconnect failed: {result.stderr.strip()}[/red]")
        
        except Exception as e:
            self.console.print(f"[red]Disconnect error: {e}[/red]")
        
        self._pause()
    
    def _wifi_saved_networks(self, interface: str) -> None:
        """Show and manage saved Wi-Fi networks."""
        self._print_section_header(f"Saved Wi-Fi Networks - {interface}")
        
        try:
            result = subprocess.run(['wpa_cli', '-i', interface, 'list_networks'], 
                                  capture_output=True, text=True, timeout=5)
            
            if result.returncode != 0:
                self.console.print("[red]Failed to get saved networks.[/red]")
                self._pause()
                return
            
            lines = result.stdout.splitlines()
            if len(lines) <= 1:
                self.console.print("[yellow]No saved networks found.[/yellow]")
                self._pause()
                return
            
            # Parse and display networks
            table = Table()
            table.add_column("ID", style="cyan", width=5)
            table.add_column("SSID", style="white", min_width=20)
            table.add_column("BSSID", style="dim", width=17)
            table.add_column("Flags", style="yellow", width=15)
            
            networks = []
            for line in lines[1:]:  # Skip header
                parts = line.split('\t')
                if len(parts) >= 2:
                    network_id = parts[0]
                    ssid = parts[1]
                    bssid = parts[2] if len(parts) > 2 else "any"
                    flags = parts[3] if len(parts) > 3 else ""
                    
                    networks.append({
                        'id': network_id,
                        'ssid': ssid,
                        'bssid': bssid,
                        'flags': flags
                    })
                    
                    # Color code flags
                    flag_display = flags
                    if 'CURRENT' in flags:
                        flag_display = Text(flags, style="green")
                    elif 'DISABLED' in flags:
                        flag_display = Text(flags, style="red")
                    else:
                        flag_display = Text(flags, style="yellow")
                    
                    table.add_row(network_id, ssid, bssid, flag_display)
            
            self.console.print(table)
            
            if networks:
                self.console.print("\n[cyan]Actions:[/cyan]")
                self.console.print("Enter network ID to enable/disable")
                self.console.print("'d' + ID to delete (e.g., 'd2')")
                
                choice = Prompt.ask("Action or 'b' to go back", default="b")
                
                if choice != 'b':
                    if choice.startswith('d') and len(choice) > 1:
                        # Delete network
                        net_id = choice[1:]
                        if Confirm.ask(f"Delete network ID {net_id}?", default=False):
                            result = subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'remove_network', net_id], 
                                                  capture_output=True, text=True, timeout=10)
                            if result.returncode == 0:
                                subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'save_config'], 
                                             capture_output=True, timeout=10)
                                self.console.print(f"[green]✓ Network {net_id} deleted[/green]")
                            else:
                                self.console.print(f"[red]✗ Failed to delete network {net_id}[/red]")
                    elif choice.isdigit():
                        # Enable/disable network
                        net_id = choice
                        result = subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'enable_network', net_id], 
                                              capture_output=True, text=True, timeout=10)
                        if result.returncode == 0:
                            self.console.print(f"[green]✓ Network {net_id} enabled[/green]")
                        else:
                            self.console.print(f"[red]✗ Failed to enable network {net_id}[/red]")
        
        except Exception as e:
            self.console.print(f"[red]Error managing saved networks: {e}[/red]")
        
        self._pause()