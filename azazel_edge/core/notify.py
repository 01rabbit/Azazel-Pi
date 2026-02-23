"""Notification helpers for security workflow events (Mattermost + ntfy)."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, Optional

from . import notify_config


class MattermostNotifier:
    """Send structured webhook payloads for a limited set of security events."""

    def __init__(self) -> None:
        cfg = notify_config.get("mattermost", {}) or {}
        self.webhook = cfg.get("webhook_url") or notify_config.MATTERMOST_WEBHOOK_URL
        self.channel = cfg.get("channel") or None
        self.username = cfg.get("username") or None
        self.icon = cfg.get("icon_emoji") or None
        self.notify_users: Iterable[str] = cfg.get("notify_users") or []
        enabled_flag = cfg.get("enabled", True)

        suppress = notify_config.get("suppress", {}) or {}
        self.cooldown_seconds = int(suppress.get("cooldown_seconds", 60) or 60)

        self.enabled = bool(enabled_flag and self.webhook)
        self._last_sent: Dict[str, float] = {}

    # ------------------------------------------------------------------ #
    # Public notification helpers limited to the three approved triggers #
    # ------------------------------------------------------------------ #
    def notify_threat_detected(self, alert: Dict[str, Any]) -> bool:
        """Send a Suricata threat notification with signature/IP/severity."""
        if not alert:
            return False
        payload = {
            "type": "suricata_threat",
            "signature": alert.get("signature") or alert.get("event"),
            "severity": alert.get("severity"),
            "src_ip": alert.get("src_ip"),
            "dest_ip": alert.get("dest_ip"),
            "proto": alert.get("proto"),
            "dest_port": alert.get("dest_port"),
            "timestamp": alert.get("timestamp"),
        }
        key = f"threat:{payload.get('signature')}:{payload.get('src_ip')}"
        fields = [
            ("Signature", payload.get("signature") or "-"),
            ("Severity", payload.get("severity") or "-"),
            ("Source IP", payload.get("src_ip") or "-"),
            ("Destination IP", payload.get("dest_ip") or "-"),
            ("Protocol", payload.get("proto") or "-"),
            ("Destination Port", payload.get("dest_port") or "-"),
            ("Timestamp", payload.get("timestamp") or "-"),
        ]
        text = self._render_message("⚠️ Suricata detected a new threat", fields)
        return self._send(text, key, payload)

    def notify_redirect_change(self, target_ip: str, endpoints: Iterable[Dict[str, Any]], applied: bool) -> bool:
        """Inform Mattermost when OpenCanary diversion rules are applied/removed."""
        payload = {
            "type": "traffic_redirect",
            "target_ip": target_ip,
            "status": "applied" if applied else "removed",
            "endpoints": list(endpoints),
        }
        action = "applied" if applied else "removed"
        key = f"redirect:{target_ip}:{action}"
        if payload["endpoints"]:
            port_desc = ", ".join(
                f"{ep.get('protocol','tcp').lower()}/{ep.get('port')}" for ep in payload["endpoints"]
            )
        else:
            port_desc = "all protocols"
        fields = [
            ("Target IP", target_ip),
            ("Status", action),
            ("Ports", port_desc),
        ]
        text = self._render_message("🔁 Traffic diversion change", fields)
        return self._send(text, key, payload)

    def notify_mode_change(self, previous: str, current: str, average: float) -> bool:
        """Emit a message when the defensive mode changes."""
        payload = {
            "type": "mode_change",
            "previous": previous,
            "current": current,
            "average_score": round(float(average), 2),
        }
        key = f"mode:{previous}->{current}"
        fields = [
            ("Previous", previous),
            ("Current", current),
            ("Average score", payload["average_score"]),
        ]
        text = self._render_message("🛡️ Defense mode changed", fields)
        return self._send(text, key, payload)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #
    def _render_message(self, title: str, fields: Iterable[tuple[str, Any]]) -> str:
        parts = [title]
        for label, value in fields:
            if value in (None, "", []):
                continue
            parts.append(f"{label}: {value}")
        return "\n".join(parts)

    def _should_send(self, key: str) -> bool:
        if not key:
            return True
        now = time.time()
        last = self._last_sent.get(key)
        if not last or (now - last) > self.cooldown_seconds:
            self._last_sent[key] = now
            return True
        return False

    def _send(self, text: str, key: str, payload: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        if not self._should_send(key):
            return False

        try:
            body = {"text": text}
            if self.channel:
                body["channel"] = self.channel
            if self.username:
                body["username"] = self.username
            if self.icon:
                body["icon_emoji"] = self.icon
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(self.webhook, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                return 200 <= resp.getcode() < 300
        except urllib.error.HTTPError:
            return False
        except Exception:
            return False


class NtfyNotifier:
    """Send security notifications to a self-hosted ntfy endpoint."""

    def __init__(self) -> None:
        notify_cfg = notify_config.get("notify", {}) or {}
        ntfy_cfg = notify_cfg.get("ntfy", {}) if isinstance(notify_cfg, dict) else {}
        suppress = notify_config.get("suppress", {}) or {}

        self.base_url = str(ntfy_cfg.get("base_url", "http://10.55.0.10:8081")).rstrip("/")
        self.topic_alert = str(ntfy_cfg.get("topic_alert", "azg-alert-critical"))
        self.topic_info = str(ntfy_cfg.get("topic_info", "azg-info-status"))
        self.token_file = str(ntfy_cfg.get("token_file", "/etc/azazel/ntfy.token"))
        self.cooldown_seconds = int(
            ntfy_cfg.get("cooldown_sec", suppress.get("cooldown_seconds", 60)) or 60
        )
        self.timeout = float(ntfy_cfg.get("timeout_seconds", 2.0) or 2.0)

        enabled_flag = bool(ntfy_cfg.get("enabled", True))
        self.token = self._read_token(self.token_file)
        self.enabled = bool(enabled_flag and self.base_url and self.token)
        self._last_sent: Dict[str, float] = {}

    def notify_threat_detected(self, alert: Dict[str, Any]) -> bool:
        if not alert:
            return False
        signature = alert.get("signature") or alert.get("event") or "Unknown threat"
        src_ip = alert.get("src_ip") or "-"
        sev = alert.get("severity") or "-"
        body = "\n".join(
            [
                f"Signature: {signature}",
                f"Severity: {sev}",
                f"Source IP: {src_ip}",
                f"Destination IP: {alert.get('dest_ip') or '-'}",
                f"Protocol: {alert.get('proto') or '-'}",
                f"Destination Port: {alert.get('dest_port') or '-'}",
            ]
        )
        key = f"ntfy:threat:{signature}:{src_ip}"
        return self._send(
            topic=self.topic_alert,
            title="Suricata detected a new threat",
            body=body,
            key=key,
            priority=5,
            tags=("warning", "shield"),
            payload={"type": "suricata_threat", "signature": signature, "src_ip": src_ip},
        )

    def notify_redirect_change(self, target_ip: str, endpoints: Iterable[Dict[str, Any]], applied: bool) -> bool:
        status = "applied" if applied else "removed"
        endpoint_list = list(endpoints or [])
        ports = ", ".join(
            f"{ep.get('protocol', 'tcp').lower()}/{ep.get('port')}" for ep in endpoint_list
        ) if endpoint_list else "all protocols"
        body = "\n".join(
            [
                f"Target IP: {target_ip}",
                f"Status: {status}",
                f"Ports: {ports}",
            ]
        )
        key = f"ntfy:redirect:{target_ip}:{status}"
        return self._send(
            topic=self.topic_info,
            title="Traffic diversion change",
            body=body,
            key=key,
            priority=3 if applied else 2,
            tags=("arrows_counterclockwise", "network"),
            payload={"type": "traffic_redirect", "target_ip": target_ip, "status": status},
        )

    def notify_mode_change(self, previous: str, current: str, average: float) -> bool:
        body = "\n".join(
            [
                f"Previous: {previous}",
                f"Current: {current}",
                f"Average score: {round(float(average), 2)}",
            ]
        )
        key = f"ntfy:mode:{previous}->{current}"
        return self._send(
            topic=self.topic_info,
            title="Defense mode changed",
            body=body,
            key=key,
            priority=3,
            tags=("shield",),
            payload={"type": "mode_change", "previous": previous, "current": current},
        )

    @staticmethod
    def _read_token(path: str) -> str:
        try:
            if path and os.path.exists(path):
                return open(path, "r", encoding="utf-8").read().strip()
        except Exception:
            return ""
        return ""

    def _should_send(self, key: str) -> bool:
        if not key:
            return True
        now = time.time()
        last = self._last_sent.get(key)
        if not last or (now - last) > self.cooldown_seconds:
            self._last_sent[key] = now
            return True
        return False

    def _send(
        self,
        topic: str,
        title: str,
        body: str,
        key: str,
        priority: int,
        tags: Iterable[str],
        payload: Dict[str, Any],
    ) -> bool:
        del payload  # payload kept for parity with Mattermost; not needed in HTTP request.
        if not self.enabled or not topic:
            return False
        if not self._should_send(key):
            return False

        url = f"{self.base_url}/{topic}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Title": title,
            "Priority": str(priority),
            "Tags": ",".join(tags),
            "Content-Type": "text/plain; charset=utf-8",
        }
        data = body.encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return 200 <= resp.getcode() < 300
        except urllib.error.HTTPError:
            return False
        except Exception:
            return False


class CompositeNotifier:
    """Fan-out notifier that invokes all configured notifier backends."""

    def __init__(self, notifiers: Iterable[object]) -> None:
        self._notifiers = list(notifiers)

    def notify_threat_detected(self, alert: Dict[str, Any]) -> bool:
        return self._broadcast("notify_threat_detected", alert)

    def notify_redirect_change(self, target_ip: str, endpoints: Iterable[Dict[str, Any]], applied: bool) -> bool:
        return self._broadcast("notify_redirect_change", target_ip, endpoints, applied)

    def notify_mode_change(self, previous: str, current: str, average: float) -> bool:
        return self._broadcast("notify_mode_change", previous, current, average)

    def _broadcast(self, method: str, *args: Any) -> bool:
        sent = False
        for notifier in self._notifiers:
            fn = getattr(notifier, method, None)
            if not fn:
                continue
            try:
                sent = bool(fn(*args)) or sent
            except Exception:
                continue
        return sent


def build_default_notifier() -> object | None:
    """Build default notifier chain (Mattermost + ntfy when configured)."""
    backends: list[object] = []
    try:
        mm = MattermostNotifier()
        if getattr(mm, "enabled", False):
            backends.append(mm)
    except Exception:
        pass
    try:
        ntfy = NtfyNotifier()
        if getattr(ntfy, "enabled", False):
            backends.append(ntfy)
    except Exception:
        pass

    if not backends:
        return None
    if len(backends) == 1:
        return backends[0]
    return CompositeNotifier(backends)
