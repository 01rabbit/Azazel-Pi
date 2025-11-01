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

from .daemon import AzazelDaemon
import yaml
import time
from queue import Queue, Empty
import threading
import signal
from azazel_pi.core.ingest.suricata_tail import SuricataTail
from azazel_pi.core.ingest.canary_tail import CanaryTail
from azazel_pi.core import notify_config as notice
from azazel_pi.core.display.status_collector import StatusCollector


# ---------------------------------------------------------------------------
# State machine wiring (unchanged)
# ---------------------------------------------------------------------------
def build_machine() -> StateMachine:
    portal = State(name="portal", description="Nominal operations")
    shield = State(name="shield", description="Heightened monitoring")
    lockdown = State(name="lockdown", description="Full containment mode")

    machine = StateMachine(initial_state=portal)
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


def _wlan_ap_status(iface: str = "wlan0") -> dict:
    info = {"iface": iface, "is_ap": None, "stations": None, "ssid": None, "channel": None, "bssid": None, "hostapd_cli": None}
    if not _which("iw"):
        return info
    # Determine interface type
    code, out = _run(["iw", "dev", iface, "info"])
    if code == 0:
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("type "):
                info["is_ap"] = (line.split(" ", 1)[1] == "AP")
                break
    # Count associated stations
    code, out = _run(["iw", "dev", iface, "station", "dump"])
    if code == 0:
        stations = sum(1 for line in out.splitlines() if line.strip().startswith("Station "))
        info["stations"] = stations

    # hostapd details if available
    info["hostapd_cli"] = bool(_which("hostapd_cli"))
    if info["hostapd_cli"]:
        code, out = _run(["hostapd_cli", "-i", iface, "status"])
        if code == 0 and out:
            hs = _parse_hostapd_status(out)
            # If hostapd says ENABLED, we can assert AP mode
            state = hs.get("state")
            if state:
                info["is_ap"] = True if state.upper() in ("ENABLED", "AUTHENTICATING", "ASSOCIATING", "ASSOCIATED", "_CONNECTED", "RUNNING") else info.get("is_ap")
            info["ssid"] = hs.get("ssid") or info.get("ssid")
            info["channel"] = hs.get("channel") or info.get("channel")
            info["bssid"] = hs.get("bssid") or info.get("bssid")
            if hs.get("num_sta") is not None:
                info["stations"] = hs.get("num_sta")
    return info


def _wlan_link_info(iface: str = "wlan1") -> dict:
    info = {"iface": iface, "connected": None, "ssid": None, "ip4": None, "signal_dbm": None, "tx_bitrate": None, "rx_bitrate": None}
    if _which("iw"):
        code, out = _run(["iw", "dev", iface, "link"])
        if code == 0:
            if "Not connected." in out:
                info["connected"] = False
            else:
                info["connected"] = True
                for line in out.splitlines():
                    line = line.strip()
                    if line.startswith("SSID:"):
                        info["ssid"] = line.split(":", 1)[1].strip()
                    elif line.startswith("signal:"):
                        # e.g., signal: -45 dBm
                        parts = line.split(":", 1)[1].strip().split()
                        try:
                            info["signal_dbm"] = int(parts[0])
                        except Exception:
                            pass
                    elif line.startswith("tx bitrate:"):
                        info["tx_bitrate"] = line.split(":", 1)[1].strip()
                    elif line.startswith("rx bitrate:"):
                        info["rx_bitrate"] = line.split(":", 1)[1].strip()
    if _which("ip"):
        code, out = _run(["ip", "-4", "-o", "addr", "show", "dev", iface])
        if code == 0:
            # Format: "3: wlan1    inet 192.168.1.10/24 brd ..."
            for tok in out.split():
                if tok.count("/") == 1 and tok.split("/")[0].count(".") == 3:
                    info["ip4"] = tok
                    break
    return info


def _active_profile() -> Optional[str]:
    candidates = [
        Path("/etc/azazel/azazel.yaml"),
        Path("configs/network/azazel.yaml"),
        Path("configs/profiles/lte.yaml"),
        Path("configs/profiles/sat.yaml"),
        Path("configs/profiles/fiber.yaml"),
    ]
    for p in candidates:
        try:
            if not p.exists():
                continue
            with p.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                continue
            prof = data.get("profiles", {}).get("active")
            if prof:
                return str(prof)
        except Exception:
            continue
    return None


def cmd_status(decisions: Optional[str], output_json: bool, lan_if: str = "wlan0", wan_if: str = "wlan1") -> int:
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

    wlan0 = _wlan_ap_status(lan_if)
    wlan1 = _wlan_link_info(wan_if)
    profile = _active_profile()

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


def _mode_style(mode: Optional[str]) -> tuple[str, str]:
    name = (mode or "unknown").lower()
    if name == "portal":
        return ("PORTAL", "green")
    if name == "shield":
        return ("SHIELD", "yellow")
    if name == "lockdown":
        return ("LOCKDOWN", "red")
    return (name.upper(), "cyan")


def cmd_status_tui(decisions: Optional[str], lan_if: str, wan_if: str, interval: float, once: bool) -> int:
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

    collector = StatusCollector()

    def render():
        last = _read_last_decision(decision_paths)
        defensive_mode = last.get("mode") if isinstance(last, dict) else None
        mode_label, color = _mode_style(defensive_mode)

        status = collector.collect()
        wlan0 = _wlan_ap_status(lan_if)
        wlan1 = _wlan_link_info(wan_if)

        # Header
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = Text.assemble(
            (" Azazel Pi ", "bold white on blue"),
            ("  "),
            (f"{now}", "dim"),
        )

        # Mode/Score/Alerts panel
        t_left = Table.grid(padding=(0, 1))
        t_left.add_row("Mode", Text(mode_label, style=f"bold {color}"))
        t_left.add_row("Score(avg)", f"{status.security.score_average:.1f}")
        t_left.add_row("Alerts(recent)", f"{status.security.total_alerts} ({status.security.recent_alerts})")
        t_left.add_row("Services", f"Suricata: {'ON' if status.security.suricata_active else 'off'}, Canary: {'ON' if status.security.opencanary_active else 'off'}")
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
        from rich.console import Console
        Console().print(render())
        return 0

    with Live(render(), refresh_per_second=max(1, int(1/interval)) if interval < 1 else int(1/interval) if interval >= 1 else 1, screen=False) as live:
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
    p_status.add_argument("--lan-if", default="wlan0", help="LAN/AP interface name (default: wlan0)")
    p_status.add_argument("--wan-if", default="wlan1", help="WAN/client interface name (default: wlan1)")
    p_status.add_argument("--tui", action="store_true", help="Rich TUI like the E-Paper layout")
    p_status.add_argument("--watch", action="store_true", help="Continuously update status")
    p_status.add_argument("--interval", type=float, default=5.0, help="Refresh interval in seconds (default: 5.0)")

    # Serve: long-running daemon that consumes ingest streams and updates mode
    p_serve = sub.add_parser("serve", help="Run long-running daemon to consume events and auto-update mode")
    p_serve.add_argument("--decisions-log", help="Path to decisions.log (optional)")
    p_serve.add_argument("--suricata-eve", help="Path to Suricata eve.json (defaults from configs)", default=notice.SURICATA_EVE_JSON_PATH)
    p_serve.add_argument("--lan-if", default="wlan0", help="LAN/AP interface name (default: wlan0)")
    p_serve.add_argument("--wan-if", default="wlan1", help="WAN/client interface name (default: wlan1)")

    # Back-compat: events processing (original behavior)
    p_events = sub.add_parser("events", help="Process events from a YAML config")
    p_events.add_argument("--config", required=True, help="Path to configuration YAML")

    # If no subcommand was provided, fall back to legacy behavior and expect --config
    parser.add_argument("--config", help="[LEGACY] Path to configuration YAML (no subcommand)")

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "status":
        if getattr(args, "tui", False) or getattr(args, "watch", False):
            # TUI path (one-shot with --tui or continuous with --watch)
            return cmd_status_tui(
                decisions=getattr(args, "decisions_log", None),
                lan_if=getattr(args, "lan_if", "wlan0"),
                wan_if=getattr(args, "wan_if", "wlan1"),
                interval=float(getattr(args, "interval", 5.0)),
                once=not bool(getattr(args, "watch", False)),
            )
        return cmd_status(
            decisions=getattr(args, "decisions_log", None),
            output_json=bool(getattr(args, "json", False)),
            lan_if=getattr(args, "lan_if", "wlan0"),
            wan_if=getattr(args, "wan_if", "wlan1"),
        )
    if args.command == "serve":
        return cmd_serve(
            decisions=getattr(args, "decisions_log", None),
            suricata_eve=getattr(args, "suricata_eve", notice.SURICATA_EVE_JSON_PATH),
            lan_if=getattr(args, "lan_if", "wlan0"),
            wan_if=getattr(args, "wan_if", "wlan1"),
        )

    # Legacy or explicit events mode
    config_path = None
    if args.command == "events":
        config_path = args.config
    elif args.config:
        config_path = args.config

    if not config_path:
        parser.error("--config is required (either use 'events --config' or legacy '--config')")

    machine = build_machine()
    daemon = AzazelDaemon(machine=machine, scorer=ScoreEvaluator())
    daemon.process_events(load_events(config_path))
    return 0


def cmd_serve(decisions: Optional[str], suricata_eve: str, lan_if: str, wan_if: str) -> int:
    """Run a simple long-running daemon: tail Suricata and apply scoring/modes."""
    # Prepare machine and daemon
    machine = build_machine()
    decisions_path = Path(decisions) if decisions else Path(notice._get_nested({}, "paths.decisions", "/var/log/azazel/decisions.log"))
    daemon = AzazelDaemon(machine=machine, scorer=ScoreEvaluator(), decisions_log=decisions_path)

    # Ensure parent dir exists (requires permissions)
    try:
        daemon.decisions_log.parent.mkdir(parents=True, exist_ok=True)
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
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
