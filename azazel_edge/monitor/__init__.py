"""Monitor daemons for log watching and event processing."""

from .main_suricata import watch_suricata
from .main_opencanary import watch_opencanary

__all__ = [
    "watch_suricata", 
    "watch_opencanary",
]