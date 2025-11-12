#!/usr/bin/env python3
"""Helper to run epd_daemon test-mode against a given WAN state file.

Usage:
    python tests/helpers/run_wan_state_test.py /path/to/wan_state.json /tmp/out.png

This script writes a minimal WAN state file if it does not exist, then runs
`azazel_pi.core.display.epd_daemon` in test+emulate mode pointing at that file and
saving the output PNG to the given path.
"""
from __future__ import annotations

import json
import subprocess
from azazel_pi.utils.cmd_runner import run as run_cmd
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Usage: run_wan_state_test.py <wan_state.json> <output_png>")
        return 2

    wan_path = Path(argv[1])
    out_png = Path(argv[2])

    if not wan_path.exists():
        wan = {
            "active_interface": "eth0",
            "status": "degraded",
            "message": "manual-test",
            "candidates": [],
        }
        wan_path.parent.mkdir(parents=True, exist_ok=True)
        wan_path.write_text(json.dumps(wan))

    cmd = [
        sys.executable,
        "-m",
        "azazel_pi.core.display.epd_daemon",
        "--mode",
        "test",
        "--emulate",
        "--wan-state-path",
        str(wan_path),
        "--emulate-output",
        str(out_png),
    ]

    print("Running:", " ".join(cmd))
    res = run_cmd(cmd)
    return res.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
