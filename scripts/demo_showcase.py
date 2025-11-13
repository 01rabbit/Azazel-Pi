#!/usr/bin/env python3
"""Demo orchestrator for Azazel-Pi

Runs a small showcase that:
- optionally starts the demo_injector to append Suricata-like alerts to a file
- monitors the alert file and evaluates alerts via Mock-LLM (and optionally ollama)
- applies traffic-control actions through TrafficControlEngine (or simulates them)
- updates a simple TUI (rich) and writes a lightweight EPD-like output file
- sends Mattermost notifications via existing util when enabled

Designed to run in "simulate" mode by default (no privileged tc/nft calls).
Run with sudo/appropriate privileges and --no-simulate to execute real system commands.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.console import Console

try:
    from azazel_pi.core.enforcer.traffic_control import get_traffic_control_engine, TrafficControlEngine
    from azazel_pi.core.mock_llm import simulate_llm_request
    from azazel_pi.utils.mattermost import send_alert_to_mattermost, send_simple_message
except ModuleNotFoundError:
    # If the package isn't installed (running script directly from repo),
    # add repo root to sys.path so imports work when running via system python.
    import sys
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from azazel_pi.core.enforcer.traffic_control import get_traffic_control_engine, TrafficControlEngine
    from azazel_pi.core.mock_llm import simulate_llm_request
    from azazel_pi.utils.mattermost import send_alert_to_mattermost, send_simple_message

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_EVE = Path("runtime/demo_eve.json")
DEFAULT_EPD_OUT = Path("runtime/demo_epd_output.txt")


def make_fake_runner(log_file: Path = Path("/tmp/demo_cmds.log")):
    def runner(cmd, capture_output=True, text=True, timeout=None, check=False, **kw):
        try:
            s = ' '.join(map(str, cmd)) if isinstance(cmd, (list, tuple)) else str(cmd)
        except Exception:
            s = str(cmd)
        with open(log_file, 'a') as fh:
            fh.write(f"[{datetime.now().isoformat()}] {s}\n")
        # return a subprocess.CompletedProcess-like object
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    return runner


class DemoOrchestrator:
    def __init__(
        self,
        eve_path: Path,
        epd_out: Path,
        simulate: bool = True,
        notify: bool = False,
        decisions_log: Path | None = None,
        events_log: Path | None = None,
    ):
        self.eve_path = eve_path
        self.epd_out = epd_out
        self.simulate = simulate
        self.notify = notify
        self.decisions_log = decisions_log or Path("/var/log/azazel/decisions.log")
        self.events_log = events_log or Path("/var/log/azazel/events.json")

        self.console = Console()
        self._stop = threading.Event()
        self.engine: TrafficControlEngine = get_traffic_control_engine()
        if simulate:
            self.engine.set_subprocess_runner(make_fake_runner())

        # internal state
        self.mode = "portal"
        self.score = 0
        self.alerts_processed = 0
        # simulated service statuses for display
        self.services = {
            "Suricata": "ON",
            "OpenCanary": "ON" if simulate else "OFF",
        }
        # score decay parameters (per second)
        self._decay_rate = 1.0  # points per second
        self._decay_interval = 1.0

    def notify_mattermost(self, title: str, alert: Dict[str, Any]):
        if self.notify:
            send_alert_to_mattermost(title, alert)
        else:
            # fallback print
            send_simple_message(f"[Demo] {title}", level="info")

    def _append_event_log(self, alert: Dict[str, Any]):
        """Append the processed alert to the events log (if writable).

        This is a best-effort operation: if the demo isn't running as root
        or the path isn't writable we silently skip with a console message.
        """
        try:
            p = self.events_log
            # Ensure parent exists for local demo paths
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a") as fh:
                # Keep the canonical fields for downstream consumers
                fh.write(json.dumps(alert, default=str) + "\n")
        except Exception as e:
            # Not fatal — just log for operator visibility
            self.console.log(f"Could not append to events log {self.events_log}: {e}")

    def _append_decision_log(self):
        """Append a lightweight decision line to the decisions.log so the
        system TUI / EPD can pick up the current mode and average score.

        The entry mirrors what the real daemon writes: one JSON object per line.
        """
        try:
            p = self.decisions_log
            p.parent.mkdir(parents=True, exist_ok=True)
            # Normalize the written 'average' to a 0-100 display scale so that
            # other components (StateMachine, EPD/TUI) that expect 0-100 do not
            # see arbitrarily large demo accumulations. Keep raw_score for
            # debugging and diagnostics.
            raw_score = float(self.score)
            # Simple clamp: if raw_score is huge, cap to 0-100 for the display
            display_avg = max(0.0, min(100.0, raw_score))
            entry = {
                "timestamp": datetime.now().isoformat(),
                "mode": self.mode,
                "average": float(display_avg),
                "raw_demo_score": float(raw_score),
                "history": [],
                "note": "demo_orchestrator",
            }
            with p.open("a") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            self.console.log(f"Could not append to decisions log {self.decisions_log}: {e}")

    def _update_mode(self, score_delta: int):
        self.score += score_delta
        prev = self.mode
        if self.score < 30:
            self.mode = "portal"
        elif self.score < 70:
            self.mode = "shield"
        else:
            self.mode = "lockdown"

        if self.mode != prev:
            msg = f"Mode changed: {prev} -> {self.mode} (score={self.score})"
            self.console.log(msg)
            self.notify_mattermost("Mode Change", {"signature": msg, "severity": 2, "src_ip": "-", "dest_ip": "-", "proto": "-", "details": msg, "confidence": "High", "timestamp": datetime.now().isoformat()})
            # apply higher-level actions when entering shield/lockdown
            if self.mode in ("shield", "lockdown"):
                # apply combined action via engine (in simulate mode this is a noop but recorded)
                try:
                    self.engine.apply_combined_action("198.51.100.200", "shield" if self.mode == "shield" else "normal")
                except Exception as e:
                    self.console.log(f"Failed to apply combined action: {e}")
        # Always write a decisions.log entry on mode/score update so external
        # displays (TUI/EPD) that rely on the file see the authoritative
        # state. Best-effort: if write fails we log and continue.
        try:
            self._append_decision_log()
        except Exception as e:
            self.console.log(f"Could not update decisions.log: {e}")

    def _process_alert(self, alert: Dict[str, Any]):
        # Evaluate alert with Mock-LLM (and optionally ollama)
        prompt = json.dumps(alert)
        try:
            resp = simulate_llm_request(prompt)
            data = json.loads(resp)
            risk = int(data.get('risk', 3))
        except Exception:
            risk = alert.get('alert', {}).get('severity', 3)

        # Map risk to score delta
        delta = (risk - 2) * 5  # simple mapping
        self._update_mode(delta)

        # persist a lightweight EPD-like line (for visual display)
        epd_line = f"{datetime.now().isoformat()} | {alert.get('src_ip')} -> {alert.get('dest_ip')} | {alert.get('alert',{}).get('signature')} | risk={risk} | mode={self.mode}\n"
        with open(self.epd_out, 'a') as fh:
            fh.write(epd_line)

        # Append to system events log so the EPD daemon and other services
        # observing events.json see the incoming alert (best-effort).
        try:
            self._append_event_log(alert)
        except Exception:
            pass

        # mattermost notify
        self.notify_mattermost("Alert Processed", {"signature": alert.get('alert',{}).get('signature'), "severity": risk, "src_ip": alert.get('src_ip'), "dest_ip": alert.get('dest_ip'), "proto": alert.get('proto'), "details": "Processed by demo orchestrator", "confidence": "Simulated", "timestamp": datetime.now().isoformat()})

        self.alerts_processed += 1
        # debug log for visibility
        self.console.log(f"Processed alert from {alert.get('src_ip')} risk={risk} -> score={self.score} mode={self.mode}")

        # Write a decisions.log entry so the TUI/EPD display updates.
        try:
            self._append_decision_log()
        except Exception:
            pass

    def _decay_loop(self):
        # Gradually reduce score towards zero so modes can recover
        while not self._stop.is_set():
            time.sleep(self._decay_interval)
            if self.score > 0:
                old = self.score
                self.score = max(0, self.score - int(self._decay_rate * self._decay_interval))
                if int(self.score) != int(old):
                    # update mode on decay
                    self._update_mode(0)

    def tail_eve(self):
        # simple tail-follow implementation
        p = self.eve_path
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("")

        with p.open('r') as fh:
            # seek end
            fh.seek(0, 2)
            while not self._stop.is_set():
                line = fh.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                # normalize fields
                alert = {
                    'timestamp': obj.get('timestamp') or datetime.now().isoformat(),
                    'src_ip': obj.get('src_ip') or obj.get('src') or 'unknown',
                    'dest_ip': obj.get('dest_ip') or obj.get('dest') or 'unknown',
                    'proto': obj.get('proto') or 'unknown',
                    'alert': obj.get('alert', {'signature': obj.get('signature','demo'), 'severity': obj.get('severity',3)})
                }
                self._process_alert(alert)

    def run_tui(self):
        layout = Layout()
        layout.split_column(
            Layout(name="upper", ratio=3),
            Layout(name="lower", ratio=1)
        )

        def make_table():
            t = Table.grid(expand=True)
            t.add_column(justify="left")
            t.add_column(justify="right")
            t.add_row(f"Mode: [bold magenta]{self.mode}[/]", f"Score: [bold cyan]{self.score}[/]")
            t.add_row(f"Alerts processed: {self.alerts_processed}", f"Simulate: {self.simulate}")
            # services
            svc_text = ", ".join([f"{k}: {v}" for k, v in self.services.items()])
            t.add_row(f"Services", svc_text)
            return Panel(t, title="Azazel-Pi Demo Status")

        def make_lower():
            # show last lines of epd_out
            lines = []
            if self.epd_out.exists():
                try:
                    with self.epd_out.open('r') as fh:
                        lines = fh.readlines()[-5:]
                except Exception:
                    lines = []
            text = "".join(lines) or "(no events yet)"
            return Panel(text, title="EPD Preview")

        with Live(layout, refresh_per_second=2, console=self.console):
            while not self._stop.is_set():
                layout["upper"].update(make_table())
                layout["lower"].update(make_lower())
                time.sleep(0.2)

    def start(self, injector_count: int = 100, injector_interval: float = 0.2, injector_burst: bool = False, exit_after_injector: bool = False):
        # start tail thread
        t = threading.Thread(target=self.tail_eve, daemon=True)
        t.start()

        # start tui thread
        tui_thread = threading.Thread(target=self.run_tui, daemon=True)
        tui_thread.start()

        # start decay thread so the system can return to portal over time
        decay_thread = threading.Thread(target=self._decay_loop, daemon=True)
        decay_thread.start()

        # optionally start injector
        injector_proc = None
        if injector_count > 0:
            cmd = [sys.executable, str(SCRIPT_DIR / 'demo_injector.py'), '--path', str(self.eve_path), '--count', str(injector_count), '--interval', str(injector_interval)]
            if injector_burst:
                cmd.append('--burst')
            injector_proc = subprocess.Popen(cmd)

        try:
            # Wait for injector to finish (if started)
            while injector_proc and injector_proc.poll() is None:
                time.sleep(0.5)

            if exit_after_injector:
                # give a small grace period for tail processor to consume remaining lines
                grace = 2.0
                t0 = time.time()
                last_count = self.alerts_processed
                while time.time() - t0 < grace:
                    if self.alerts_processed != last_count:
                        # reset timer when new alerts are processed
                        last_count = self.alerts_processed
                        t0 = time.time()
                    time.sleep(0.2)
                # set stop to exit cleanly
                self._stop.set()
            else:
                # wait until user interrupts
                while not self._stop.is_set():
                    time.sleep(0.5)
        except KeyboardInterrupt:
            self.console.log("Stopping demo...")
        finally:
            self._stop.set()
            if injector_proc and injector_proc.poll() is None:
                try:
                    injector_proc.terminate()
                except Exception:
                    pass


def main() -> int:
    p = argparse.ArgumentParser(description="Azazel-Pi demo orchestrator")
    p.add_argument('--eve', type=Path, default=DEFAULT_EVE, help='Path to eve.json to monitor')
    p.add_argument('--epd-out', type=Path, default=DEFAULT_EPD_OUT, help='Path to write lightweight EPD preview output')
    p.add_argument('--count', type=int, default=200, help='Number of demo events to inject (0 to skip injector)')
    p.add_argument('--interval', type=float, default=0.1, help='Injector interval (seconds)')
    p.add_argument('--burst', action='store_true', help='Injector burst mode')
    p.add_argument('--no-simulate', dest='simulate', action='store_false', help='Do not simulate system commands; run real tc/nft')
    p.add_argument('--notify', action='store_true', help='Enable Mattermost notifications (requires config)')
    p.add_argument('--exit-after-injector', dest='exit_after_injector', action='store_true', help='Exit after injector finishes and remaining events are consumed')
    p.add_argument('--decisions-log', type=Path, default=None, help='Path to decisions.log to write (default system /var/log/azazel/decisions.log)')
    p.add_argument('--events-log', type=Path, default=None, help='Path to events.json to write (default system /var/log/azazel/events.json)')
    args = p.parse_args()

    orchestrator = DemoOrchestrator(
        args.eve,
        args.epd_out,
        simulate=args.simulate,
        notify=args.notify,
        decisions_log=args.decisions_log,
        events_log=args.events_log,
    )
    orchestrator.start(injector_count=args.count, injector_interval=args.interval, injector_burst=args.burst, exit_after_injector=args.exit_after_injector)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
