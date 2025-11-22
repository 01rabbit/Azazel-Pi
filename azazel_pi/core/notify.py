"""Mattermost notification helper constrained to security workflow events."""
from __future__ import annotations

import json
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
