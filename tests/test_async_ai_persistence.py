import time
import json
from pathlib import Path

import azazel_edge.core.async_ai as async_ai
from azazel_edge.core import notify_config


def test_async_ai_persists_deep_result(tmp_path):
    # prepare decisions path
    decisions = tmp_path / "decisions_test.log"

    # stub evaluator
    class DummyEvaluator:
        def evaluate_threat(self, alert):
            return {"risk": 3, "category": "malware", "reason": "dummy", "score": 75}

    # monkeypatch evaluator in module
    async_ai.get_ai_evaluator = lambda: DummyEvaluator()

    # ensure sampling always allows
    notify_config._CFG.setdefault('ai', {})
    notify_config._CFG['ai']['deep_sample_rate'] = 1.0
    notify_config._CFG['ai']['deep_max_per_min'] = 10
    notify_config._CFG['ai']['deep_eval_retries'] = 1
    notify_config._CFG['ai']['deep_persist_retries'] = 1

    # enqueue a test alert
    alert = {"src_ip": "10.0.0.5", "signature": "TEST ALERT", "timestamp": time.time()}
    async_ai.enqueue(alert, context={"decisions_log": str(decisions)})

    # wait for worker to persist
    timeout = 5.0
    start = time.time()
    while time.time() - start < timeout:
        if decisions.exists():
            break
        time.sleep(0.1)

    # signal shutdown and allow worker finish
    async_ai.shutdown()
    time.sleep(0.1)

    assert decisions.exists(), "decisions log was not created"
    with decisions.open("r", encoding="utf-8") as fh:
        lines = [ln.strip() for ln in fh.readlines() if ln.strip()]
    assert len(lines) >= 1
    data = json.loads(lines[-1])
    assert data.get('note') == 'deep_followup'
    assert data.get('deep_ai', {}).get('category') == 'malware'
