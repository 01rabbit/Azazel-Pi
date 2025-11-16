import json
import subprocess
import tempfile
import types
from pathlib import Path

import pytest

from azazel_pi.core.enforcer.traffic_control import TrafficControlEngine, TrafficControlRule


class DummyCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_restore_persisted_nft_handles(tmp_path, monkeypatch):
    tmp_file = tmp_path / "diversions.json"
    data = {
        "198.51.100.1": {
            "family": "inet",
            "table": "azazel",
            "handle": "123",
            "action": "redirect",
            "dest_port": None
        },
        "198.51.100.2": {
            "family": "inet",
            "table": "azazel",
            "handle": "124",
            "action": "block"
        }
    }
    tmp_file.write_text(json.dumps(data))

    monkeypatch.setattr(TrafficControlEngine, '_diversion_state_path', lambda self: tmp_file)

    def fake_run(cmd, capture_output=False, text=False, timeout=None, check=False):
        joined = ' '.join(cmd)
        if 'tc qdisc show' in joined:
            return DummyCompleted(0, stdout="")
        return DummyCompleted(0, stdout="")

    monkeypatch.setattr(subprocess, 'run', fake_run)

    engine = TrafficControlEngine(config_path=str(tmp_path / 'nope.yaml'))
    rules = engine.get_active_rules()

    assert "198.51.100.1" in rules
    assert any(r.action_type == 'redirect' for r in rules['198.51.100.1'])
    assert "198.51.100.2" in rules
    assert any(r.action_type == 'block' for r in rules['198.51.100.2'])


def test_replace_only_invoked(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output=False, text=False, timeout=None, check=False):
        calls.append(cmd)
        # Simulate replace returning non-zero with "File exists" on some calls
        if 'qdisc' in cmd and 'replace' in cmd:
            return DummyCompleted(0, stdout="")
        if 'class' in cmd and 'replace' in cmd:
            return DummyCompleted(0, stdout="")
        if 'filter' in cmd and 'replace' in cmd:
            return DummyCompleted(0, stdout="")
        return DummyCompleted(0, stdout="")

    monkeypatch.setattr(subprocess, 'run', fake_run)
    engine = TrafficControlEngine(config_path='/nonexistent')
    # apply a delay which would call tc class replace / qdisc replace / filter replace
    ok = engine.apply_delay('198.51.100.99', 50)
    assert ok is True
    # ensure replace cmds were called (not add)
    joined = [' '.join(c) for c in calls]
    assert any('tc qdisc replace' in ' '.join(c) or 'tc class replace' in ' '.join(c) for c in calls)
