from azazel_edge.core import notify_config
from azazel_edge.core.notify import MattermostNotifier, NtfyNotifier


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


def test_ntfy_notifier_builds_headers_and_posts(monkeypatch, tmp_path):
    token_file = tmp_path / "ntfy.token"
    token_file.write_text("tk_testtoken", encoding="utf-8")
    notify_config._CFG.setdefault("notify", {})
    notify_config._CFG["notify"]["ntfy"] = {
        "enabled": True,
        "base_url": "http://127.0.0.1:8081",
        "token_file": str(token_file),
        "topic_alert": "azg-alert-critical",
        "topic_info": "azg-info-status",
        "cooldown_sec": 1,
        "timeout_seconds": 1.0,
    }

    notifier = NtfyNotifier()
    assert notifier.enabled is True

    captured = {}

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def getcode(self):
            return 200

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["timeout"] = timeout
        captured["body"] = req.data.decode("utf-8")
        return DummyResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    alert = {
        "signature": "ET NTFY TEST",
        "severity": 2,
        "src_ip": "10.1.1.1",
        "dest_ip": "10.0.0.5",
        "proto": "TCP",
        "dest_port": 443,
    }

    assert notifier.notify_threat_detected(alert) is True
    assert captured["url"] == "http://127.0.0.1:8081/azg-alert-critical"
    assert "authorization" in {k.lower() for k in captured["headers"].keys()}
    assert "ET NTFY TEST" in captured["body"]
