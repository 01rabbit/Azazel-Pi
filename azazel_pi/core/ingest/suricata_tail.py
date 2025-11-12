"""Enhanced streaming helper for Suricata EVE logs with filtering."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Optional, Set

from ..state_machine import Event
from .. import notify_config


@dataclass
class FilteredEvent:
    """Represents a filtered and enriched Suricata event."""

    timestamp: str
    event_type: str
    signature: str
    severity: int
    src_ip: str
    dest_ip: str
    proto: str
    dest_port: Optional[int] = None
    confidence: str = "Unknown"
    details: Dict = None

    @classmethod
    def from_eve_record(cls, record: Dict) -> Optional["FilteredEvent"]:
        """Create a FilteredEvent from a Suricata EVE record."""
        if record.get("event_type") != "alert":
            return None

        alert = record.get("alert", {})
        signature = alert.get("signature", "")

        # Filter events by category
        category = signature.split(" ", 2)[1] if signature.startswith("ET ") else None
        if category and category not in FILTER_CATEGORIES:
            return None

        return cls(
            timestamp=record.get("timestamp", ""),
            event_type=record.get("event_type", "alert"),
            signature=signature,
            severity=int(alert.get("severity", 3)),
            src_ip=record.get("src_ip", ""),
            dest_ip=record.get("dest_ip", ""),
            proto=record.get("proto", ""),
            dest_port=record.get("dest_port"),
            confidence=alert.get("metadata", {}).get("confidence", ["Unknown"])[0],
            details=alert,
        )


@dataclass
class SuricataTail:
    """Enhanced Suricata log tailer with filtering and rate limiting."""

    path: Path
    cooldown_seconds: int = 60
    skip_existing: bool = True

    def __post_init__(self) -> None:
        self.last_alert_times: Dict[str, float] = {}
        self.suppressed_alerts: Dict[str, int] = {}
        self.last_summary_time = time.time()

    def stream(self) -> Generator[Event, None, None]:
        """Yield events from an EVE JSON log with filtering."""
        pos = None

        while True:
            if not self.path.exists():
                time.sleep(1)
                continue

            size = self.path.stat().st_size
            with self.path.open() as f:
                if pos is None:
                    if self.skip_existing:
                        f.seek(0, 2)
                    pos = f.tell()

                if size < pos:
                    pos = 0
                f.seek(pos)

                for line in f:
                    try:
                        record = json.loads(line)
                        event = FilteredEvent.from_eve_record(record)
                        if event:
                            # Yield enriched Event including network/source metadata
                            yield Event(
                                name=event.event_type,
                                severity=event.severity,
                                src_ip=event.src_ip,
                                dest_ip=event.dest_ip,
                                signature=event.signature,
                                details=event.details,
                            )
                    except json.JSONDecodeError:
                        continue

                pos = f.tell()
            time.sleep(0.5)

    def should_notify(self, key: str) -> bool:
        """Check if an alert should be shown based on cooldown."""
        now = time.time()
        last = self.last_alert_times.get(key)
        if not last or (now - last) > self.cooldown_seconds:
            self.last_alert_times[key] = now
            return True
        return False


# Categories of events to process
FILTER_CATEGORIES: Set[str] = {
    "Attack Response", "DNS", "DOS", "Exploit", "FTP",
    "ICMP", "IMAP", "Malware", "NETBIOS", "Phishing",
    "POP3", "RPC", "SCAN", "Shellcode", "SMTP",
    "SNMP", "SQL", "TELNET", "TFTP", "Web Client",
    "Web Server", "Web Specific Apps", "WORM"
}
