import json
import os
from pathlib import Path
import tempfile
import subprocess

import pytest

from azazel_pi.core.display import epd_daemon


def test_status_collector_reads_wan_state(tmp_path):
    # prepare a WAN state file
    state = {
        "active_interface": "test0",
        "status": "degraded",
        "message": "link flaps",
        "candidates": [],
    }
    path = tmp_path / "wan_state.json"
    path.write_text(json.dumps(state))

    # create collector with explicit path
    collector = epd_daemon.StatusCollector(events_log=None, wan_state_path=path)
    net = collector._get_network_status()

    assert net.wan_state == "degraded"
    assert net.wan_message == "link flaps"
    assert net.interface == "test0"


def test_epd_daemon_test_mode_saves_image(tmp_path, monkeypatch):
    # prepare a fake status and renderer to avoid hardware access
    out_path = tmp_path / "out.png"
    # Run as a subprocess invoking the module to keep behavior realistic
    cmd = [
        "python",
        "-m",
        "azazel_pi.core.display.epd_daemon",
        "--mode",
        "test",
        "--emulate",
        "--emulate-output",
        str(out_path),
    ]

    # Run the command; it should exit 0 and write the output file
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Module failed: {res.stderr}"
    assert out_path.exists(), "Emulate output image was not created"
