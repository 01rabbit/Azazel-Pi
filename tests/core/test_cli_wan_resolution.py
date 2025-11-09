import json
from types import SimpleNamespace

import azctl.cli as cli


def test_status_uses_helper_when_no_wan_if(monkeypatch, capsys):
    # Arrange: patch helper to return a distinctive interface
    # CLI module imports the helper at module import time; patch the symbol in the cli module
    monkeypatch.setattr(cli, "get_active_wan_interface", lambda: "eth99")

    captured = {}

    def fake_cmd_status(decisions, output_json, lan_if, wan_if):
        captured['wan_if'] = wan_if
        return 0

    monkeypatch.setattr(cli, "cmd_status", fake_cmd_status)

    # Act
    rc = cli.main(["status", "--lan-if", "wlan0", "--json"]) 

    # Assert
    assert rc == 0
    assert captured.get('wan_if') == "eth99"


def test_menu_uses_helper_when_no_wan_if(monkeypatch):
    monkeypatch.setattr(cli, "get_active_wan_interface", lambda: "ethX")

    captured = {}

    def fake_cmd_menu(decisions, lan_if, wan_if):
        captured['wan_if'] = wan_if
        return 0

    monkeypatch.setattr(cli, "cmd_menu", fake_cmd_menu)

    rc = cli.main(["menu", "--lan-if", "wlan0"]) 

    assert rc == 0
    assert captured.get('wan_if') == "ethX"


def test_serve_uses_helper_when_no_wan_if(monkeypatch):
    monkeypatch.setattr(cli, "get_active_wan_interface", lambda: "ethSERVE")

    captured = {}

    def fake_cmd_serve(config, decisions, suricata_eve, lan_if, wan_if):
        captured['wan_if'] = wan_if
        return 0

    monkeypatch.setattr(cli, "cmd_serve", fake_cmd_serve)

    rc = cli.main(["serve", "--lan-if", "wlan0"]) 

    assert rc == 0
    assert captured.get('wan_if') == "ethSERVE"
