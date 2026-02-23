"""Simple tailer for OpenCanary log (JSON lines).

Yields Event objects with name 'canary' for ingestion by AzazelDaemon.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Generator, Optional

from ..state_machine import Event
from .. import notify_config


@dataclass
class CanaryTail:
    path: Path
    skip_existing: bool = True

    def stream(self) -> Generator[Event, None, None]:
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
                        # OpenCanary output formats vary; try to extract an IP
                        src_ip = None
                        if isinstance(record, dict):
                            # common keys
                            src_ip = record.get("src_ip") or record.get("src") or record.get("remote_addr")
                            ts = record.get("timestamp") or record.get("time")
                        else:
                            ts = None

                        if src_ip:
                            yield Event(
                                name="canary",
                                severity=0,
                                src_ip=str(src_ip),
                                timestamp=str(ts) if ts else None,
                                details=record,
                            )
                    except json.JSONDecodeError:
                        continue

                pos = f.tell()
            time.sleep(0.5)


def default_canary_tail(skip_existing: bool = True) -> CanaryTail:
    path = Path(notify_config.OPENCANARY_LOG_PATH)
    return CanaryTail(path=path, skip_existing=skip_existing)

