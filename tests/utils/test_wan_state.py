import os
from pathlib import Path

from azazel_edge.utils import wan_state


def test_update_and_load_custom_path(tmp_path, monkeypatch):
    """WAN state helpers should honor custom file paths."""
    state_path = tmp_path / "wan_state.json"
    monkeypatch.setenv("AZAZEL_WAN_STATE_PATH", str(state_path))

    # Initial load should be empty
    state = wan_state.load_wan_state(state_path)
    assert state.active_interface is None

    wan_state.update_wan_state(
        active_interface="eth0",
        status="ready",
        message="eth0 selected",
        path=state_path,
    )
    state = wan_state.load_wan_state(state_path)
    assert state.active_interface == "eth0"
    assert state.status == "ready"
    assert state.message == "eth0 selected"

    # Setting active_interface=None should clear it
    wan_state.update_wan_state(
        active_interface=None,
        status="degraded",
        message="no interface",
        path=state_path,
    )
    state = wan_state.load_wan_state(state_path)
    assert state.active_interface is None
    assert state.status == "degraded"
    assert state.message == "no interface"
