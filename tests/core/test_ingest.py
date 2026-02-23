from pathlib import Path

from azazel_edge.core.ingest import CanaryTail, SuricataTail


def test_suricata_tail_includes_metadata(tmp_path: Path):
    path = tmp_path / "eve.json"
    path.write_text(
        '{"event_type": "alert", "timestamp": "2024-01-01T00:00:00Z",'
        ' "src_ip": "1.2.3.4", "dest_ip": "10.0.0.5", "proto": "TCP", "dest_port": 22,'
        ' "alert": {"severity": 2, "signature": "ET DOS TEST"}}\n'
    )
    tail = SuricataTail(path=path, skip_existing=False)
    event = next(tail.stream())
    assert event.severity == 2
    assert event.src_ip == "1.2.3.4"
    assert event.dest_ip == "10.0.0.5"
    assert event.proto == "TCP"
    assert event.dest_port == 22
    assert event.signature == "ET DOS TEST"
    assert event.timestamp == "2024-01-01T00:00:00Z"


def test_canary_tail(tmp_path: Path):
    path = tmp_path / "canary.log"
    path.write_text('{"logtype": "login"}\n')
    tail = CanaryTail(path=path)
    events = list(tail.stream())
    assert events[0].name == "login"
