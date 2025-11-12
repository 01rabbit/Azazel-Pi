"""Central, test-injectable subprocess runner used across the project.

This module exposes:
- run(cmd, **kwargs): proxy to the current runner (defaults to subprocess.run)
- set_runner(runner): set a custom runner for tests (callable with same signature)
- reset_runner(): restore default

The runner should accept the same parameters as subprocess.run and return
an object with attributes: returncode, stdout, stderr when capture_output/text
are used. Tests can inject a lightweight callable (e.g., FakeSubprocess).
"""
from __future__ import annotations
import subprocess
from typing import Callable

# Default runner is subprocess.run
_runner: Callable = subprocess.run


def run(cmd, **kwargs):
    """Run command via the currently configured runner.

    Accepts the same args as subprocess.run and returns whatever the runner returns.
    """
    return _runner(cmd, **kwargs)


def set_runner(runner: Callable):
    """Set custom runner for tests.

    runner: callable(cmd, **kwargs) -> CompletedProcess-like
    """
    global _runner
    _runner = runner


def reset_runner():
    """Reset runner to subprocess.run."""
    global _runner
    _runner = subprocess.run
