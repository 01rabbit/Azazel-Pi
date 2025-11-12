"""Mattermost notification helper with simple suppression logic.

This module reads configuration from `azazel_pi.core.notify_config` and only
sends notifications when a Mattermost webhook is configured.

Suppression is implemented with an in-memory last-sent map keyed by a
user-provided key (e.g. "signature:src_ip") and cooldown seconds from
config.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

from . import notify_config


class MattermostNotifier:
    def __init__(self) -> None:
        cfg = notify_config.get("mattermost", {}) or {}
        self.webhook = cfg.get("webhook_url") or notify_config.MATTERMOST_WEBHOOK_URL
        self.channel = cfg.get("channel") or "azazel-alerts"
        self.username = cfg.get("username") or "Azazel-Bot"
        self.icon = cfg.get("icon_emoji") or ":shield:"

        # Suppression settings
        suppress = notify_config.get("suppress", {}) or {}
        self.cooldown_seconds = int(suppress.get("cooldown_seconds", 60) or 60)

        self.enabled = bool(self.webhook)
        self._last_sent: Dict[str, float] = {}

    def _should_send(self, key: str) -> bool:
        if not key:
            return True
        now = time.time()
        last = self._last_sent.get(key)
        if not last or (now - last) > self.cooldown_seconds:
            self._last_sent[key] = now
            return True
        return False

    def notify(self, payload: Dict[str, Any], key: Optional[str] = None) -> bool:
        """Send a notification payload (dict) to Mattermost via webhook.

        payload: dictionary with summary data. This will be rendered into a
        simple text message. key: suppression key; if provided, repeated sends
        within cooldown_seconds will be suppressed.
        """
        if not self.enabled:
            return False

        key = key or ""
        if not self._should_send(key):
            return False

        try:
            text_lines = [f"*{payload.get('event','') }* — score {payload.get('score','')}"]
            if payload.get("src_ip"):
                text_lines.append(f"Source: {payload.get('src_ip')}")
            if payload.get("mode"):
                text_lines.append(f"Mode: {payload.get('mode')}")
            if payload.get("actions"):
                text_lines.append(f"Actions: {payload.get('actions')}")

            message = "\n".join(text_lines)

            body = {
                "channel": self.channel,
                "username": self.username,
                "icon_emoji": self.icon,
                "text": message,
            }

            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(self.webhook, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                return 200 <= resp.getcode() < 300
        except urllib.error.HTTPError:
            return False
        except Exception:
            return False
