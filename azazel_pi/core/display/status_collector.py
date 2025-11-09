"""Status collector for gathering system and security state."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, Optional, Iterable

from ..state_machine import StateMachine
from ...utils.wan_state import (
    InterfaceSnapshot,
    WANState,
    get_active_wan_interface,
    load_wan_state,
)


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
        wan_state_path: Optional[Path] = None,  # 修正: wan_state_path を追加
    ):
        """Initialize the status collector.

        Args:
            state_machine: Optional state machine instance for mode/score info
            events_log: Path to events.json for alert counting
            wan_state_path: Optional path to WAN state JSON file
        """
        self.state_machine = state_machine
        self.events_log = events_log or Path("/var/log/azazel/events.json")
        self.wan_state_path = wan_state_path  # 修正: wan_state_path を保存

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
        env_iface = os.environ.get("AZAZEL_WAN_IF")
        active_iface = wan_state.active_interface or interface or env_iface
        if not active_iface:
            try:
                active_iface = get_active_wan_interface(default=env_iface or "wlan1")
            except Exception:
                active_iface = env_iface or "wlan1"

        # If the WAN manager did not provide an explicit active_interface
        # and the environment did not force one, prefer the kernel's actual
        # default route decision — this catches cases where the system's
        # default route is via eth0 even though no wan_state file exists.
        if (not wan_state.active_interface) and (env_iface is None):
            route_iface = self._get_default_route_interface()
            if route_iface:
                active_iface = route_iface

        if not active_iface:
            active_iface = "wlan1"

        # When multiple WAN candidates are up simultaneously (e.g. wlan1
        # and eth0), prefer the interface reporting the highest measured
        # speed so the display reflects the interface users actually use.
        # This mirrors operator expectations where a newly plugged-in
        # faster link should immediately become the "primary" on the EPD
        # even before state files are refreshed.
        active_iface = self._prefer_fastest_candidate(wan_state, active_iface)
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

    def _get_default_route_interface(self) -> Optional[str]:
        """Return the interface used for the default route (best-effort)."""
        try:
            result = subprocess.run(
                ["ip", "route", "get", "1.1.1.1"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
        except Exception:
            return None

        out = (result.stdout or "").strip()
        if not out:
            return None
        parts = out.split()
        if "dev" not in parts:
            return None
        idx = parts.index("dev")
        if idx + 1 >= len(parts):
            return None
        return parts[idx + 1] or None

    def _prefer_fastest_candidate(self, wan_state: WANState, current_iface: str) -> str:
        """Return the interface representing the fastest healthy candidate."""
        fastest = self._fastest_candidate(wan_state.candidates)
        if not fastest:
            return current_iface

        if fastest.name == current_iface:
            return current_iface

        current_snapshot = self._find_snapshot(wan_state.candidates, current_iface)
        fastest_speed = fastest.speed_mbps or 0
        current_speed = (current_snapshot.speed_mbps or 0) if current_snapshot else -1

        # If we have no data for the current interface or it is down, switch immediately.
        if (not current_snapshot) or (not current_snapshot.link_up) or (
            not current_snapshot.ip_address
        ):
            return fastest.name

        if fastest_speed > current_speed:
            return fastest.name
        return current_iface

    @staticmethod
    def _fastest_candidate(
        candidates: Iterable[InterfaceSnapshot],
    ) -> Optional[InterfaceSnapshot]:
        """Pick the fastest candidate that is link-up and has an IP."""
        fastest: Optional[InterfaceSnapshot] = None
        for snap in candidates:
            if not snap.link_up or not snap.ip_address:
                continue
            if fastest is None:
                fastest = snap
                continue
            snap_speed = snap.speed_mbps or 0
            fastest_speed = fastest.speed_mbps or 0
            if snap_speed > fastest_speed:
                fastest = snap
        return fastest

    @staticmethod
    def _find_snapshot(
        candidates: Iterable[InterfaceSnapshot], iface: Optional[str]
    ) -> Optional[InterfaceSnapshot]:
        if iface is None:
            return None
        for snap in candidates:
            if snap.name == iface:
                return snap
        return None

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
