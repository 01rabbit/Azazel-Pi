"""Textual UI ported from Azazel-Zero unified monitor."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Static

SnapshotLoader = Callable[[], Any]
ActionSender = Callable[[str], None]


class AzazelTextualApp(App):
    TITLE = "Azazel Unified TUI"
    SUB_TITLE = "Azazel-Zero port"

    CSS = """
    Screen { layout: vertical; background: #080a0f; color: #eeeeee; }
    Header { background: #0f131a; color: #00d4ff; text-style: bold; }
    Footer { background: #0f131a; color: #aaaaaa; height: 1; }

    #status-line { height: 1; color: #05080e; background: #00d4ff; text-style: bold; content-align: left middle; padding: 0 1; }
    #status-line.state-safe { background: #2ecc71; color: #05080e; }
    #status-line.state-limited { background: #f39c12; color: #05080e; }
    #status-line.state-contained { background: #e74c3c; color: #ffffff; }
    #status-line.state-deception { background: #e74c3c; color: #ffffff; }

    #summary { height: 8; border: round #00d4ff; background: #0f131a; padding: 0 1; }
    #summary.state-safe { border: round #2ecc71; }
    #summary.state-limited { border: round #f39c12; }
    #summary.state-contained { border: round #e74c3c; }
    #summary.state-deception { border: round #e74c3c; }

    #middle { height: 12; }
    #connection { width: 1fr; border: round #00d4ff; background: #0f131a; padding: 0 1; }
    #control { width: 1fr; border: round #00d4ff; background: #0f131a; padding: 0 1; }
    #evidence { height: 1fr; border: round #f39c12; background: #0f131a; padding: 0 1; }
    #flow { height: 1; background: #0f131a; color: #aaaaaa; content-align: left middle; padding: 0 1; }
    #details { height: 8; border: round #00d4ff; background: #0f131a; padding: 0 1; display: none; }
    #menu { height: 1fr; border: round #00d4ff; background: #0f131a; padding: 0 1; display: none; }
    """

    _STATE_CLASSES = ("state-safe", "state-limited", "state-contained", "state-deception")

    BINDINGS = [
        Binding("u", "refresh", "Refresh"),
        Binding("a", "stage_open", "Stage-Open"),
        Binding("r", "reprobe", "Re-Probe"),
        Binding("c", "contain", "Contain"),
        Binding("l", "details", "Details"),
        Binding("m", "toggle_menu", "Menu"),
        Binding("up", "menu_up", "Menu Up", show=False),
        Binding("down", "menu_down", "Menu Down", show=False),
        Binding("j", "menu_down", "Menu Down", show=False),
        Binding("k", "menu_up", "Menu Up", show=False),
        Binding("enter", "menu_select", "Select", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        load_snapshot_fn: SnapshotLoader,
        send_command_fn: ActionSender,
        unicode_mode: bool,
        start_menu: bool = False,
    ) -> None:
        super().__init__()
        self._load_snapshot_fn = load_snapshot_fn
        self._send_command_fn = send_command_fn
        self._unicode_mode = unicode_mode

        self._snapshot: Any = None
        self._is_loading = False
        self._details_open = False
        self._menu_open = start_menu
        self._menu_idx = 0
        self._menu_items = self._build_menu_items()
        self._status_message = "Ready"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Status: booting...", id="status-line", markup=False)
        yield Static("Loading snapshot...", id="summary", markup=False)
        with Horizontal(id="middle"):
            yield Static("Loading connection...", id="connection", markup=False)
            yield Static("Loading control...", id="control", markup=False)
        yield Static("Loading evidence...", id="evidence", markup=False)
        yield Static("Flow: PROBE -> DEGRADED -> NORMAL -> SAFE", id="flow", markup=False)
        yield Static("Control menu loading...", id="menu", markup=False)
        yield Static("Details hidden. Press [L] to toggle.", id="details", markup=False)
        yield Footer()

    async def on_mount(self) -> None:
        self.set_interval(1.0, self._tick_age_only)
        self._apply_menu_visibility()
        await self._refresh_snapshot(initial=True)

    def _build_menu_items(self) -> list[dict[str, object]]:
        return [
            {"label": "Refresh Snapshot", "kind": "refresh"},
            {"label": "Stage-Open (portal)", "kind": "send_action", "action": "stage_open"},
            {"label": "Re-Probe (shield)", "kind": "send_action", "action": "reprobe"},
            {"label": "Contain (lockdown)", "kind": "send_action", "action": "contain"},
            {"label": "Toggle Details", "kind": "toggle_details"},
            {"label": "Close Menu", "kind": "close_menu"},
        ]

    def _menu_text(self) -> str:
        lines = ["Control Menu [Enter=Run, M=Close]", ""]
        for i, item in enumerate(self._menu_items):
            marker = ">" if i == self._menu_idx else " "
            lines.append(f"{marker} {item['label']}")
        return "\n".join(lines)

    def _apply_menu_visibility(self) -> None:
        summary = self.query_one("#summary", Static)
        middle = self.query_one("#middle", Horizontal)
        flow = self.query_one("#flow", Static)
        menu = self.query_one("#menu", Static)
        evidence = self.query_one("#evidence", Static)
        if self._menu_open:
            summary.styles.height = 6
            middle.styles.height = 8
            flow.styles.display = "none"
            evidence.styles.display = "none"
            menu.styles.display = "block"
        else:
            summary.styles.height = 8
            middle.styles.height = 12
            flow.styles.display = "block"
            evidence.styles.display = "block"
            menu.styles.display = "none"
        if self._menu_open:
            menu.update(Text(self._menu_text()))

    def _tick_age_only(self) -> None:
        if self._snapshot is not None:
            self._render_status_line()

    def _safe_get(self, obj: Any, name: str, default: Any) -> Any:
        try:
            return getattr(obj, name, default)
        except Exception:
            return default

    def _live_age(self) -> str:
        ts = self._safe_get(self._snapshot, "snapshot_epoch", 0.0) or 0.0
        if not ts:
            return "00:00:00"
        delta = max(0, int(time.time() - float(ts)))
        return time.strftime("%H:%M:%S", time.gmtime(delta))

    def _state_css_class(self, state: str) -> str:
        name = str(state).upper()
        if name == "SAFE":
            return "state-safe"
        if name == "LIMITED":
            return "state-limited"
        if name in ("CONTAINED", "LOCKDOWN"):
            return "state-contained"
        if name == "DECEPTION":
            return "state-deception"
        return ""

    def _apply_state_class(self, widget: Static, state: str) -> None:
        for css_class in self._STATE_CLASSES:
            widget.remove_class(css_class)
        new_cls = self._state_css_class(state)
        if new_cls:
            widget.add_class(new_cls)

    def _state_icon(self, state: str) -> str:
        if not self._unicode_mode:
            return {"SAFE": "OK", "LIMITED": "!", "CONTAINED": "X", "DECEPTION": "D"}.get(str(state).upper(), "~")
        return {
            "SAFE": "✅",
            "LIMITED": "⚠️",
            "CONTAINED": "⛔",
            "DECEPTION": "👁",
        }.get(str(state).upper(), "⟳")

    def _threat_bar(self, level: int) -> str:
        level = max(0, min(int(level), 5))
        if self._unicode_mode:
            return "".join("🔴" if i < level else "⚪" for i in range(5))
        return "".join("X" if i < level else "." for i in range(5))

    def _render_status_line(self) -> None:
        if self._snapshot is None:
            self.query_one("#status-line", Static).update(Text(f"Status: {self._status_message}"))
            return
        status_widget = self.query_one("#status-line", Static)
        state = self._safe_get(self._snapshot, "user_state", "CHECKING")
        self._apply_state_class(status_widget, state)
        line = (
            f"State={state}  SSID={self._safe_get(self._snapshot, 'ssid', '-')}  "
            f"Risk={self._safe_get(self._snapshot, 'risk_score', 0)}/100  Age={self._live_age()}  "
            f"View={self._safe_get(self._snapshot, 'source', 'SNAPSHOT')}  Status={self._status_message}"
        )
        status_widget.update(Text(line))

    def _render_panels(self) -> None:
        if self._snapshot is None:
            return

        snap = self._snapshot
        connection = self._safe_get(snap, "connection", {}) or {}
        monitoring = self._safe_get(snap, "monitoring", {}) or {}
        degrade = self._safe_get(snap, "degrade", {}) or {}
        probe = self._safe_get(snap, "probe", {}) or {}
        dns_stats = self._safe_get(snap, "dns_stats", {}) or {}
        top_blocked = self._safe_get(snap, "top_blocked", []) or []
        evidence = self._safe_get(snap, "evidence", []) or []

        state = self._safe_get(snap, "user_state", "CHECKING")
        self._apply_state_class(self.query_one("#summary", Static), state)
        summary = (
            f"{self._state_icon(state)} {state}   Recommendation: {self._safe_get(snap, 'recommendation', '-') }\n"
            f"Reason: {' / '.join(self._safe_get(snap, 'reasons', []) or ['-'])}\n"
            f"Threat: [{self._threat_bar(self._safe_get(snap, 'threat_level', 0))}] "
            f"level={self._safe_get(snap, 'threat_level', 0)}   Risk Score: {self._safe_get(snap, 'risk_score', 0)}/100\n"
            f"Next: {self._safe_get(snap, 'next_action_hint', '-') }\n"
            f"CPU: {self._safe_get(snap, 'cpu_percent', 0.0)}%  "
            f"Mem: {self._safe_get(snap, 'mem_used_mb', 0)}/{self._safe_get(snap, 'mem_total_mb', 0)}MB "
            f"({self._safe_get(snap, 'mem_percent', 0)}%)  Temp: {self._safe_get(snap, 'temp_c', 0.0)}C\n"
            f"Monitoring: Suricata={monitoring.get('suricata', 'UNKNOWN')}  "
            f"OpenCanary={monitoring.get('opencanary', 'UNKNOWN')}  ntfy={monitoring.get('ntfy', 'UNKNOWN')}"
        )
        self.query_one("#summary", Static).update(Text(summary))

        connection_text = (
            "Connection\n"
            f"SSID: {self._safe_get(snap, 'ssid', '-')}\n"
            f"BSSID: {self._safe_get(snap, 'bssid', '-')}\n"
            f"Signal: {self._safe_get(snap, 'signal_dbm', '-')} dBm\n"
            f"Channel: {self._safe_get(snap, 'channel', '-')} "
            f"(congestion={self._safe_get(snap, 'channel_congestion', 'unknown')}, "
            f"APs={self._safe_get(snap, 'channel_ap_count', 0)})\n"
            f"Gateway: {self._safe_get(snap, 'gateway_ip', '-')}\n"
            f"Up IF: {self._safe_get(snap, 'up_if', '-')}  IP: {self._safe_get(snap, 'up_ip', '-')}\n"
            f"WiFi: {connection.get('wifi_state', 'UNKNOWN')}  NAT: {connection.get('usb_nat', 'UNKNOWN')}  "
            f"Internet: {connection.get('internet_check', 'UNKNOWN')}"
        )
        self.query_one("#connection", Static).update(Text(connection_text))

        control_text = (
            "Control / Safety\n"
            f"QUIC: {self._safe_get(snap, 'quic', 'unknown')}  "
            f"DoH: {self._safe_get(snap, 'doh', 'unknown')}  DNS mode: {self._safe_get(snap, 'dns_mode', 'unknown')}\n"
            f"Degrade: on={degrade.get('on', False)} rtt={degrade.get('rtt_ms', 0)}ms rate={degrade.get('rate_mbps', 0)}Mbps\n"
            f"Probe: ok={probe.get('tls_ok', 0)}/{probe.get('tls_total', 0)} blocked={probe.get('blocked', 0)}\n"
            f"DNS stats: ok={dns_stats.get('ok', 0)} warn={dns_stats.get('anomaly', 0)} blocked={dns_stats.get('blocked', 0)}\n"
            f"Traffic: down={self._safe_get(snap, 'download_mbps', 0.0):.1f} up={self._safe_get(snap, 'upload_mbps', 0.0):.1f} Mbps"
        )
        self.query_one("#control", Static).update(Text(control_text))

        ev = evidence[-12:] if len(evidence) > 12 else evidence
        evidence_text = "Evidence (last entries)\n" + "\n".join(f"• {line}" for line in ev)
        if not ev:
            evidence_text += "\n- (no evidence)"
        self.query_one("#evidence", Static).update(Text(evidence_text))

        self.query_one("#flow", Static).update(Text(f"Flow: PROBE -> DEGRADED -> NORMAL -> SAFE | state_timeline: {self._safe_get(snap, 'state_timeline', '-') }"))

        if self._details_open:
            blocked_text = ", ".join(f"{d}({c})" for d, c in top_blocked[:5]) if top_blocked else "-"
            details_text = (
                "Details / Internal\n"
                f"state_name={self._safe_get(snap, 'internal', {}).get('state_name', '-')}\n"
                f"suspicion={self._safe_get(snap, 'internal', {}).get('suspicion', '-')}\n"
                f"decay={self._safe_get(snap, 'internal', {}).get('decay', '-')}\n"
                f"top_blocked={blocked_text}"
            )
            self.query_one("#details", Static).update(Text(details_text))

        self._apply_menu_visibility()
        self._render_status_line()

    async def _refresh_snapshot(self, initial: bool = False) -> None:
        if self._is_loading:
            return
        self._is_loading = True
        self._status_message = "Refreshing..."
        self._render_status_line()
        try:
            snap = await asyncio.to_thread(self._load_snapshot_fn)
            self._snapshot = snap
            self._status_message = "Refresh complete"
        except Exception as exc:
            self._status_message = f"Refresh failed: {exc}"
        finally:
            self._is_loading = False
            self._render_panels()

    async def _send_action(self, action: str) -> None:
        try:
            await asyncio.to_thread(self._send_command_fn, action)
            self._status_message = f"Action sent: {action}"
            self._render_panels()
            await self._refresh_snapshot()
        except Exception as exc:
            self._status_message = f"Action failed: {exc}"
            self._render_status_line()

    async def action_refresh(self) -> None:
        await self._refresh_snapshot()

    async def action_stage_open(self) -> None:
        await self._send_action("stage_open")

    async def action_reprobe(self) -> None:
        await self._send_action("reprobe")

    async def action_contain(self) -> None:
        await self._send_action("contain")

    def action_details(self) -> None:
        self._details_open = not self._details_open
        details = self.query_one("#details", Static)
        details.styles.display = "block" if self._details_open else "none"
        self._status_message = "Details shown" if self._details_open else "Details hidden"
        self._render_panels()

    def action_toggle_menu(self) -> None:
        self._menu_open = not self._menu_open
        self._status_message = "Menu opened" if self._menu_open else "Menu closed"
        self._apply_menu_visibility()
        self._render_status_line()

    def action_menu_up(self) -> None:
        if not self._menu_open:
            return
        self._menu_idx = (self._menu_idx - 1) % len(self._menu_items)
        self._apply_menu_visibility()

    def action_menu_down(self) -> None:
        if not self._menu_open:
            return
        self._menu_idx = (self._menu_idx + 1) % len(self._menu_items)
        self._apply_menu_visibility()

    async def action_menu_select(self) -> None:
        if not self._menu_open:
            return
        item = self._menu_items[self._menu_idx]
        kind = item.get("kind")
        if kind == "close_menu":
            self._menu_open = False
            self._status_message = "Menu closed"
            self._apply_menu_visibility()
            self._render_status_line()
            return
        if kind == "toggle_details":
            self.action_details()
            return
        if kind == "refresh":
            await self._refresh_snapshot()
            return
        if kind == "send_action":
            action = str(item.get("action", ""))
            if action:
                await self._send_action(action)


def run_textual(
    load_snapshot_fn: SnapshotLoader,
    send_command_fn: ActionSender,
    unicode_mode: bool,
    start_menu: bool = False,
) -> None:
    app = AzazelTextualApp(
        load_snapshot_fn=load_snapshot_fn,
        send_command_fn=send_command_fn,
        unicode_mode=unicode_mode,
        start_menu=start_menu,
    )
    app.run()
