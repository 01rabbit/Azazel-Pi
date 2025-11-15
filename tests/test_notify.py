from azazel_pi.core import notify_config
from azazel_pi.core.notify import MattermostNotifier


def test_mattermost_notifier_builds_payload(monkeypatch):
    notify_config._CFG.setdefault("mattermost", {})
    notify_config._CFG["mattermost"]["webhook_url"] = "http://localhost/hooks/test"
    notifier = MattermostNotifier()
    captured = {}

    def fake_send(text, key, payload):
        captured["text"] = text
        captured["key"] = key
        captured["payload"] = payload
        return True

    monkeypatch.setattr(notifier, "_send", fake_send)

    alert = {
        "signature": "ET TEST ALERT",
        "severity": 3,
        "src_ip": "1.2.3.4",
        "dest_ip": "10.0.0.5",
        "proto": "TCP",
        "dest_port": 22,
        "timestamp": "2024-01-01T00:00:00Z",
    }

    assert notifier.notify_threat_detected(alert) is True
    assert captured["payload"]["type"] == "suricata_threat"
    assert captured["payload"]["src_ip"] == "1.2.3.4"
    assert captured["key"].startswith("threat:")
    assert captured["text"].startswith("⚠️ Suricata detected a new threat")
    assert "Signature: ET TEST ALERT" in captured["text"]
    assert "Source IP: 1.2.3.4" in captured["text"]
