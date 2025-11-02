"""Test configuration and fixtures."""
import os
import tempfile
from pathlib import Path
import pytest
import yaml

@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_dir = os.getcwd()
        os.chdir(tmpdir)
        yield Path(tmpdir)
        os.chdir(old_dir)

@pytest.fixture
def mock_notify_yaml(temp_config_dir):
    """Create a mock notify.yaml for testing."""
    config = {
        "mattermost": {
            "webhook_url": "http://mock.example.com/hooks/test",
            "channel": "test-channel",
            "username": "test-bot",
        },
        "paths": {
            "events": "/tmp/events.json",
            "suricata_eve": "/tmp/eve.json",
        },
        "network": {
            "interface": "test0",
            "delay": {"base_ms": 100},
        },
    }
    
    config_dir = temp_config_dir / "configs" / "monitoring"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "notify.yaml"
    
    with config_file.open("w") as f:
        yaml.safe_dump(config, f)
    
    return config_file

@pytest.fixture
def mock_azazel_yaml(temp_config_dir):
    """Create a mock azazel.yaml for testing."""
    config = {
        "node": "test-node-01",
        "interfaces": {"lan": "lan0", "wan": "wan0"},
        "thresholds": {
            "t1_shield": 50,
            "t2_lockdown": 80,
            "unlock_wait_secs": {"shield": 600, "portal": 1800},
        },
        "actions": {
            "portal": {"delay_ms": 100},
            "shield": {"delay_ms": 100},
            "lockdown": {"delay_ms": 300, "shape_kbps": 64, "block": True},
        },
    }
    
    # Place at configs/azazel.yaml (state_machine expects this path)
    config_dir = temp_config_dir / "configs"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "azazel.yaml"
    
    with config_file.open("w") as f:
        yaml.safe_dump(config, f)
    
    return config_file