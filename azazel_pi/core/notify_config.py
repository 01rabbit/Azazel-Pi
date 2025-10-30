"""Shared notification configuration loader.

Provides a small compatibility layer so legacy monitoring scripts and
`azazel_core` can read the same `configs/notify.yaml` settings.

Exports the same names legacy code expects (e.g. MATTERMOST_WEBHOOK_URL,
SURICATA_EVE_JSON_PATH) and a helper `get()` for ad-hoc values.
"""
from __future__ import annotations

from datetime import timezone, timedelta
from pathlib import Path
from typing import Any, Dict
import yaml


_DEFAULTS: Dict[str, Any] = {
    "tz": "+09:00",
    "mattermost": {
        "webhook_url": "",
        "channel": "azazel-alerts",
        "username": "Azazel-Bot",
        "icon_emoji": ":shield:",
    },
    "paths": {
        "events": "/opt/azazel/logs/events.json",
        "opencanary": "/opt/azazel/logs/opencanary.log",
        "suricata_eve": "/var/log/suricata/eve.json",
        "decisions": "/var/log/azazel/decisions.log",
    },
    "suppress": {
        "key_mode": "signature_ip_user",
        "cooldown_seconds": 60,
        "summary_interval_mins": 5,
    },
    "opencanary": {
        "ip": "172.16.10.10",
        "ports": [22, 80, 5432],
    },
    "network": {
        "interface": "wlan1",
        "inactivity_minutes": 2,
        "delay": {
            "base_ms": 500,
            "jitter_ms": 100,
        },
    },
}


def _cfg_path() -> Path:
    # configs/notify.yaml at repository root (relative to this file)
    return Path(__file__).resolve().parents[1] / "configs" / "notify.yaml"


def _load() -> Dict[str, Any]:
    path = _cfg_path()
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}


_CFG = _load()

# timezone helper: legacy code used TZ constant. Provide a fixed +9 timezone.
TZ = timezone(timedelta(hours=9))

# Helper function to get nested config values
def _get_nested(cfg: Dict[str, Any], path: str, default: Any = None) -> Any:
    """Get a nested config value using dot notation (e.g., 'mattermost.webhook_url')"""
    parts = path.split('.')
    current = cfg
    for part in parts:
        if not isinstance(current, dict):
            return default
        if part not in current:
            return default
        current = current[part]
    return current

# Backwards-compatible uppercase names
MATTERMOST_WEBHOOK_URL = _get_nested(_CFG, "mattermost.webhook_url", _DEFAULTS["mattermost"]["webhook_url"])
EVENTS_JSON_PATH = _get_nested(_CFG, "paths.events", _DEFAULTS["paths"]["events"])
OPENCANARY_LOG_PATH = _get_nested(_CFG, "paths.opencanary", _DEFAULTS["paths"]["opencanary"])
SURICATA_EVE_JSON_PATH = _get_nested(_CFG, "paths.suricata_eve", _DEFAULTS["paths"]["suricata_eve"])
SUPPRESS_KEY_MODE = _get_nested(_CFG, "suppress.key_mode", _DEFAULTS["suppress"]["key_mode"])
OPENCANARY_IP = _get_nested(_CFG, "opencanary.ip", _DEFAULTS["opencanary"]["ip"])
NET_INTERFACE = _get_nested(_CFG, "network.interface", _DEFAULTS["network"]["interface"])
INACTIVITY_MINUTES = int(_get_nested(_CFG, "network.inactivity_minutes", _DEFAULTS["network"]["inactivity_minutes"]))


def get(key: str, default: Any = None) -> Any:
    """Return a config value by key (prefers YAML, falls back to defaults)."""
    if key in _CFG:
        return _CFG[key]
    return _DEFAULTS.get(key, default)
