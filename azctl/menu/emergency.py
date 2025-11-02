#!/usr/bin/env python3
"""
Emergency Operations Module

Provides emergency response and recovery operations for the Azazel TUI menu system.
"""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.text import Text
from rich.prompt import Prompt, Confirm

from .types import MenuCategory, MenuAction
from ..cli import _wlan_ap_status, _wlan_link_info


class EmergencyModule:
    """Emergency operations and recovery functionality."""
    
    def __init__(self, console: Console, lan_if: str = "wlan0", wan_if: str = "wlan1"):
        self.console = console
        self.lan_if = lan_if
        self.wan_if = wan_if
    
    def get_category(self) -> MenuCategory:
        """Get the emergency operations menu category."""
        return MenuCategory(
            title="Emergency Operations",
            description="Emergency response and recovery operations",
            actions=[
                MenuAction("Emergency Lockdown 🔒 ⚠️", "Immediately lock down all network access", self._emergency_lockdown, requires_root=True, dangerous=True),
                MenuAction("Reset Network Configuration 🔒 ⚠️", "Reset all network settings to defaults", self._reset_network, requires_root=True, dangerous=True),
                MenuAction("Generate System Report", "Create comprehensive system status report", self._system_report),
                MenuAction("Factory Reset 🔒 ⚠️", "Reset system to factory defaults", self._factory_reset, requires_root=True, dangerous=True),
            ]
        )
    
    def _emergency_lockdown(self) -> None:
        """Immediate emergency lockdown of all network access."""
        self.console.print("[bold red]EMERGENCY LOCKDOWN PROCEDURE[/bold red]")
        title = Text("Emergency Network Lockdown", style="bold red")
        self.console.print(title)
        self.console.print(Text("─" * len("Emergency Network Lockdown"), style="dim"))
        
        self.console.print("[yellow]This will immediately:")
        self.console.print("• Block all incoming and outgoing traffic")
        self.console.print("• Disconnect all wireless connections")
        self.console.print("• Stop all network services")
        self.console.print("• Switch to maximum security mode[/yellow]")
        self.console.print()
        
        if not Confirm.ask("[red]Proceed with emergency lockdown?[/red]", default=False):
            self.console.print("[yellow]Emergency lockdown cancelled.[/yellow]")
            self._pause()
            return
        
        self.console.print("[red]Initiating emergency lockdown...[/red]")
        
        try:
            # Step 1: Switch to lockdown mode
            self.console.print("[blue]1. Switching to lockdown mode...[/blue]")
            result = subprocess.run(
                ["python3", "-m", "azctl", "events", "--mode", "lockdown"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                self.console.print("[green]✓ Lockdown mode activated[/green]")
            else:
                self.console.print(f"[red]✗ Mode switch failed: {result.stderr.strip()}[/red]")
            
            # Step 2: Apply emergency firewall rules
            self.console.print("[blue]2. Applying emergency firewall rules...[/blue]")
            try:
                subprocess.run(["sudo", "nft", "flush", "ruleset"], timeout=10)
                subprocess.run([
                    "sudo", "nft", "add", "table", "inet", "emergency"
                ], timeout=5)
                subprocess.run([
                    "sudo", "nft", "add", "chain", "inet", "emergency", "input", 
                    "{", "type", "filter", "hook", "input", "priority", "0", ";", "policy", "drop", ";", "}"
                ], timeout=5)
                subprocess.run([
                    "sudo", "nft", "add", "chain", "inet", "emergency", "forward",
                    "{", "type", "filter", "hook", "forward", "priority", "0", ";", "policy", "drop", ";", "}"
                ], timeout=5)
                subprocess.run([
                    "sudo", "nft", "add", "chain", "inet", "emergency", "output",
                    "{", "type", "filter", "hook", "output", "priority", "0", ";", "policy", "drop", ";", "}"
                ], timeout=5)
                # Allow loopback
                subprocess.run([
                    "sudo", "nft", "add", "rule", "inet", "emergency", "input", "iif", "lo", "accept"
                ], timeout=5)
                subprocess.run([
                    "sudo", "nft", "add", "rule", "inet", "emergency", "output", "oif", "lo", "accept"
                ], timeout=5)
                
                self.console.print("[green]✓ Emergency firewall rules applied[/green]")
            except Exception as e:
                self.console.print(f"[red]✗ Firewall rules failed: {e}[/red]")
            
            # Step 3: Disconnect wireless
            self.console.print("[blue]3. Disconnecting wireless connections...[/blue]")
            try:
                subprocess.run(["sudo", "wpa_cli", "-i", self.wan_if, "disconnect"], timeout=10)
                self.console.print("[green]✓ Wireless connections disconnected[/green]")
            except Exception as e:
                self.console.print(f"[red]✗ Wireless disconnect failed: {e}[/red]")
            
            # Step 4: Stop services
            self.console.print("[blue]4. Stopping non-essential services...[/blue]")
            services_to_stop = ["vector", "opencanary"]
            for service in services_to_stop:
                try:
                    subprocess.run(["sudo", "systemctl", "stop", f"{service}.service"], timeout=15)
                    self.console.print(f"[green]✓ {service} stopped[/green]")
                except Exception:
                    self.console.print(f"[yellow]! {service} stop failed[/yellow]")
            
            self.console.print("\n[bold red]EMERGENCY LOCKDOWN COMPLETED[/bold red]")
            self.console.print("[yellow]System is now in maximum security lockdown mode.[/yellow]")
            self.console.print("[yellow]Manual intervention required to restore normal operations.[/yellow]")
            
        except Exception as e:
            self.console.print(f"[red]Emergency lockdown failed: {e}[/red]")
        
        self._pause()
    
    def _reset_network(self) -> None:
        """Reset network configuration to defaults."""
        title = Text("Reset Network Configuration", style="bold red")
        self.console.print(title)
        self.console.print(Text("─" * len("Reset Network Configuration"), style="dim"))
        
        self.console.print("[yellow]This will:")
        self.console.print("• Remove all saved Wi-Fi networks")
        self.console.print("• Reset network interfaces")
        self.console.print("• Restore default network configuration")
        self.console.print("• Restart network services[/yellow]")
        self.console.print()
        
        if not Confirm.ask("[red]Proceed with network reset?[/red]", default=False):
            return
        
        self.console.print("[blue]Resetting network configuration...[/blue]")
        
        try:
            # Reset wpa_supplicant configuration
            self.console.print("[blue]1. Resetting Wi-Fi configuration...[/blue]")
            try:
                subprocess.run(["sudo", "systemctl", "stop", "wpa_supplicant"], timeout=10)
                
                # Backup and reset wpa_supplicant.conf
                subprocess.run([
                    "sudo", "cp", "/etc/wpa_supplicant/wpa_supplicant.conf",
                    f"/etc/wpa_supplicant/wpa_supplicant.conf.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                ], timeout=5)
                
                # Create minimal wpa_supplicant.conf
                minimal_config = """ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US
"""
                with open("/tmp/wpa_supplicant_reset.conf", "w") as f:
                    f.write(minimal_config)
                
                subprocess.run([
                    "sudo", "cp", "/tmp/wpa_supplicant_reset.conf", 
                    "/etc/wpa_supplicant/wpa_supplicant.conf"
                ], timeout=5)
                
                subprocess.run(["sudo", "systemctl", "start", "wpa_supplicant"], timeout=10)
                self.console.print("[green]✓ Wi-Fi configuration reset[/green]")
                
            except Exception as e:
                self.console.print(f"[red]✗ Wi-Fi reset failed: {e}[/red]")
            
            # Reset network interfaces
            self.console.print("[blue]2. Resetting network interfaces...[/blue]")
            try:
                subprocess.run(["sudo", "ip", "link", "set", self.wan_if, "down"], timeout=5)
                subprocess.run(["sudo", "ip", "link", "set", self.wan_if, "up"], timeout=5)
                subprocess.run(["sudo", "ip", "link", "set", self.lan_if, "down"], timeout=5)
                subprocess.run(["sudo", "ip", "link", "set", self.lan_if, "up"], timeout=5)
                self.console.print("[green]✓ Network interfaces reset[/green]")
            except Exception as e:
                self.console.print(f"[red]✗ Interface reset failed: {e}[/red]")
            
            # Restart network services
            self.console.print("[blue]3. Restarting network services...[/blue]")
            services = ["dhcpcd", "hostapd"]
            for service in services:
                try:
                    subprocess.run(["sudo", "systemctl", "restart", service], timeout=15)
                    self.console.print(f"[green]✓ {service} restarted[/green]")
                except Exception:
                    self.console.print(f"[yellow]! {service} restart failed[/yellow]")
            
            self.console.print("\n[bold green]Network configuration reset completed[/bold green]")
            
        except Exception as e:
            self.console.print(f"[red]Network reset failed: {e}[/red]")
        
        self._pause()
    
    def _system_report(self) -> None:
        """Generate comprehensive system status report."""
        title = Text("System Status Report Generator", style="bold")
        self.console.print(title)
        self.console.print(Text("─" * len("System Status Report Generator"), style="dim"))
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"/tmp/azazel_system_report_{timestamp}.txt"
        
        self.console.print(f"[blue]Generating system report: {report_file}[/blue]")
        
        try:
            with open(report_file, 'w') as report:
                report.write(f"AZAZEL-PI SYSTEM REPORT\n")
                report.write(f"Generated: {datetime.now().isoformat()}\n")
                report.write("=" * 50 + "\n\n")
                
                # System information
                report.write("SYSTEM INFORMATION\n")
                report.write("-" * 20 + "\n")
                try:
                    result = subprocess.run(["uname", "-a"], capture_output=True, text=True, timeout=5)
                    report.write(f"Kernel: {result.stdout.strip()}\n")
                except Exception:
                    report.write("Kernel: Unable to determine\n")
                
                try:
                    result = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
                    report.write(f"Uptime: {result.stdout.strip()}\n")
                except Exception:
                    report.write("Uptime: Unable to determine\n")
                
                report.write("\n")
                
                # Current mode
                report.write("AZAZEL STATUS\n")
                report.write("-" * 15 + "\n")
                try:
                    from ..cli import _read_last_decision
                    decision_paths = [Path("/var/log/azazel/decisions.log")]
                    current = _read_last_decision(decision_paths)
                    if current:
                        report.write(f"Current Mode: {current.get('mode', 'unknown').upper()}\n")
                        report.write(f"Last Decision: {current.get('timestamp', 'unknown')}\n")
                        report.write(f"Reason: {current.get('reason', 'No reason provided')}\n")
                    else:
                        report.write("Current Mode: Unable to determine\n")
                except Exception:
                    report.write("Current Mode: Error reading decision log\n")
                
                report.write("\n")
                
                # Network status
                report.write("NETWORK STATUS\n")
                report.write("-" * 15 + "\n")
                try:
                    wlan0 = _wlan_ap_status(self.lan_if)
                    wlan1 = _wlan_link_info(self.wan_if)
                    
                    report.write(f"LAN Interface ({self.lan_if}):\n")
                    report.write(f"  AP Mode: {'Yes' if wlan0.get('is_ap') else 'No'}\n")
                    report.write(f"  SSID: {wlan0.get('ssid', 'N/A')}\n")
                    report.write(f"  Clients: {wlan0.get('stations', 'N/A')}\n")
                    
                    report.write(f"WAN Interface ({self.wan_if}):\n")
                    report.write(f"  Connected: {'Yes' if wlan1.get('connected') else 'No'}\n")
                    report.write(f"  SSID: {wlan1.get('ssid', 'N/A')}\n")
                    report.write(f"  IP: {wlan1.get('ip4', 'N/A')}\n")
                    
                except Exception as e:
                    report.write(f"Network Status: Error - {e}\n")
                
                report.write("\n")
                
                # Service status
                report.write("SERVICE STATUS\n")
                report.write("-" * 15 + "\n")
                services = ["azctl", "azctl-serve", "suricata", "opencanary", "vector"]
                for service in services:
                    try:
                        result = subprocess.run(
                            ["systemctl", "is-active", f"{service}.service"],
                            capture_output=True, text=True, timeout=5
                        )
                        status = "ACTIVE" if result.returncode == 0 else "INACTIVE"
                        report.write(f"{service}: {status}\n")
                    except Exception:
                        report.write(f"{service}: UNKNOWN\n")
                
                report.write("\n")
                
                # System resources
                report.write("SYSTEM RESOURCES\n")
                report.write("-" * 17 + "\n")
                try:
                    result = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5)
                    report.write("Memory Usage:\n")
                    report.write(result.stdout)
                except Exception:
                    report.write("Memory Usage: Unable to determine\n")
                
                try:
                    result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
                    report.write("\nDisk Usage:\n")
                    report.write(result.stdout)
                except Exception:
                    report.write("Disk Usage: Unable to determine\n")
                
                report.write("\n")
                
                # Recent logs
                report.write("RECENT SYSTEM LOGS\n")
                report.write("-" * 19 + "\n")
                try:
                    result = subprocess.run(
                        ["journalctl", "-n", "20", "--no-pager"],
                        capture_output=True, text=True, timeout=10
                    )
                    report.write(result.stdout)
                except Exception:
                    report.write("Recent logs: Unable to retrieve\n")
            
            self.console.print(f"[green]✓ System report generated: {report_file}[/green]")
            self.console.print(f"[blue]Report can be viewed with: cat {report_file}[/blue]")
            
        except Exception as e:
            self.console.print(f"[red]Failed to generate report: {e}[/red]")
        
        self._pause()
    
    def _factory_reset(self) -> None:
        """Reset system to factory defaults."""
        title = Text("Factory Reset", style="bold red")
        self.console.print(title)
        self.console.print(Text("─" * len("Factory Reset"), style="dim"))
        
        self.console.print("[red]WARNING: This will reset ALL system settings to factory defaults![/red]")
        self.console.print("[yellow]This includes:")
        self.console.print("• All Wi-Fi networks and passwords")
        self.console.print("• Custom configurations")
        self.console.print("• Log files and history")
        self.console.print("• User settings and profiles")
        self.console.print("• Decision history[/yellow]")
        self.console.print()
        
        # Multiple confirmations for factory reset
        if not Confirm.ask("[red]Are you sure you want to perform a factory reset?[/red]", default=False):
            return
        
        if not Confirm.ask("[red]This cannot be undone. Really proceed with factory reset?[/red]", default=False):
            return
        
        # Require typing "FACTORY RESET" to confirm
        confirmation = Prompt.ask("[red]Type 'FACTORY RESET' to confirm")
        if confirmation != "FACTORY RESET":
            self.console.print("[yellow]Factory reset cancelled.[/yellow]")
            self._pause()
            return
        
        self.console.print("[red]Performing factory reset...[/red]")
        
        try:
            # This would implement actual factory reset logic
            # For safety, we'll just simulate the process
            self.console.print("[blue]1. Stopping all services...[/blue]")
            self.console.print("[blue]2. Clearing configurations...[/blue]")
            self.console.print("[blue]3. Resetting to defaults...[/blue]")
            self.console.print("[blue]4. Restarting services...[/blue]")
            
            # In a real implementation, you would:
            # - Stop all Azazel services
            # - Remove configuration files
            # - Restore default configurations
            # - Clear logs and decision history
            # - Reset network settings
            # - Restart all services
            
            self.console.print("[yellow]Factory reset simulation completed.[/yellow]")
            self.console.print("[red]In production, this would reset all system settings.[/red]")
            
        except Exception as e:
            self.console.print(f"[red]Factory reset failed: {e}[/red]")
        
        self._pause()
    
    def _pause(self) -> None:
        """Pause for user input."""
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="", show_default=False)