from types import SimpleNamespace

from azctl.daemon import AzazelDaemon
from azazel_edge.core.scorer import ScoreEvaluator
from azazel_edge.core.state_machine import Event


class DummyMachine:
    def __init__(self):
        self.current_state = SimpleNamespace(name="normal", description="")

    def apply_score(self, score: int):
        mode = "lockdown" if score >= 80 else "normal"
        self.current_state = SimpleNamespace(name=mode, description="")
        return {
            "average": score,
            "desired_mode": mode,
            "target_mode": mode,
            "applied_mode": mode,
        }

    def get_actions_preset(self):
        return {"delay_ms": 0}


class DummyTrafficEngine:
    def __init__(self):
        self.applied = []
        self.removed = []
        self.cleanup_called = False
        self.diverted = []

    def apply_combined_action(self, ip: str, mode: str):
        self.applied.append((ip, mode))
        return True

    def apply_dnat_redirect(self, ip: str, dest_port=None):
        self.diverted.append((ip, dest_port))
        return True

    def remove_rules_for_ip(self, ip: str):
        self.removed.append(ip)
        return True

    def cleanup_expired_rules(self):
        self.cleanup_called = True
        return 0


class DummyNotifier:
    def __init__(self):
        self.threats = []
        self.redirects = []
        self.modes = []

    def notify_threat_detected(self, payload):
        self.threats.append(payload)
        return True

    def notify_redirect_change(self, target_ip, endpoints, applied):
        self.redirects.append({"ip": target_ip, "endpoints": endpoints, "applied": applied})
        return True

    def notify_mode_change(self, previous, current, average):
        self.modes.append({"previous": previous, "current": current, "average": average})
        return True


def test_daemon_controls_and_notifies(monkeypatch):
    machine = DummyMachine()
    traffic = DummyTrafficEngine()
    notifier = DummyNotifier()
    daemon = AzazelDaemon(machine=machine, scorer=ScoreEvaluator(), traffic_engine=traffic, notifier=notifier)
    daemon._opencanary_endpoints = [{"protocol": "tcp", "port": 2222}]
    daemon._next_cleanup_at = 0.0

    monkeypatch.setattr(
        "azctl.daemon.evaluate_with_hybrid_system",
        lambda alert: {"score": 90, "category": "critical"},
    )

    event = Event(name="alert", severity=2, src_ip="5.5.5.5", dest_ip="10.0.0.1", signature="SIG")
    daemon.process_event(event)

    assert traffic.diverted == [("5.5.5.5", None)]
    assert traffic.applied == [("5.5.5.5", "lockdown")]
    assert notifier.redirects[-1]["applied"] is True
    assert notifier.threats[-1]["src_ip"] == "5.5.5.5"
    assert notifier.modes[-1]["current"] == "lockdown"
    assert traffic.cleanup_called is True

    monkeypatch.setattr(
        "azctl.daemon.evaluate_with_hybrid_system",
        lambda alert: {"score": 0, "category": "benign"},
    )
    daemon.process_event(event)

    assert traffic.removed == ["5.5.5.5"]
    assert notifier.redirects[-1]["applied"] is False
