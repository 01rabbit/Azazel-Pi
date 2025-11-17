"""Status collector for gathering system and security state."""
from __future__ import annotations

import json
import subprocess
from azazel_pi.utils.cmd_runner import run as run_cmd
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, Optional, Iterable

from ..state_machine import StateMachine
import math
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
    # New: recent score history (most recent last) and last decision summary
    score_history: list[float] = field(default_factory=list)
    last_decision: Optional[dict] = None


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
            result = run_cmd(["hostname"], capture_output=True, text=True, timeout=1, check=False)
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
            result = run_cmd(["ip", "link", "show", active_iface], capture_output=True, text=True, timeout=1, check=False)
            status.is_up = "state UP" in (result.stdout or "")
        except Exception:
            pass

        # Get IP address
        try:
            result = run_cmd(["ip", "-4", "addr", "show", active_iface], capture_output=True, text=True, timeout=1, check=False)
            for line in (result.stdout or "").splitlines():
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
            result = run_cmd(["ip", "route", "get", "1.1.1.1"], capture_output=True, text=True, timeout=1, check=False)
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
            # Prefer EWMA score if state_machine exposes it via get_current_score()
            try:
                metrics = self.state_machine.get_current_score()
                score_average = float(metrics.get("ewma", 0.0))
                # use history from state machine if provided
                score_history = list(metrics.get("history", []))[-24:]
            except Exception:
                # Fallback to legacy window average
                if len(self.state_machine._score_window) > 0:
                    score_average = sum(self.state_machine._score_window) / len(
                        self.state_machine._score_window
                    )

        # Build a recent score history (copy, limit to last 24 entries)
        score_history = []
        try:
            if self.state_machine and hasattr(self.state_machine, "_score_window"):
                score_history = list(self.state_machine._score_window)[-24:]
        except Exception:
            score_history = []

        # If we still have no score_history (either because the in-memory
        # StateMachine hasn't collected values yet or because we're running
        # in a short-lived process), attempt to build recent history from
        # the authoritative decisions.log. We do this regardless of whether
        # a state_machine exists so the TUI/EPD can show a trend even when
        # the in-process machine hasn't been populated.
        if not score_history:
            try:
                # Probe the same candidate paths as _read_last_decision_if_any()
                candidates = [
                    Path("/var/log/azazel/decisions.log"),
                    Path("/etc/azazel/decisions.log"),
                    Path("/var/lib/azazel/decisions.log"),
                    Path("decisions.log"),
                ]
                for p in candidates:
                    if not p.exists():
                        continue
                    with p.open("r") as fh:
                        lines = [l.strip() for l in fh.readlines() if l.strip()]
                    if not lines:
                        continue
                    # Parse last up to 24 JSON lines and extract the most
                    # representative numeric field (prefer 'average', then
                    # 'score', then 'severity').
                    recent = []
                    for ln in lines[-24:]:
                        try:
                            obj = json.loads(ln)
                        except Exception:
                            continue
                        val = None
                        if isinstance(obj.get("average"), (int, float)):
                            val = obj.get("average")
                        elif isinstance(obj.get("score"), (int, float)):
                            val = obj.get("score")
                        else:
                            val = obj.get("severity")
                        if val is None:
                            continue
                        try:
                            recent.append(float(val))
                        except Exception:
                            continue
                    if recent:
                        score_history = recent
                        score_average = sum(score_history) / len(score_history)
                        # We found a candidate file and built history; stop searching
                        break
            except Exception:
                # Best-effort fallback; leave score_history empty on error
                pass

        # Count alerts from events log
        total_alerts, recent_alerts = self._count_alerts()

        # Check service status
        suricata_active = self._is_service_active("suricata")
        opencanary_active = self._is_service_active("opencanary")

        # Read last decision from typical decision log locations
        last_decision = self._read_last_decision_if_any()

        # If there's a recent last_decision available from the daemon, prefer
        # its authoritative mode/average values for display. This keeps the
        # TUI/EPD consistent with the running daemon even when the local
        # in-process StateMachine isn't receiving events.
        try:
            if isinstance(last_decision, dict):
                # Use mode if present
                last_mode = last_decision.get("mode")
                if last_mode:
                    mode = last_mode
                # Use reported average if present (decisions.log contains "average")
                last_avg = last_decision.get("average")
                if isinstance(last_avg, (int, float)):
                    score_average = float(last_avg)
                # If decisions.log contains multiple recent entries we may also
                # build a small history for sparkline purposes. Prefer any
                # 'history' field if present, else leave existing score_history.
                if isinstance(last_decision.get("history"), list):
                    score_history = list(last_decision.get("history"))[-24:]
        except Exception:
            # Best-effort: ignore errors and keep prior values
            pass

        # If the authoritative decisions.log hasn't been updated recently
        # we want the displayed score to gradually fall to reflect a
        # decaying threat level even when no new events are being written.
        # This is a display-only decay (we don't modify the decisions.log).
        try:
            # Find the most likely decisions.log file and inspect mtime
            candidates = [
                Path("/var/log/azazel/decisions.log"),
                Path("/etc/azazel/decisions.log"),
                Path("/var/lib/azazel/decisions.log"),
                Path("decisions.log"),
            ]
            found_path = None
            for p in candidates:
                if p.exists():
                    found_path = p
                    break
            if found_path is not None:
                now_ts = datetime.now(timezone.utc).timestamp()
                try:
                    age = now_ts - float(found_path.stat().st_mtime)
                except Exception:
                    age = 0.0
                # Configure decay timescale (seconds). Can be tuned via env var.
                try:
                    decay_tau = float(os.getenv("AZAZEL_DISPLAY_DECAY_TAU", "120"))
                except Exception:
                    decay_tau = 120.0
                # Apply exponential decay for display if age is non-zero and
                # we have a positive baseline score to decay from.
                if age > 0.5 and score_average > 0.0 and decay_tau > 0.0:
                    try:
                        decayed = float(score_average) * math.exp(-age / decay_tau)
                        # Ensure we don't go below zero due to numeric noise
                        decayed = max(0.0, decayed)
                        score_average = decayed
                        # Add decayed value to history so sparkline shows decline
                        if score_history:
                            score_history = (score_history[-23:] + [decayed])
                        else:
                            score_history = [decayed]
                    except Exception:
                        # If decay calculation fails, ignore and keep existing
                        pass
        except Exception:
            # Non-fatal: keep previous values
            pass

        return SecurityStatus(
            mode=mode,
            score_average=score_average,
            total_alerts=total_alerts,
            recent_alerts=recent_alerts,
            suricata_active=suricata_active,
            opencanary_active=opencanary_active,
            score_history=score_history,
            last_decision=last_decision,
        )

    def _read_last_decision_if_any(self) -> Optional[dict]:
        """Attempt to read the last JSON line from a decisions.log file.

        Probes a set of candidate paths and returns the decoded JSON of the
        last non-empty line if available.
        """
        # Prefer the system-installed decision log before any relative
        # file that may exist in the current working directory.
        candidates = [
            Path("/var/log/azazel/decisions.log"),
            Path("/etc/azazel/decisions.log"),
            Path("/var/lib/azazel/decisions.log"),
            Path("decisions.log"),
        ]
        for p in candidates:
            try:
                if not p.exists():
                    continue
                with p.open("rb") as fh:
                    fh.seek(0, os.SEEK_END)
                    size = fh.tell()
                    if size == 0:
                        continue
                    block = 4096
                    data = b""
                    while size > 0 and b"\n" not in data:
                        delta = min(block, size)
                        size -= delta
                        fh.seek(size)
                        data = fh.read(delta) + data
                    last = data.splitlines()[-1] if data else b""
                if not last:
                    continue
                try:
                    return json.loads(last.decode("utf-8", errors="ignore"))
                except Exception:
                    continue
            except Exception:
                continue
        return None

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
        if service_name == "opencanary":
            return self._is_container_running("azazel_opencanary")
        try:
            result = run_cmd(["systemctl", "is-active", f"{service_name}.service"], capture_output=True, text=True, timeout=2, check=False)
            return (result.stdout or "").strip() == "active"
        except Exception:
            return False

    def _is_container_running(self, container_name: str) -> bool:
        """Check if a Docker container is running."""
        try:
            result = run_cmd(
                ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            return result.returncode == 0 and (result.stdout or "").strip().lower() == "true"
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
