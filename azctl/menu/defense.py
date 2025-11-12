#!/usr/bin/env python3
"""
Defense Control Module

Provides defensive mode management and threat response functionality
for the Azazel TUI menu system.
"""

import subprocess
from azazel_pi.utils.cmd_runner import run as run_cmd
from pathlib import Path
from typing import Optional, Dict, Any
import os

from rich.console import Console
from rich.layout import Layout
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.text import Text

from azctl.menu.types import MenuCategory, MenuAction
from azctl.cli import _read_last_decision, _mode_style
from azazel_pi.utils.network_utils import get_wlan_ap_status, get_wlan_link_info, get_active_profile

try:
    from azazel_pi.core.ingest.status_collector import NetworkStatusCollector
except ImportError:
    NetworkStatusCollector = None


class DefenseModule:
    """Defense control and mode management functionality."""
    
    def __init__(self, console: Console, decisions_log: Optional[str] = None, lan_if: Optional[str] = None, wan_if: Optional[str] = None):
        self.console = console
        self.decisions_log = decisions_log
        # LAN precedence: explicit arg -> AZAZEL_LAN_IF env -> default wlan0
        self.lan_if = lan_if or os.environ.get("AZAZEL_LAN_IF") or "wlan0"
        # Resolve WAN interface default from explicit arg -> env -> WANManager helper -> fallback
        try:
            from azazel_pi.utils.wan_state import get_active_wan_interface
            # Resolve WAN precedence: explicit arg -> AZAZEL_WAN_IF -> WAN manager -> fallback
            self.wan_if = (
                wan_if
                or os.environ.get("AZAZEL_WAN_IF")
                or get_active_wan_interface(default=os.environ.get("AZAZEL_WAN_IF", "wlan1"))
            )
        except Exception:
            self.wan_if = wan_if or os.environ.get("AZAZEL_WAN_IF") or "wlan1"
        
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
                MenuAction("User Override: Portal Mode ⏱️", "Override to Portal mode for 3 minutes", self._user_override_portal, requires_root=True),
                MenuAction("User Override: Shield Mode ⏱️", "Override to Shield mode for 3 minutes", self._user_override_shield, requires_root=True),
                MenuAction("User Override: Lockdown Mode ⚠️⏱️", "Override to Lockdown mode for 3 minutes", self._user_override_lockdown, dangerous=True, requires_root=True),
                MenuAction("Return to Auto Mode", "Cancel user override and return to automatic mode", self._return_to_auto, requires_root=True),
                MenuAction("View Decision History", "Show recent mode change decisions", self._view_decisions),
            ]
        )
    
    def _view_status(self) -> None:
        """Display comprehensive system status."""
        # Clear screen for better visibility
        self.console.clear()
        
        title = Text("Defense Status & System Overview", style="bold blue")
        self.console.print(title)
        self.console.print(Text("─" * 40, style="dim"))
        
        # Get status data
        decision_paths = [
            Path(self.decisions_log) if self.decisions_log else None,
            Path("/var/log/azazel/decisions.log"),
            Path("decisions.log"),
        ]
        decision_paths = [p for p in decision_paths if p is not None]
        
        # Get current machine state 
        try:
            from azctl.cli import build_machine
            machine = build_machine()
            summary = machine.summary()
            current_mode = summary.get("state", "unknown")
            is_user_mode = summary.get("user_mode") == "true"
            timeout_remaining = float(summary.get("user_timeout_remaining", "0"))
            
            if is_user_mode:
                base_mode = machine.get_base_mode()
                mode_label = f"USER_{base_mode.upper()} ({timeout_remaining:.0f}s remaining)"
                # Use base mode color for user override
                if base_mode == "portal":
                    color = "green"
                elif base_mode == "shield":
                    color = "yellow"
                elif base_mode == "lockdown":
                    color = "red"
                else:
                    color = "green"
                mode_emoji = "👤"
            else:
                from azctl.cli import _mode_style
                result = _mode_style(current_mode)
                if result and len(result) == 2:
                    mode_label, color = result
                else:
                    mode_label = current_mode.upper()
                    color = "green" if current_mode == "portal" else "yellow" if current_mode == "shield" else "red" if current_mode == "lockdown" else "blue"
                mode_emoji = {"portal": "🟢", "shield": "🟡", "lockdown": "🔴"}.get(current_mode, "⚪")
        except Exception:
            # Fallback to decision log
            last_decision = _read_last_decision(decision_paths)
            mode = last_decision.get("mode") if last_decision else "portal"
            from azctl.cli import _mode_style
            result = _mode_style(mode)
            if result and len(result) == 2:
                mode_label, color = result
            else:
                mode_label = mode.upper()
                color = "green" if mode == "portal" else "yellow" if mode == "shield" else "red" if mode == "lockdown" else "blue"
            mode_emoji = {"portal": "🟢", "shield": "🟡", "lockdown": "🔴"}.get(mode, "⚪")
        
        wlan0 = get_wlan_ap_status(self.lan_if)
        wlan1 = get_wlan_link_info(self.wan_if)
        profile = get_active_profile()
        
        try:
            status = self.status_collector.collect()
            uptime = status.get('uptime', 'Unknown')
            # Parse CPU and memory if available - fallback to our custom functions
            try:
                cpu_usage = status.get('cpu_percent', None)
                if cpu_usage is None or cpu_usage == 'N/A':
                    cpu_usage = self._get_cpu_usage()
                else:
                    cpu_usage = f"{cpu_usage}%"
                    
                memory_usage = status.get('memory_percent', None)
                if memory_usage is None or memory_usage == 'N/A':
                    memory_usage = self._get_memory_usage()
                else:
                    memory_usage = f"{memory_usage}%"
            except:
                cpu_usage = self._get_cpu_usage()
                memory_usage = self._get_memory_usage()
        except Exception:
            status = None
            uptime = 'Unknown'
            cpu_usage = self._get_cpu_usage()
            memory_usage = self._get_memory_usage()

        # Create compact info table
        info_table = Table(show_header=False, box=None, pad_edge=False)
        info_table.add_column("Label", style="bold", width=16)
        info_table.add_column("Value", style="white", width=28)
        info_table.add_column("Label2", style="bold", width=14)
        info_table.add_column("Value2", style="white")
        
        # Row 1: Defense Mode & Profile
        info_table.add_row(
            f"{mode_emoji} Defense Mode:",
            f"[{color}]{mode_label}[/{color}]",
            "📊 Profile:",
            profile or "Unknown"
        )
        
        # Row 2: Threat Scores (if available)
        if status and 'threat_score' in status:
            score_info = f"{status['threat_score']:.1f} (avg: {status.get('avg_score', 0):.1f})"
        else:
            score_info = "No data"
        
        info_table.add_row(
            "⚠️ Threat Score:",
            score_info,
            "⏱️ Uptime:",
            str(uptime)
        )
        
        # Row 3: Network Interfaces
        ap_status = "Active" if wlan0.get('is_ap') else "Inactive"
        if wlan0.get('is_ap') and wlan0.get('ssid'):
            ap_status += f" ({wlan0['ssid']})"
            
        wan_status = "Connected" if wlan1.get('connected') else "Disconnected"
        if wlan1.get('connected') and wlan1.get('ssid'):
            wan_status += f" ({wlan1['ssid']})"
            
        info_table.add_row(
            f"📡 AP ({self.lan_if}):",
            ap_status,
            f"🌐 WAN ({self.wan_if}):",
            wan_status
        )
        
        # Row 4: System Resources
        info_table.add_row(
            "💾 CPU Usage:",
            cpu_usage,
            "🧠 Memory:",
            memory_usage
        )
        
        # Add services status if available
        try:
            import subprocess
            suricata_status = run_cmd(['systemctl', 'is-active', 'suricata'], capture_output=True, text=True).stdout.strip()
            canary_status = run_cmd(['systemctl', 'is-active', 'opencanary'], capture_output=True, text=True).stdout.strip()
            
            services_info = f"Suricata: {'✅' if suricata_status == 'active' else '❌'} | Canary: {'✅' if canary_status == 'active' else '❌'}"
        except:
            services_info = "Status unknown"
            
        info_table.add_row(
            "🛡️ Services:",
            services_info,
            "",
            ""
        )
        
        # Display in a compact panel
        self.console.print(Panel(
            info_table, 
            title="[bold]System Status[/bold]",
            border_style=color,
            padding=(1, 2)
        ))
        
        # Add pause to allow user to read the information
        self.console.print("\n[dim]Press Enter to continue...[/dim]")
        input()
    
    def _user_override_portal(self) -> None:
        """User override to Portal mode."""
        self._user_override_mode("portal", "Portal mode provides minimal restrictions and monitoring.")

    def _user_override_shield(self) -> None:
        """User override to Shield mode."""
        self._user_override_mode("shield", "Shield mode provides enhanced monitoring and moderate restrictions.")

    def _user_override_lockdown(self) -> None:
        """User override to Lockdown mode."""
        if not Confirm.ask("[red]Warning: Lockdown mode will block all traffic except essential services. Continue?[/red]"):
            return
        self._user_override_mode("lockdown", "Lockdown mode provides maximum security with strict traffic filtering.")
    
    def _return_to_auto(self) -> None:
        """Return to automatic mode."""
        try:
            from azctl.daemon import AzazelDaemon
            from azazel_pi.core.state_machine import Event
            from azazel_pi.core.config import AzazelConfig
            from azazel_pi.core.scorer import ScoreEvaluator
            from azctl.cli import build_machine
            
            # Load the config
            config_path = "/home/azazel/Azazel-Pi/configs/network/azazel.yaml"
            config = AzazelConfig.from_file(config_path)
            
            # Create state machine and check current state
            machine = build_machine()
            
            # Load existing state if possible (simplified approach)
            if machine.is_user_mode():
                base_mode = machine.get_base_mode()
                timeout_event = f"timeout_{base_mode}"
                machine.dispatch(Event(name=timeout_event, severity=0))
                self.console.print(f"[green]✓ Returned to automatic {base_mode.upper()} mode[/green]")
            else:
                self.console.print("[yellow]Already in automatic mode[/yellow]")
                
        except Exception as e:
            self.console.print(f"[red]✗ Failed to return to auto mode: {e}[/red]")
            
    def _user_override_mode(self, mode: str, description: str) -> None:
        """User override mode switching function with 3-minute timer."""
        # Clear screen for better visibility
        self.console.clear()
        
        self.console.print(f"[bold blue]🔄 User Override: {mode.upper()} Mode[/bold blue]")
        self.console.print(Text("─" * 40, style="dim"))
        self.console.print(f"[blue]Starting user override: {mode.upper()} mode (3 minutes)...[/blue]")
        self.console.print(f"[dim]{description}[/dim]")
        self.console.print("[yellow]⏱️ User override will expire in 3 minutes and return to automatic mode[/yellow]")
        
        try:
            # Create a command file for the daemon to process
            import tempfile
            import yaml
            import json
            import os
            import time
            
            # Create command file with user override instruction
            command_data = {
                "command": "user_override",
                "mode": mode,
                "duration_minutes": 3.0,
                "timestamp": time.time()
            }
            
            command_file = "/tmp/azazel_user_command.yaml"
            with open(command_file, 'w') as f:
                yaml.dump(command_data, f)
            
            # Also create a direct state file for immediate menu feedback
            state_data = {
                "state": f"user_{mode}",
                "user_mode": True,
                "base_mode": mode,
                "timeout_timestamp": time.time() + (3.0 * 60),
                "updated": time.time()
            }
            
            state_file = "/tmp/azazel_state.json"
            with open(state_file, 'w') as f:
                json.dump(state_data, f)
            
            # Signal the daemon by creating events with the new user mode
            config_path = "/home/azazel/Azazel-Pi/configs/network/azazel.yaml"
            
            # Create temporary config with user override event
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            # Add user override event
            config_data['events'] = [
                {
                    "name": f"user_{mode}",
                    "severity": 0,
                    "user_override": True
                }
            ]
            
            # Write temporary config
            temp_config = f"/tmp/azazel_override_{mode}.yaml"
            with open(temp_config, 'w') as f:
                yaml.dump(config_data, f)
            
            try:
                # Process events with azctl
                result = run_cmd(
                    ["python3", "-m", "azctl", "events", "--config", temp_config],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    self.console.print(f"[green]✓ Successfully started user override: {mode.upper()} mode[/green]")
                    self.console.print("[dim]Mode will automatically return to system control in 3 minutes[/dim]")
                    
                    # Show updated status
                    self.console.print("\n[bold]Current Status:[/bold]")
                    try:
                        from azctl.cli import build_machine
                        machine = build_machine()
                        machine.start_user_mode(mode, 3.0)  # Simulate the state locally for display
                        summary = machine.summary()
                        
                        if summary.get("user_mode") == "true":
                            timeout_remaining = float(summary.get("user_timeout_remaining", "0"))
                            self.console.print(f"[yellow]👤 Mode: USER_{mode.upper()} ({timeout_remaining:.0f}s remaining)[/yellow]")
                        else:
                            self.console.print(f"[green]🟢 Mode: {mode.upper()}[/green]")
                    except Exception:
                        self.console.print(f"[green]🟢 Mode: {mode.upper()} (User Override Active)[/green]")
                else:
                    self.console.print(f"[red]✗ Failed to start user override: {result.stderr.strip()}[/red]")
                    
            finally:
                # Clean up temp files
                for temp_file in [command_file, temp_config]:
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                
        except Exception as e:
            self.console.print(f"[red]✗ Failed to start user override: {e}[/red]")
            
        # Add pause to allow user to read the result
        self.console.print("\n[dim]Press Enter to continue...[/dim]")
        input()

    def _switch_mode(self, mode: str, description: str) -> None:
        """Generic mode switching function."""
        self.console.print(f"[blue]Switching to {mode.upper()} mode...[/blue]")
        self.console.print(f"[dim]{description}[/dim]")
        
        try:
            # Simple approach: create a temporary config with the event and process it
            import tempfile
            import yaml
            import os
            
            # Load base config
            config_path = "/home/azazel/Azazel-Pi/configs/network/azazel.yaml"
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            # Add the mode switch event
            config_data['events'] = [
                {
                    "name": mode,
                    "severity": 0
                }
            ]
            
            # Write temporary config file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_file:
                yaml.dump(config_data, temp_file, default_flow_style=False)
                temp_config_path = temp_file.name
            
            try:
                # Process events with azctl
                result = run_cmd(
                    ["python3", "-m", "azctl", "events", "--config", temp_config_path],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    self.console.print(f"[green]✓ Successfully switched to {mode.upper()} mode[/green]")
                else:
                    # Try to give more specific error info
                    error_msg = result.stderr.strip() or result.stdout.strip()
                    self.console.print(f"[red]✗ Failed to switch mode: {error_msg}[/red]")
                    
            finally:
                # Clean up temp file
                if os.path.exists(temp_config_path):
                    os.unlink(temp_config_path)
                
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
    
    def _get_cpu_usage(self) -> str:
        """Get current CPU usage percentage."""
        try:
            # Read load average
            with open('/proc/loadavg', 'r') as f:
                load_avg = float(f.read().strip().split()[0])
            
            # Get CPU count
            with open('/proc/cpuinfo', 'r') as f:
                cpu_count = len([line for line in f if line.startswith('processor')])
            
            # Calculate rough CPU usage from load average
            cpu_usage = min(100.0, (load_avg / cpu_count) * 100)
            return f"{cpu_usage:.1f}%"
            
        except Exception:
            return "N/A"

    def _get_memory_usage(self) -> str:
        """Get current memory usage percentage."""
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
            
            return f"{mem_usage:.1f}%"
            
        except Exception:
            return "N/A"

    def _pause(self) -> None:
        """Pause for user input."""
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="", show_default=False)