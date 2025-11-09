"""Status collector for gathering system and security state."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..state_machine import StateMachine
from ...utils.wan_state import load_wan_state, get_active_wan_interface


@dataclass
class NetworkStatus:
    """Network interface status."""

    interface: str
    ip_address: Optional[str] = None
    is_up: bool = False
    tx_bytes: int = 0
    rx_bytes: int = 0
    wan_state: Optional[str] = None
    wan_message: Optional[str] = None


@dataclass
class SecurityStatus:
    """Security monitoring status."""

    mode: str
    score_average: float
    total_alerts: int
    recent_alerts: int
    suricata_active: bool
    opencanary_active: bool


@dataclass
class SystemStatus:
    """Overall system status snapshot."""

    timestamp: datetime
    hostname: str
    network: NetworkStatus
    security: SecurityStatus
    uptime_seconds: int


class StatusCollector:
    """Collects status information from various Azazel Pi components."""

    def __init__(
        self,
        state_machine: Optional[StateMachine] = None,
        events_log: Optional[Path] = None,
        wan_state_path: Optional[Path] = None,
    ):
        """Initialize the status collector.

        Args:
            state_machine: Optional state machine instance for mode/score info
            events_log: Path to events.json for alert counting
        """
        self.state_machine = state_machine
        self.events_log = events_log or Path("/var/log/azazel/events.json")
        # Optional explicit path to the WAN state file. If None, the
        # utilities in azazel_pi.utils.wan_state will consult
        # AZAZEL_WAN_STATE_PATH or fallback locations.
        self.wan_state_path = wan_state_path

    def collect(self) -> SystemStatus:
        """Collect current system status."""
        return SystemStatus(
            timestamp=datetime.now(timezone.utc),
            hostname=self._get_hostname(),
            network=self._get_network_status(),
            security=self._get_security_status(),
            uptime_seconds=self._get_uptime(),
        )

    def _get_hostname(self) -> str:
        """Get system hostname."""
        try:
            result = subprocess.run(
                ["hostname"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            return result.stdout.strip() or "azazel-pi"
        except Exception:
            return "azazel-pi"

    def _get_network_status(self, interface: Optional[str] = None) -> NetworkStatus:
        """Get network interface status."""
        # Load WAN state, allowing an explicit path to override env/defaults.
        wan_state = load_wan_state(path=self.wan_state_path)
        # Prefer explicit wan_state.active_interface, then caller-provided interface.
        # Next preference: AZAZEL_WAN_IF env, then WANManager helper; final fallback to eth0.
        active_iface = wan_state.active_interface or interface or os.environ.get("AZAZEL_WAN_IF")
        if not active_iface:
            try:
                # Ask the WAN state helper for the current active interface.
                # If no active interface is recorded, prefer AZAZEL_WAN_IF or
                # fall back to the historical default (eth0).
                active_iface = get_active_wan_interface(default=os.environ.get("AZAZEL_WAN_IF", "eth0"))
            except Exception:
                active_iface = os.environ.get("AZAZEL_WAN_IF", "eth0")
        status = NetworkStatus(
            interface=active_iface,
            wan_state=wan_state.status,
            wan_message=wan_state.message,
        )

        # Check if interface is up
        try:
            result = subprocess.run(
                ["ip", "link", "show", active_iface],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            status.is_up = "state UP" in result.stdout
        except Exception:
            pass

        # Get IP address
        try:
            result = subprocess.run(
                ["ip", "-4", "addr", "show", active_iface],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            for line in result.stdout.splitlines():
                if "inet " in line:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        status.ip_address = parts[1].split("/")[0]
                        break
        except Exception:
            pass

        # Get traffic stats
        try:
            stats_path = Path(f"/sys/class/net/{active_iface}/statistics")
            if stats_path.exists():
                tx_path = stats_path / "tx_bytes"
                rx_path = stats_path / "rx_bytes"
                if tx_path.exists():
                    status.tx_bytes = int(tx_path.read_text().strip())
                if rx_path.exists():
                    status.rx_bytes = int(rx_path.read_text().strip())
        except Exception:
            pass

        return status

    def _get_security_status(self) -> SecurityStatus:
        """Get security monitoring status."""
        mode = "portal"
        score_average = 0.0

        # Get mode and score from state machine if available
        if self.state_machine:
            mode = self.state_machine.current_state.name
            if len(self.state_machine._score_window) > 0:
                score_average = sum(self.state_machine._score_window) / len(
                    self.state_machine._score_window
                )

        # Count alerts from events log
        total_alerts, recent_alerts = self._count_alerts()

        # Check service status
        suricata_active = self._is_service_active("suricata")
        opencanary_active = self._is_service_active("opencanary")

        return SecurityStatus(
            mode=mode,
            score_average=score_average,
            total_alerts=total_alerts,
            recent_alerts=recent_alerts,
            suricata_active=suricata_active,
            opencanary_active=opencanary_active,
        )

    def _count_alerts(self, recent_window_seconds: int = 300) -> tuple[int, int]:
        """Count total and recent alerts from events log.

        Args:
            recent_window_seconds: Time window for recent alerts (default 5 min)

        Returns:
            Tuple of (total_alerts, recent_alerts)
        """
        if not self.events_log.exists():
            return 0, 0

        total = 0
        recent = 0
        cutoff = datetime.now(timezone.utc).timestamp() - recent_window_seconds

        try:
            with open(self.events_log, "r") as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        total += 1
                        # Check if event is recent
                        if "timestamp" in event:
                            ts = datetime.fromisoformat(
                                event["timestamp"].replace("Z", "+00:00")
                            ).timestamp()
                            if ts >= cutoff:
                                recent += 1
                    except (json.JSONDecodeError, ValueError):
                        continue
        except Exception:
            pass

        return total, recent

    def _is_service_active(self, service_name: str) -> bool:
        """Check if a systemd service is active."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", f"{service_name}.service"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            return result.stdout.strip() == "active"
        except Exception:
            return False

    def _get_uptime(self) -> int:
        """Get system uptime in seconds."""
        try:
            with open("/proc/uptime", "r") as f:
                uptime_seconds = float(f.read().split()[0])
                return int(uptime_seconds)
        except Exception:
            return 0
