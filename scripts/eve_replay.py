#!/usr/bin/env python3
"""EVE Replay for demo (Tool A alternative)

Writes synthetic Suricata EVE JSON alert lines to a demo file (default: runtime/demo_eve.json)
at a configurable interval. Designed to escalate threat level over a sequence so that the
monitoring pipeline (azctl serve or main_suricata) will detect and enact mode transitions.

Usage:
  python3 scripts/eve_replay.py --file runtime/demo_eve.json --interval 5

This script is safe to run locally; it only appends JSON lines to the chosen file.
Run the monitoring daemon with:
  python3 -m azctl.cli serve --suricata-eve runtime/demo_eve.json --decisions-log ./decisions.log

Then start this script to inject alerts.
"""
from __future__ import annotations

import time
import json
import argparse
from datetime import datetime
from pathlib import Path

SAMPLE_ALERTS = [
    # low -> reconnaissance
    {
        "event_type": "alert",
        "timestamp": "{ts}",
        "src_ip": "10.0.0.5",
        "dest_ip": "172.16.0.10",
        "proto": "ICMP",
        "dest_port": None,
        "alert": {"signature": "ET SCAN Potential scan detected (NMAP)", "severity": 4}
    },
    # medium -> brute/scan
    {
        "event_type": "alert",
        "timestamp": "{ts}",
        "src_ip": "198.51.100.23",
        "dest_ip": "172.16.0.10",
        "proto": "TCP",
        "dest_port": 22,
        "alert": {"signature": "ET BRUTEFORCE SSH Brute force attempt", "severity": 3}
    },
    # higher -> exploit
    {
        "event_type": "alert",
        "timestamp": "{ts}",
        "src_ip": "198.51.100.23",
        "dest_ip": "172.16.0.10",
        "proto": "TCP",
        "dest_port": 80,
        "alert": {"signature": "ET EXPLOIT Possible buffer overflow", "severity": 1}
    },
    # final aggressive -> ddos/flood
    {
        "event_type": "alert",
        "timestamp": "{ts}",
        "src_ip": "203.0.113.9",
        "dest_ip": "172.16.0.10",
        "proto": "UDP",
        "dest_port": 0,
        "alert": {"signature": "ET DOS Possible DDoS amplification", "severity": 1}
    }
]


def append_line(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False))
        fh.write("\n")


def main():
    parser = argparse.ArgumentParser(description="EVE replay generator for Azazel demo")
    parser.add_argument("--file", default="runtime/demo_eve.json", help="Path to EVE file to append to")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between alert injections")
    parser.add_argument("--loop", action="store_true", help="Loop the sequence until stopped")
    args = parser.parse_args()

    eve_path = Path(args.file)
    seq = SAMPLE_ALERTS

    print(f"EVE replay: writing to {eve_path} every {args.interval}s (loop={args.loop})")

    try:
        while True:
            for item in seq:
                data = dict(item)
                ts = datetime.now().isoformat()
                data["timestamp"] = ts
                # normalize None dest_port to null
                if data.get("dest_port") is None:
                    data["dest_port"] = None
                append_line(eve_path, data)
                print(f"Appended alert: {data['alert']['signature']} @ {ts}")
                time.sleep(args.interval)
            if not args.loop:
                break
    except KeyboardInterrupt:
        print("EVE replay interrupted by user")


if __name__ == "__main__":
    main()
