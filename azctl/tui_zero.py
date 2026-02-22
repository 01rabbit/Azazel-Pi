"""Azazel-Zero style unified Textual TUI for Azazel-Pi.

Ported from Azazel-Zero unified TUI and adapted to Azazel-Pi control paths.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Snapshot:
    now_time: str
    ssid: str
    bssid: str
    channel: str
    signal_dbm: str
    gateway_ip: str
    up_if: str
    up_ip: str
    user_state: str
    recommendation: str
    reasons: List[str]
    next_action_hint: str
    quic: str
    doh: str
    dns_mode: str
    degrade: Dict[str, object]
    probe: Dict[str, object]
    evidence: List[str]
    internal: Dict[str, object]
    connection: Dict[str, object]
    monitoring: Dict[str, str]
    source: str = "SNAPSHOT"
    snapshot_epoch: float = 0.0
    threat_level: int = 0
    risk_score: int = 0
    cpu_percent: float = 0.0
    mem_percent: int = 0
    mem_used_mb: int = 0
    mem_total_mb: int = 0
    temp_c: float = 0.0
    download_mbps: float = 0.0
    upload_mbps: float = 0.0
    channel_congestion: str = "unknown"
    channel_ap_count: int = 0
    state_timeline: str = "-"
    dns_stats: Dict[str, int] = None
    top_blocked: List[Tuple[str, int]] = None

    def __post_init__(self) -> None:
        if self.dns_stats is None:
            self.dns_stats = {"ok": 0, "anomaly": 0, "blocked": 0}
        if self.top_blocked is None:
            self.top_blocked = []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _parse_signal_dbm(raw: Any) -> str:
    try:
        if raw is None:
            return "-"
        text = str(raw).strip().lower().replace("dbm", "").strip()
        if not text or text == "-":
            return "-"
        return str(int(float(text)))
    except Exception:
        return "-"


def _mode_to_state(mode: str) -> Tuple[str, int]:
    m = str(mode or "").strip().lower()
    if m in {"lockdown", "user_lockdown"}:
        return ("CONTAINED", 5)
    if m in {"shield", "user_shield"}:
        return ("LIMITED", 3)
    if m in {"portal", "user_portal"}:
        return ("SAFE", 1)
    return ("CHECKING", 0)


def _service_active(name: str) -> bool:
    try:
        res = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=1.5)
        return res.returncode == 0 and res.stdout.strip() == "active"
    except Exception:
        return False


def _collect_monitoring_state() -> Dict[str, str]:
    return {
        "suricata": "ON" if _service_active("suricata.service") else "OFF",
        "opencanary": "ON" if _service_active("opencanary.service") else "OFF",
        "ntfy": "ON" if _service_active("ntfy.service") else "OFF",
    }


def _run_status_json(lan_if: str, wan_if: str) -> Optional[Dict[str, Any]]:
    try:
        cmd = [
            "python3",
            "-m",
            "azctl.cli",
            "status",
            "--json",
            "--lan-if",
            lan_if,
        ]
        if wan_if:
            cmd.extend(["--wan-if", wan_if])
        env = dict(os.environ)
        env["AZCTL_TUI_STATUS_CALL"] = "1"
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=8, env=env)
        if result.returncode != 0:
            return None
        payload = json.loads(result.stdout)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _snapshot_from_status(lan_if: str, wan_if: str) -> Optional[Snapshot]:
    payload = _run_status_json(lan_if, wan_if)
    if payload is None:
        return None

    wlan = payload.get("wlan1") if isinstance(payload.get("wlan1"), dict) else {}
    mode = str(payload.get("defensive_mode") or "portal")
    state, level = _mode_to_state(mode)
    connected = bool(wlan.get("connected"))

    recommendation = {
        "CONTAINED": "Containment active. Isolate and investigate.",
        "LIMITED": "Threat elevated. Keep monitoring and verify upstream.",
        "SAFE": "Nominal operation.",
        "CHECKING": "Collecting status.",
    }.get(state, "Collecting status.")

    reasons = [f"defensive_mode={mode}"]
    evidence = [
        f"mode={mode}",
        f"wan_connected={connected}",
        f"wan_ssid={wlan.get('ssid') or '-'}",
    ]

    return Snapshot(
        now_time=time.strftime("%H:%M:%S"),
        ssid=str(wlan.get("ssid") or "-"),
        bssid=str(wlan.get("bssid") or "-"),
        channel="-",
        signal_dbm=_parse_signal_dbm(wlan.get("signal_dbm")),
        gateway_ip=str(wlan.get("gateway") or "-"),
        up_if=str(wan_if or "-"),
        up_ip=str(wlan.get("ip4") or "-"),
        user_state=state,
        recommendation=recommendation,
        reasons=reasons,
        next_action_hint="Use menu actions to switch mode",
        quic="unknown",
        doh="unknown",
        dns_mode="azazel",
        degrade={"on": state in {"LIMITED", "CONTAINED"}, "rtt_ms": 0, "rate_mbps": 0},
        probe={"tls_ok": 0, "tls_total": 0, "blocked": 0},
        evidence=evidence,
        internal={"state_name": state, "suspicion": level * 20, "decay": "-"},
        connection={
            "wifi_state": "CONNECTED" if connected else "DISCONNECTED",
            "usb_nat": "UNKNOWN",
            "internet_check": "OK" if connected else "UNKNOWN",
            "captive_portal": "NO",
            "captive_portal_reason": "-",
        },
        monitoring=_collect_monitoring_state(),
        source="AZCTL_STATUS",
        snapshot_epoch=time.time(),
        threat_level=level,
        risk_score=min(100, level * 20),
    )


def load_snapshot(lan_if: str, wan_if: str) -> Snapshot:
    runtime_path = Path("runtime/ui_snapshot.json")
    if runtime_path.exists():
        try:
            data = json.loads(runtime_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                internal = data.get("internal") if isinstance(data.get("internal"), dict) else {}
                state_name = str(internal.get("state_name") or "NORMAL").upper()
                state_map = {
                    "NORMAL": "SAFE",
                    "PROBE": "CHECKING",
                    "DEGRADED": "LIMITED",
                    "CONTAIN": "CONTAINED",
                    "DECEPTION": "DECEPTION",
                }
                state = state_map.get(state_name, "CHECKING")
                connection = data.get("connection") if isinstance(data.get("connection"), dict) else {}
                monitoring = data.get("monitoring") if isinstance(data.get("monitoring"), dict) else _collect_monitoring_state()
                return Snapshot(
                    now_time=str(data.get("now_time") or time.strftime("%H:%M:%S")),
                    ssid=str(data.get("ssid") or "-"),
                    bssid=str(data.get("bssid") or "-"),
                    channel=str(data.get("channel") or "-"),
                    signal_dbm=_parse_signal_dbm(data.get("signal_dbm")),
                    gateway_ip=str(data.get("gateway_ip") or "-"),
                    up_if=str(data.get("up_if") or wan_if or "-"),
                    up_ip=str(data.get("up_ip") or "-"),
                    user_state=state,
                    recommendation=str(data.get("recommendation") or "Checking"),
                    reasons=list(data.get("reasons") or ["-"])[:3],
                    next_action_hint=str(data.get("next_action_hint") or "-"),
                    quic=str(data.get("quic") or "unknown"),
                    doh=str(data.get("doh") or "unknown"),
                    dns_mode=str(data.get("dns_mode") or "unknown"),
                    degrade=data.get("degrade") if isinstance(data.get("degrade"), dict) else {"on": False, "rtt_ms": 0, "rate_mbps": 0},
                    probe=data.get("probe") if isinstance(data.get("probe"), dict) else {"tls_ok": 0, "tls_total": 0, "blocked": 0},
                    evidence=list(data.get("evidence") or [])[-20:],
                    internal=internal,
                    connection=connection,
                    monitoring=monitoring,
                    source="SNAPSHOT",
                    snapshot_epoch=float(data.get("snapshot_epoch") or time.time()),
                    threat_level=min(5, max(0, _safe_int(internal.get("suspicion"), 0) // 20)),
                    risk_score=min(100, max(0, _safe_int(internal.get("suspicion"), 0))),
                    cpu_percent=float(data.get("cpu_percent") or 0.0),
                    mem_percent=_safe_int(data.get("mem_percent"), 0),
                    mem_used_mb=_safe_int(data.get("mem_used_mb"), 0),
                    mem_total_mb=_safe_int(data.get("mem_total_mb"), 0),
                    temp_c=float(data.get("temp_c") or 0.0),
                    download_mbps=float(data.get("download_mbps") or 0.0),
                    upload_mbps=float(data.get("upload_mbps") or 0.0),
                    channel_congestion=str(data.get("channel_congestion") or "unknown"),
                    channel_ap_count=_safe_int(data.get("channel_ap_count"), 0),
                    state_timeline=str(data.get("state_timeline") or "-"),
                    dns_stats=data.get("dns_stats") if isinstance(data.get("dns_stats"), dict) else {"ok": 0, "anomaly": 0, "blocked": 0},
                    top_blocked=data.get("top_blocked") if isinstance(data.get("top_blocked"), list) else [],
                )
        except Exception:
            pass

    snap = _snapshot_from_status(lan_if, wan_if)
    if snap is not None:
        return snap

    return Snapshot(
        now_time=time.strftime("%H:%M:%S"),
        ssid="-",
        bssid="-",
        channel="-",
        signal_dbm="-",
        gateway_ip="-",
        up_if=wan_if or "-",
        up_ip="-",
        user_state="CHECKING",
        recommendation="Status unavailable",
        reasons=["status fetch failed"],
        next_action_hint="verify azctl service",
        quic="unknown",
        doh="unknown",
        dns_mode="unknown",
        degrade={"on": False, "rtt_ms": 0, "rate_mbps": 0},
        probe={"tls_ok": 0, "tls_total": 0, "blocked": 0},
        evidence=["could not read runtime/ui_snapshot.json", "could not query azctl status"],
        internal={"state_name": "UNKNOWN", "suspicion": 0, "decay": "-"},
        connection={"wifi_state": "UNKNOWN", "usb_nat": "UNKNOWN", "internet_check": "UNKNOWN", "captive_portal": "UNKNOWN", "captive_portal_reason": "-"},
        monitoring=_collect_monitoring_state(),
        source="FALLBACK",
        snapshot_epoch=time.time(),
    )


def send_command(action: str) -> None:
    mapping = {
        "stage_open": "portal",
        "contain": "lockdown",
        "reprobe": "shield",
    }
    mode = mapping.get(action)
    if mode is None:
        return

    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", prefix="azctl-tui-", delete=False, encoding="utf-8") as tf:
            tf.write("events:\n")
            tf.write(f"  - name: {mode}\n")
            tf.write("    severity: 0\n")
            temp_path = Path(tf.name)

        result = subprocess.run(
            ["python3", "-m", "azctl.cli", "events", "--config", str(temp_path)],
            capture_output=True,
            text=True,
            timeout=12,
            env={**os.environ, "AZCTL_TUI_STATUS_CALL": "1"},
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "action failed")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def run_menu(lan_if: str, wan_if: str, start_menu: bool = True) -> int:
    try:
        from .tui_zero_textual import run_textual
    except Exception:
        try:
            from tui_zero_textual import run_textual  # type: ignore
        except Exception as e:
            print(f"Textual UI is unavailable: {e}")
            print("Install dependency: pip install textual")
            return 1

    run_textual(
        load_snapshot_fn=lambda: load_snapshot(lan_if, wan_if),
        send_command_fn=send_command,
        unicode_mode=True,
        start_menu=start_menu,
    )
    return 0
