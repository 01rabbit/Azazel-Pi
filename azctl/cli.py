"""Azazel control CLI and status inspector.

Backwards compatible with the original event-processing mode, and adds a
"status" subcommand to report current defensive mode and WLAN info.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Iterable, Optional
from datetime import datetime

from azazel_pi.core.config import AzazelConfig
from azazel_pi.core.scorer import ScoreEvaluator
from azazel_pi.core.state_machine import Event, State, StateMachine, Transition
from azazel_pi.utils.network_utils import (
    get_wlan_ap_status, get_wlan_link_info, get_active_profile,
    get_network_interfaces_stats, format_bytes
)
from collections import deque

from azctl.daemon import AzazelDaemon
import yaml
import time
from queue import Queue, Empty
import threading
import signal
from azazel_pi.core.ingest.suricata_tail import SuricataTail
from azazel_pi.core.ingest.canary_tail import CanaryTail
from azazel_pi.core import notify_config as notice
from azazel_pi.core.display.status_collector import StatusCollector
from azazel_pi.utils.wan_state import get_active_wan_interface


# ---------------------------------------------------------------------------
# State machine wiring (unchanged)
# ---------------------------------------------------------------------------
def build_machine() -> StateMachine:
    # Automatic modes (system controlled)
    portal = State(name="portal", description="Nominal operations")
    shield = State(name="shield", description="Heightened monitoring")
    lockdown = State(name="lockdown", description="Full containment mode")
    
    # User intervention modes (manually controlled with 3-minute timer)
    user_portal = State(name="user_portal", description="User controlled: Nominal operations")
    user_shield = State(name="user_shield", description="User controlled: Heightened monitoring")
    user_lockdown = State(name="user_lockdown", description="User controlled: Full containment")

    machine = StateMachine(initial_state=portal)
    # Auto-mode transitions (system threat detection)
    machine.add_transition(
        Transition(
            source=portal,
            target=shield,
            condition=lambda event: event.name == "shield",
        )
    )
    machine.add_transition(
        Transition(
            source=portal,
            target=lockdown,
            condition=lambda event: event.name == "lockdown",
        )
    )
    machine.add_transition(
        Transition(
            source=shield,
            target=portal,
            condition=lambda event: event.name == "portal",
        )
    )
    machine.add_transition(
        Transition(
            source=shield,
            target=lockdown,
            condition=lambda event: event.name == "lockdown",
        )
    )
    machine.add_transition(
        Transition(
            source=lockdown,
            target=shield,
            condition=lambda event: event.name == "shield",
        )
    )
    machine.add_transition(
        Transition(
            source=lockdown,
            target=portal,
            condition=lambda event: event.name == "portal",
        )
    )
    
    # User intervention transitions (manual override)
    # From auto modes to user modes
    machine.add_transition(
        Transition(
            source=portal,
            target=user_portal,
            condition=lambda event: event.name == "user_portal",
        )
    )
    machine.add_transition(
        Transition(
            source=portal,
            target=user_shield,
            condition=lambda event: event.name == "user_shield",
        )
    )
    machine.add_transition(
        Transition(
            source=portal,
            target=user_lockdown,
            condition=lambda event: event.name == "user_lockdown",
        )
    )
    machine.add_transition(
        Transition(
            source=shield,
            target=user_portal,
            condition=lambda event: event.name == "user_portal",
        )
    )
    machine.add_transition(
        Transition(
            source=shield,
            target=user_shield,
            condition=lambda event: event.name == "user_shield",
        )
    )
    machine.add_transition(
        Transition(
            source=shield,
            target=user_lockdown,
            condition=lambda event: event.name == "user_lockdown",
        )
    )
    machine.add_transition(
        Transition(
            source=lockdown,
            target=user_portal,
            condition=lambda event: event.name == "user_portal",
        )
    )
    machine.add_transition(
        Transition(
            source=lockdown,
            target=user_shield,
            condition=lambda event: event.name == "user_shield",
        )
    )
    machine.add_transition(
        Transition(
            source=lockdown,
            target=user_lockdown,
            condition=lambda event: event.name == "user_lockdown",
        )
    )
    
    # Between user modes
    machine.add_transition(
        Transition(
            source=user_portal,
            target=user_shield,
            condition=lambda event: event.name == "user_shield",
        )
    )
    machine.add_transition(
        Transition(
            source=user_portal,
            target=user_lockdown,
            condition=lambda event: event.name == "user_lockdown",
        )
    )
    machine.add_transition(
        Transition(
            source=user_shield,
            target=user_portal,
            condition=lambda event: event.name == "user_portal",
        )
    )
    machine.add_transition(
        Transition(
            source=user_shield,
            target=user_lockdown,
            condition=lambda event: event.name == "user_lockdown",
        )
    )
    machine.add_transition(
        Transition(
            source=user_lockdown,
            target=user_portal,
            condition=lambda event: event.name == "user_portal",
        )
    )
    machine.add_transition(
        Transition(
            source=user_lockdown,
            target=user_shield,
            condition=lambda event: event.name == "user_shield",
        )
    )
    
    # User mode timeout transitions (3-minute timer expiry)
    machine.add_transition(
        Transition(
            source=user_portal,
            target=portal,
            condition=lambda event: event.name == "timeout_portal",
        )
    )
    machine.add_transition(
        Transition(
            source=user_shield,
            target=shield,
            condition=lambda event: event.name == "timeout_shield",
        )
    )
    machine.add_transition(
        Transition(
            source=user_lockdown,
            target=lockdown,
            condition=lambda event: event.name == "timeout_lockdown",
        )
    )
    return machine


def load_events(path: str) -> Iterable[Event]:
    config = AzazelConfig.from_file(path)
    events = config.get("events", [])
    for item in events:
        yield Event(name=item.get("name", "escalate"), severity=int(item.get("severity", 0)))


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------
def _read_last_decision(decision_paths: list[Path]) -> Optional[dict]:
    for p in decision_paths:
        try:
            if not p.exists():
                continue
            with p.open("rb") as fh:
                try:
                    # Read last line efficiently
                    fh.seek(0, os.SEEK_END)
                    size = fh.tell()
                    block = 4096
                    data = b""
                    while size > 0 and b"\n" not in data:
                        delta = min(block, size)
                        size -= delta
                        fh.seek(size)
                        data = fh.read(delta) + data
                    last = data.splitlines()[-1] if data else b""
                except Exception:
                    last = fh.readlines()[-1]
            if not last:
                continue
            return json.loads(last.decode("utf-8", errors="ignore"))
        except Exception:
            continue
    return None


def _which(cmd: str) -> Optional[str]:
    for path in os.environ.get("PATH", "").split(":"):
        candidate = os.path.join(path, cmd)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return 0, out.decode("utf-8", errors="ignore")
    except subprocess.CalledProcessError as exc:
        return exc.returncode, exc.output.decode("utf-8", errors="ignore")
    except FileNotFoundError:
        return 127, ""


def _parse_hostapd_status(text: str) -> dict:
    data = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    # Normalize selected keys
    out = {
        "state": data.get("state"),
        "ssid": data.get("ssid"),
        "bssid": data.get("bssid"),
        "channel": int(data.get("channel", "0") or 0) or None,
        "num_sta": int(data.get("num_sta", "0") or 0) if data.get("num_sta") else None,
    }
    return out


# レガシー関数は network_utils.py に移行し、統合関数に完全移行しました


def cmd_status(decisions: Optional[str], output_json: bool, lan_if: str, wan_if: str) -> int:
    # Likely locations to probe for decisions.log
    candidates = [
        Path(decisions) if decisions else None,
        Path("decisions.log"),
        Path("/var/log/azazel/decisions.log"),
        Path("/etc/azazel/decisions.log"),
        Path("/var/lib/azazel/decisions.log"),
    ]
    decision_paths = [p for p in candidates if p is not None]
    last = _read_last_decision(decision_paths)
    defensive_mode = last.get("mode") if isinstance(last, dict) else None

    wlan0 = get_wlan_ap_status(lan_if)
    wlan1 = get_wlan_link_info(wan_if)
    profile = get_active_profile()

    result = {
        "defensive_mode": defensive_mode,
        "profile_active": profile,
        "wlan0": wlan0,
        "wlan1": wlan1,
    }

    if output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Azazel status")
        print("- Defensive mode:", defensive_mode or "unknown (no decisions.log)")
        print("- Active profile:", profile or "unknown")
        print(f"- {lan_if} (AP):", "yes" if wlan0.get("is_ap") else ("no" if wlan0.get("is_ap") is False else "unknown"))
        stations = wlan0.get("stations")
        print("  joined stations:", stations if stations is not None else "unknown")
        if wlan0.get("ssid"):
            print("  SSID:", wlan0.get("ssid"))
        if wlan0.get("channel"):
            print("  channel:", wlan0.get("channel"))
        if wlan0.get("bssid"):
            print("  BSSID:", wlan0.get("bssid"))
        if wlan0.get("is_ap") and wlan0.get("hostapd_cli") is False:
            print("  note: hostapd_cli not found. For richer AP status, install: sudo apt-get install -y hostapd")
        print(f"- {wan_if} connected:", "yes" if wlan1.get("connected") else ("no" if wlan1.get("connected") is False else "unknown"))
        print("  SSID:", wlan1.get("ssid") or "-")
        print("  IPv4:", wlan1.get("ip4") or "-")
        if wlan1.get("signal_dbm") is not None:
            print("  signal:", f"{wlan1['signal_dbm']} dBm")
        if wlan1.get("tx_bitrate"):
            print("  tx bitrate:", wlan1.get("tx_bitrate"))
        if wlan1.get("rx_bitrate"):
            print("  rx bitrate:", wlan1.get("rx_bitrate"))

    return 0


def _human_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(max(n, 0))
    for u in units:
        if x < 1024.0 or u == units[-1]:
            return f"{x:.1f} {u}" if u != "B" else f"{int(x)} {u}"
        x /= 1024.0


def _mode_style(mode: str) -> tuple[str, str]:
    """Get display label and color for a mode."""
    if not mode:
        return ("UNKNOWN", "blue")
    
    mode_colors = {
        "portal": "green",
        "shield": "yellow", 
        "lockdown": "red",
        "USER_PORTAL": "green",
        "USER_SHIELD": "yellow",
        "USER_LOCKDOWN": "red"
    }
    
    color = mode_colors.get(mode.upper(), "blue")
    label = mode.upper()
    
    return (label, color)


def cmd_status_tui(decisions: Optional[str], lan_if: str, wan_if: str, interval: float, once: bool) -> int:
    def _clear_terminal() -> None:
        """Clear terminal before drawing the TUI.

        Prefer Rich Console.clear() if available; fall back to ANSI.
        """
        try:
            from rich.console import Console  # type: ignore
            Console().clear()
        except Exception:
            # ANSI: clear screen and move cursor to home
            print("\033[2J\033[H", end="", flush=True)

    # Soft dependency to keep CLI usable without rich
    try:
        from rich.live import Live
        from rich.panel import Panel
        from rich.table import Table
        from rich.columns import Columns
        from rich.align import Align
        from rich.text import Text
        from rich import box
    except ImportError:
        print("'rich' is not installed. Install it with: pip install rich")
        return 1

    # Decisions and WLAN info (reuse existing helpers)
    decisions_paths = [
        Path(decisions) if decisions else None,
        Path("/var/log/azazel/decisions.log"),
        Path("decisions.log"),
    ]
    decision_paths = [p for p in decisions_paths if p is not None]

    # Try to build a local StateMachine (and apply scoring tuning from
    # /etc/azazel/azazel.yaml) so the TUI can display EWMA-based score when
    # possible. Fall back to no state_machine when anything fails.
    try:
        state_machine = None
        system_cfg = Path(os.getenv('AZAZEL_CONFIG_PATH', '/etc/azazel/azazel.yaml'))
        if system_cfg.exists():
            try:
                from azctl.cli import build_machine

                state_machine = build_machine()
                try:
                    cfg = AzazelConfig.from_file(str(system_cfg))
                    scoring = cfg.get('scoring', {}) or {}
                    if 'ewma_tau' in scoring:
                        try:
                            state_machine.ewma_tau = float(scoring.get('ewma_tau'))
                        except Exception:
                            pass
                    if 'window_size' in scoring:
                        try:
                            state_machine.window_size = int(scoring.get('window_size'))
                            state_machine._score_window = deque(maxlen=max(state_machine.window_size, 1))
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception:
                # If build_machine import or construction failed, continue without a state machine
                pass
        else:
            state_machine = None
        collector = StatusCollector(state_machine=state_machine)
    except Exception:
        collector = StatusCollector()

    def render():
        status = collector.collect()
        defensive_mode = getattr(status.security, "mode", None)
        mode_label, color = _mode_style(defensive_mode)

        wlan0 = get_wlan_ap_status(lan_if)
        wlan1 = get_wlan_link_info(wan_if)

        # Header
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = Text.assemble(
            (" AZ-01X Azazel Pi ", "bold white on blue"),
            ("  "),
            (f"{now}", "dim"),
        )

        # Mode/Score/Alerts panel
        t_left = Table.grid(padding=(0, 1))
        t_left.add_row("Mode", Text(mode_label, style=f"bold {color}"))
        t_left.add_row("Score(avg)", f"{status.security.score_average:.1f}")
        # Sparkline from recent scores (if available)
        def make_sparkline(vals: list[float]) -> str:
            if not vals:
                return ""
            blocks = ["▁","▂","▃","▄","▅","▆","▇","█"]
            mn = min(vals)
            mx = max(vals)
            # If all values equal, map their absolute magnitude to 0-100
            # scale so that a constant high score (e.g. 100.0) displays as
            # the highest block rather than always the lowest one.
            if mx - mn < 1e-6:
                try:
                    v = float(vals[-1])
                    idx = int(max(0, min(1.0, v / 100.0)) * (len(blocks) - 1))
                    return blocks[idx] * len(vals)
                except Exception:
                    return blocks[0] * len(vals)
            out = []
            for v in vals:
                idx = int((v - mn) / (mx - mn) * (len(blocks) - 1))
                out.append(blocks[idx])
            return "".join(out)

        spark = make_sparkline(status.security.score_history[-12:]) if getattr(status.security, "score_history", None) else ""
        if spark:
            t_left.add_row("Trend", spark)
        t_left.add_row("Alerts(recent)", f"{status.security.total_alerts} ({status.security.recent_alerts})")
        # Last decision summary
        if getattr(status.security, "last_decision", None):
            ld = status.security.last_decision
            # Prefer short fields if present
            reason = ld.get("reason") or ld.get("source") or ld.get("signature") or ld.get("note") or None
            score = ld.get("score") or ld.get("severity") or None
            summary = f"{reason}" if reason else "(decision)"
            if score is not None:
                summary += f" (+{score})"
            t_left.add_row("Last", summary)

        # Services row (ON/OFF)
        t_left.add_row(
            "Services",
            f"Suricata: {'ON' if status.security.suricata_active else 'OFF'}, OpenCanary: {'ON' if status.security.opencanary_active else 'OFF'}",
        )

        left_panel = Panel(t_left, title="Security", border_style=color)

        # Network panel
        t_net = Table.grid(padding=(0, 1))
        t_net.add_row("Iface", status.network.interface)
        t_net.add_row("IP", status.network.ip_address or "-")
        t_net.add_row("Uptime", f"{status.uptime_seconds//3600}h {(status.uptime_seconds//60)%60}m")
        t_net.add_row("Traffic", f"TX { _human_bytes(status.network.tx_bytes) }  RX { _human_bytes(status.network.rx_bytes) }")
        # WLAN quick view
        ap = "AP" if wlan0.get('is_ap') else ("STA" if wlan0.get('is_ap') is False else "?")
        t_net.add_row("LAN", f"{lan_if} ({ap}) SSID={wlan0.get('ssid') or '-'} Ch={wlan0.get('channel') or '-'} Sta={wlan0.get('stations') if wlan0.get('stations') is not None else '-'}")
        conn = "yes" if wlan1.get("connected") else ("no" if wlan1.get("connected") is False else "?")
        t_net.add_row("WAN", f"{wan_if} conn={conn} SSID={wlan1.get('ssid') or '-'} IP={wlan1.get('ip4') or '-'} SNR={wlan1.get('signal_dbm') or '-'}dBm")
        right_panel = Panel(t_net, title="Network", border_style="cyan")

        body = Columns([left_panel, right_panel])
        return Align.center(Panel.fit(body, title=header))

    if once:
        _clear_terminal()
        from rich.console import Console
        Console().print(render())
        return 0

    _clear_terminal()
    # Compute refresh rate safely: use fractional refresh_per_second (1/interval)
    # Live expects a positive number; avoid int-casting which can become 0 for interval>=1.
    refresh_per_second = 1.0 / interval if interval > 0 else 1.0
    with Live(render(), refresh_per_second=refresh_per_second, screen=False) as live:
        try:
            while True:
                live.update(render())
                time.sleep(interval)
        except KeyboardInterrupt:
            return 0
    return 0


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Azazel control CLI")
    sub = parser.add_subparsers(dest="command")

    # New: status command
    p_status = sub.add_parser("status", help="Show defensive mode and WLAN info")
    p_status.add_argument("--decisions-log", help="Path to decisions.log (optional)")
    p_status.add_argument("--json", action="store_true", help="Output JSON")
    p_status.add_argument("--lan-if", default=os.environ.get("AZAZEL_LAN_IF", "wlan0"), help="LAN/AP interface name (default: wlan0 or AZAZEL_LAN_IF)")
    p_status.add_argument("--wan-if", default=None, help="WAN/client interface name (default: dynamically determined by WAN manager)")
    p_status.add_argument("--tui", action="store_true", help="Rich TUI like the E-Paper layout")
    p_status.add_argument("--watch", action="store_true", help="Continuously update status")
    p_status.add_argument("--interval", type=float, default=5.0, help="Refresh interval in seconds (default: 5.0)")

    # Menu: interactive TUI menu system
    p_menu = sub.add_parser("menu", help="Launch interactive TUI menu for Azazel control operations")
    p_menu.add_argument("--decisions-log", help="Path to decisions.log (optional)")
    p_menu.add_argument("--lan-if", default=os.environ.get("AZAZEL_LAN_IF", "wlan0"), help="LAN/AP interface name (default: wlan0 or AZAZEL_LAN_IF)")
    p_menu.add_argument("--wan-if", default=None, help="WAN/client interface name (default: dynamically determined by WAN manager)")

    # Serve: long-running daemon that consumes ingest streams and updates mode
    p_serve = sub.add_parser("serve", help="Run long-running daemon to consume events and auto-update mode")
    p_serve.add_argument("--config", help="Path to Azazel configuration YAML for system initialization")
    p_serve.add_argument("--decisions-log", help="Path to decisions.log (optional)")
    p_serve.add_argument("--suricata-eve", help="Path to Suricata eve.json (defaults from configs)", default=notice.SURICATA_EVE_JSON_PATH)
    p_serve.add_argument("--lan-if", default=os.environ.get("AZAZEL_LAN_IF", "wlan0"), help="LAN/AP interface name (default: wlan0 or AZAZEL_LAN_IF)")
    p_serve.add_argument("--wan-if", default=None, help="WAN/client interface name (default: dynamically determined by WAN manager)")

    # WAN Manager: dynamic interface orchestrator
    p_wan = sub.add_parser("wan-manager", help="Monitor and select WAN interfaces automatically")
    p_wan.add_argument("--config", help="Path to azazel.yaml (default: /etc/azazel/azazel.yaml)")
    p_wan.add_argument("--candidate", action="append", dest="candidates", help="Override WAN candidates (repeatable)")
    p_wan.add_argument("--interval", type=float, default=20.0, help="Polling interval in seconds (default: 20)")
    p_wan.add_argument("--lan-cidr", default="172.16.0.0/24", help="Internal LAN CIDR for NAT (default: 172.16.0.0/24)")
    p_wan.add_argument("--state-file", help="Override WAN state file path")
    p_wan.add_argument("--once", action="store_true", help="Run a single evaluation then exit")

    # Back-compat: events processing (original behavior)
    p_events = sub.add_parser("events", help="Process events from a YAML config")
    p_events.add_argument("--config", required=True, help="Path to configuration YAML")

    # If no subcommand was provided, fall back to legacy behavior and expect --config
    parser.add_argument("--config", help="[LEGACY] Path to configuration YAML (no subcommand)")

    args = parser.parse_args(list(argv) if argv is not None else None)

    def safe_path(path_str: Optional[str], fallback: Optional[str] = None) -> Optional[Path]:
        """Return a Path for path_str if provided, otherwise a Path for fallback or None.

        This avoids calling Path(None) which raises TypeError when argparse sets
        the attribute to None even if the option wasn't provided.
        """
        if path_str:
            return Path(path_str)
        if fallback:
            return Path(fallback)
        return None

    if args.command == "status":
        # Resolve WAN interface dynamically if not provided on CLI
        wan_if = getattr(args, "wan_if", None) or get_active_wan_interface()
        if getattr(args, "tui", False) or getattr(args, "watch", False):
            # TUI path (one-shot with --tui or continuous with --watch)
            return cmd_status_tui(
                decisions=getattr(args, "decisions_log", None),
                lan_if=getattr(args, "lan_if", "wlan0"),
                wan_if=wan_if,
                interval=float(getattr(args, "interval", 5.0)),
                once=not bool(getattr(args, "watch", False)),
            )
        return cmd_status(
            decisions=getattr(args, "decisions_log", None),
            output_json=bool(getattr(args, "json", False)),
            lan_if=getattr(args, "lan_if", "wlan0"),
            wan_if=wan_if,
        )
    if args.command == "menu":
        wan_if = getattr(args, "wan_if", None) or get_active_wan_interface()
        return cmd_menu(
            decisions=getattr(args, "decisions_log", None),
            lan_if=getattr(args, "lan_if", "wlan0"),
            wan_if=wan_if,
        )
    if args.command == "serve":
        wan_if = getattr(args, "wan_if", None) or get_active_wan_interface()
        return cmd_serve(
            config=getattr(args, "config", None),
            decisions=getattr(args, "decisions_log", None),
            suricata_eve=getattr(args, "suricata_eve", notice.SURICATA_EVE_JSON_PATH),
            lan_if=getattr(args, "lan_if", "wlan0"),
            wan_if=wan_if,
        )
    if args.command == "wan-manager":
        from azazel_pi.core.network.wan_manager import WANManager

        cfg_path = safe_path(getattr(args, "config", None), "/etc/azazel/azazel.yaml")
        state_path = safe_path(getattr(args, "state_file", None), None)

        manager = WANManager(
            config_path=cfg_path,
            candidates=getattr(args, "candidates", None),
            poll_interval=float(getattr(args, "interval", 20.0)),
            lan_cidr=getattr(args, "lan_cidr", "172.16.0.0/24"),
            state_path=state_path,
        )
        return manager.run(once=bool(getattr(args, "once", False)))

    # Legacy or explicit events mode
    config_path = None
    if args.command == "events":
        config_path = args.config
    elif args.config:
        config_path = args.config

    if not config_path:
        parser.error("--config is required (either use 'events --config' or legacy '--config')")

    machine = build_machine()
    # Allow config to suggest faster scoring parameters for demo/testing
    try:
        if config_obj:
            scoring_cfg = config_obj.get("scoring", {}) or {}
            if "ewma_tau" in scoring_cfg:
                try:
                    machine.ewma_tau = float(scoring_cfg.get("ewma_tau"))
                except Exception:
                    pass
            if "window_size" in scoring_cfg:
                try:
                    machine.window_size = int(scoring_cfg.get("window_size"))
                    # resize internal deque to match new window size
                    machine._score_window = deque(maxlen=max(machine.window_size, 1))
                except Exception:
                    pass
    except Exception:
        # Non-fatal: if config parsing fails here, continue with defaults
        pass
    daemon = AzazelDaemon(machine=machine, scorer=ScoreEvaluator())
    daemon.process_events(load_events(config_path))
    return 0


def cmd_menu(decisions: Optional[str], lan_if: str, wan_if: str) -> int:
    """Launch the interactive TUI menu system."""
    try:
        from azctl.menu import AzazelTUIMenu
        menu = AzazelTUIMenu(
            decisions_log=decisions,
            lan_if=lan_if, 
            wan_if=wan_if
        )
        menu.run()
        return 0
    except ImportError as e:
        print(f"Error: TUI menu requires additional dependencies: {e}")
        print("Install with: pip install rich")
        return 1
    except Exception as e:
        print(f"Error launching menu: {e}")
        return 1


def cmd_serve(config: Optional[str], decisions: Optional[str], suricata_eve: str, lan_if: str, wan_if: str) -> int:
    """Run a simple long-running daemon: tail Suricata and apply scoring/modes."""
    
    # Initialize configuration if provided
    if config:
        try:
            # Load and validate configuration file
            config_obj = AzazelConfig.from_file(config)
            print(f"[INFO] Loaded configuration from {config}")
            print(f"[INFO] Node: {config_obj.get('node', 'unknown')}")
            print(f"[INFO] Active profile: {config_obj.get('profiles', {}).get('active', 'unknown')}")
            thresholds = config_obj.get('thresholds', {})
            print(f"[INFO] Thresholds: Shield={thresholds.get('t1_shield', 50)}, Lockdown={thresholds.get('t2_lockdown', 80)}")
        except Exception as e:
            print(f"[WARN] Failed to load config {config}: {e}")
            print("[INFO] Continuing with default configuration...")
    
    # Prepare machine and daemon
    machine = build_machine()
    # If a config path was provided, try to apply any scoring tuning (ewma_tau/window_size)
    try:
        if config:
            try:
                config_obj = AzazelConfig.from_file(config)
                scoring_cfg = config_obj.get('scoring', {}) or {}
                if 'ewma_tau' in scoring_cfg:
                    try:
                        machine.ewma_tau = float(scoring_cfg.get('ewma_tau'))
                    except Exception:
                        pass
                if 'window_size' in scoring_cfg:
                    try:
                        machine.window_size = int(scoring_cfg.get('window_size'))
                        machine._score_window = deque(maxlen=max(machine.window_size, 1))
                    except Exception:
                        pass
            except Exception:
                # if config can't be read here, continue with defaults
                pass
    except Exception:
        pass
    decisions_path = Path(decisions) if decisions else Path(notice._get_nested({}, "paths.decisions", "/var/log/azazel/decisions.log"))
    daemon = AzazelDaemon(machine=machine, scorer=ScoreEvaluator(), decisions_log=decisions_path)

    # Ensure parent dir exists (requires permissions)
    try:
        daemon.decisions_log.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    # Start background decay writer if available on the daemon. Use the
    # AZAZEL_DISPLAY_DECAY_TAU environment variable (seconds) to control
    # the timescale. Also allow configuring the check interval.
    try:
        decay_tau = float(os.getenv("AZAZEL_DISPLAY_DECAY_TAU", "120"))
    except Exception:
        decay_tau = 120.0
    try:
        check_interval = float(os.getenv("AZAZEL_DISPLAY_DECAY_CHECK_INTERVAL", "5"))
    except Exception:
        check_interval = 5.0
    try:
        # start_decay_writer is best-effort (may not exist on older daemons)
        daemon.start_decay_writer(decay_tau=decay_tau, check_interval=check_interval)
    except Exception:
        pass

    try:
        trend_interval = float(os.getenv("AZAZEL_TREND_SAMPLE_INTERVAL", "10"))
    except Exception:
        trend_interval = 10.0
    try:
        daemon.start_trend_sampler(interval=trend_interval)
    except Exception:
        pass

    # Write an initial entry describing current (default) mode so status shows something
    try:
        daemon.process_event(Event(name="startup", severity=0))
    except Exception:
        # best-effort; don't fail serve if initial write fails
        pass

    # Event queue
    q: "Queue[Event]" = Queue()
    stop = threading.Event()

    def suricata_reader(path: str):
        tail = SuricataTail(Path(path))
        for ev in tail.stream():
            if stop.is_set():
                break
            q.put(ev)

    def consumer():
        while not stop.is_set():
            try:
                ev = q.get(timeout=1)
            except Empty:
                continue
            try:
                daemon.process_event(ev)
            finally:
                q.task_done()

    def sigint_handler(sig, frame):
        stop.set()

    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigint_handler)

    t_reader = threading.Thread(target=suricata_reader, args=(suricata_eve,), daemon=True)
    t_consumer = threading.Thread(target=consumer, daemon=True)

    t_reader.start()
    t_consumer.start()

    try:
        while not stop.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()

    t_reader.join(timeout=2)
    t_consumer.join(timeout=2)
    # Stop decay writer thread cleanly if available
    try:
        daemon.stop_decay_writer()
    except Exception:
        pass
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
