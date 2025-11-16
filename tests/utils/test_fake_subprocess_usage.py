import pytest
from azazel_pi.core.enforcer.traffic_control import TrafficControlEngine
from tests.utils.fake_subprocess import FakeSubprocess


def test_fake_subprocess_injection_applies_dnat_and_records_rule(tmp_path, monkeypatch):
    """Demonstrate injecting a FakeSubprocess runner and exercising apply_dnat_redirect.

    This test does not touch system /var paths because we monkeypatch the nft handles path
    to a temporary location under tmp_path.
    """
    fake = FakeSubprocess()
    # Simulate tc/nft outputs used by TrafficControlEngine during setup and DNAT add
    fake.when("tc qdisc show").then_stdout("")
    fake.when("tc qdisc replace").then_stdout("")
    fake.when("tc class replace").then_stdout("")
    fake.when("tc filter show").then_stdout("")
    fake.when("nft list table").then_stdout("")
    # Simulate nft add with a handle in stdout
    fake.when("nft -a add rule").then_stdout("added rule handle 123")

    # Keep persisted handles in a temp location so test doesn't need root
    monkeypatch.setattr(
        TrafficControlEngine,
        "_diversion_state_path",
        lambda self: tmp_path / "diversions.json",
    )

    # Inject fake runner at class level so __init__ uses it during setup
    TrafficControlEngine._subprocess_runner = fake

    engine = None
    try:
        engine = TrafficControlEngine(config_path=str(tmp_path / "azazel.yaml"))
        ok = engine.apply_dnat_redirect("10.0.5.5", dest_port=2222)
        assert ok is True

        rules = engine.get_active_rules()
        assert "10.0.5.5" in rules
        # Ensure at least one redirect rule recorded
        assert any(r.action_type == "redirect" for r in rules["10.0.5.5"]) is True
    finally:
        # Cleanup injected runner to avoid side effects on other tests
        try:
            delattr(TrafficControlEngine, "_subprocess_runner")
        except Exception:
            pass
