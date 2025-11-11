#!/usr/bin/env python3
"""Demo event injector for Azazel-Pi

Append crafted Suricata-like alert JSON lines to the configured eve.json
to drive scoring for demos. Run with sudo to write to /var/log/suricata/eve.json.

Usage examples:
  sudo python3 scripts/demo_injector.py --count 150 --interval 0.1 --severity 80
  sudo python3 scripts/demo_injector.py --count 50 --burst --severity 100
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import random


TEMPLATE_ALERTS = [
    {
        "proto": "TCP",
        "dest_port": 22,
        "signature": "ET BRUTEFORCE SSH Brute force attempt",
    },
    {
        "proto": "TCP",
        "dest_port": 80,
        "signature": "ET EXPLOIT Possible buffer overflow",
    },
    {
        "proto": "UDP",
        "dest_port": 0,
        "signature": "ET DOS Possible DDoS amplification",
    },
    {
        "proto": "ICMP",
        "dest_port": None,
        "signature": "ET SCAN Potential scan detected (NMAP)",
    },
]


def make_event(severity: int) -> str:
    now = datetime.now(timezone.utc).isoformat()
    t = random.choice(TEMPLATE_ALERTS)
    ev = {
        "event_type": "alert",
        "timestamp": now,
        "src_ip": f"198.51.100.{random.randint(2,250)}",
        "dest_ip": "172.16.0.10",
        "proto": t["proto"],
        "dest_port": t["dest_port"],
        "alert": {"signature": t["signature"], "severity": int(severity)},
    }
    # Return single-line JSON
    return json.dumps(ev, separators=(',', ':'))


def append_event(path: Path, line: str) -> None:
    with path.open('a') as fh:
        fh.write(line + '\n')


def main() -> int:
    p = argparse.ArgumentParser(description="Inject demo Suricata EVE events to drive scoring")
    p.add_argument('--path', type=Path, default=Path('/var/log/suricata/eve.json'), help='Path to eve.json')
    p.add_argument('--count', type=int, default=100, help='Number of events to inject')
    p.add_argument('--interval', type=float, default=0.2, help='Seconds between events (ignored with --burst)')
    p.add_argument('--severity', type=int, default=80, help='Severity to set on injected alerts')
    p.add_argument('--burst', action='store_true', help='Inject as fast as possible with no sleep')
    p.add_argument('--prefix', type=str, default='', help='Optional prefix text to include in signature')
    args = p.parse_args()

    target = args.path
    if not target.parent.exists():
        print(f"Path {target} does not exist and parent {target.parent} missing")
        return 2

    print(f"Injecting {args.count} events to {target} (severity={args.severity}, interval={'burst' if args.burst else args.interval}s)")

    for i in range(args.count):
        try:
            line = make_event(args.severity)
            if args.prefix:
                # cheap way to add prefix into signature
                obj = json.loads(line)
                obj['alert']['signature'] = f"{args.prefix} {obj['alert']['signature']}"
                line = json.dumps(obj, separators=(',', ':'))
            append_event(target, line)
        except PermissionError:
            print(f"Permission denied writing to {target}. Run with sudo.")
            return 3
        except Exception as e:
            print(f"Write failed: {e}")
            return 4

        if not args.burst:
            time.sleep(max(0.0, args.interval))

    print("Done")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
