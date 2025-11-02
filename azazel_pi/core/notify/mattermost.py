"""Simplified Mattermost webhook client and YAML-backed helper.

This module provides a tiny notifier class (kept for compatibility)
and a convenience function `send_alert_to_mattermost` that loads
the webhook URL from `configs/notify.yaml` when available.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import json
import urllib.request
from pathlib import Path
import yaml


@dataclass
class MattermostNotifier:
    webhook_url: str

    def format_payload(self, message: str, level: str = "info") -> Dict[str, Any]:
        return {"text": message, "props": {"severity": level}}

    def send(self, message: str, level: str = "info") -> None:
        data = json.dumps(self.format_payload(message, level)).encode()
        request = urllib.request.Request(self.webhook_url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(request, timeout=5)


def _load_notify_cfg() -> Dict[str, Any]:
    cfg_path = Path(__file__).resolve().parents[1] / "configs" / "notify.yaml"
    if cfg_path.exists():
        try:
            return yaml.safe_load(cfg_path.read_text()) or {}
        except Exception:
            return {}
    return {}


def send_alert_to_mattermost(message: str, level: str = "info") -> None:
    """Convenience sender for quick notifications from azazel_core.

    Reads `mattermost_webhook_url` from `configs/notify.yaml` if present.
    """
    cfg = _load_notify_cfg()
    webhook = cfg.get("mattermost_webhook_url")
    if not webhook:
        # Nothing configured; be a no-op to avoid surprising network calls
        return
    notifier = MattermostNotifier(webhook_url=webhook)
    notifier.send(message, level)
