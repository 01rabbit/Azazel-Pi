import json

from azazel_pi.monitor.main_suricata import parse_alert


def test_parse_alert_accepts_et_malware():
    line = json.dumps({
        "event_type": "alert",
        "timestamp": "2025-11-04T12:00:00Z",
        "src_ip": "1.2.3.4",
        "dest_ip": "5.6.7.8",
        "proto": "TCP",
        "dest_port": 8080,
        "alert": {
            "signature": "ET MALWARE Trojan.Gen C2 Communication",
            "severity": 1,
            "metadata": {}
        }
    })
    parsed = parse_alert(line)
    assert parsed is not None
    assert parsed["signature"].startswith("ET MALWARE")


def test_parse_alert_accepts_web_specific_apps():
    line = json.dumps({
        "event_type": "alert",
        "timestamp": "2025-11-04T12:00:01Z",
        "src_ip": "1.2.3.4",
        "dest_ip": "5.6.7.8",
        "proto": "TCP",
        "dest_port": 80,
        "alert": {
            "signature": "ET WEB_SPECIFIC_APPS SQL Injection Attack",
            "severity": 1,
            "metadata": {}
        }
    })
    parsed = parse_alert(line)
    assert parsed is not None
    assert "SQL Injection" in parsed["signature"]
