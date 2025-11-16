import json
from pathlib import Path
import tempfile

from azazel_pi.core.ingest.canary_tail import CanaryTail


def test_canary_tail_reads_existing_lines(tmp_path: Path):
    p = tmp_path / "opencanary.log"
    records = [
        {"timestamp": "2025-11-16T00:00:00Z", "src_ip": "192.0.2.1", "msg": "hit"},
        {"timestamp": "2025-11-16T00:00:01Z", "src_ip": "192.0.2.2", "msg": "hit2"},
    ]
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    tail = CanaryTail(path=p, skip_existing=False)
    gen = tail.stream()

    ev1 = next(gen)
    assert ev1.name == "canary"
    assert ev1.src_ip == "192.0.2.1"

    ev2 = next(gen)
    assert ev2.name == "canary"
    assert ev2.src_ip == "192.0.2.2"
