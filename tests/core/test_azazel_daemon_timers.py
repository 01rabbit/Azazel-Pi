import os
import time

from azctl.daemon import AzazelDaemon
from azctl.cli import build_machine
from azazel_pi.core.scorer import ScoreEvaluator


class FakeTrafficEngine:
    def __init__(self):
        self.removed = []
        self.applied = []

    def apply_dnat_redirect(self, ip, dest_port=None):
        return True

    def apply_combined_action(self, ip, mode):
        self.applied.append((ip, mode))
        return True

    def remove_rules_for_ip(self, ip):
        self.removed.append(ip)
        return True

    def cleanup_expired_rules(self, *args, **kwargs):
        return 0


class FakeNotifier:
    def notify_redirect_change(self, ip, endpoints, applied):
        pass


def test_two_stage_canary_suricata_timer(tmp_path):
    # speed up timers via env
    os.environ["AZAZEL_CANARY_SILENCE_SECONDS"] = "1"
    os.environ["AZAZEL_SURICATA_SILENCE_SECONDS"] = "1"

    machine = build_machine()
    daemon = AzazelDaemon(machine=machine, scorer=ScoreEvaluator(), traffic_engine=FakeTrafficEngine(), notifier=FakeNotifier())

    ip = "192.0.2.55"
    # simulate a diversion already applied
    daemon._diverted_ips[ip] = time.time()
    # simulate last canary seen long ago
    daemon._ip_states[ip] = {"last_canary_ts": time.time() - 5}

    # wait for monitor to detect and remove
    max_wait = 5
    start = time.time()
    found_removed = False
    while time.time() - start < max_wait:
        if ip in daemon._ip_states:
            # check if removal has been recorded by fake engine
            if ip in daemon.traffic_engine.removed:
                found_removed = True
                break
        else:
            # ip state already purged
            found_removed = True
            break
        time.sleep(0.2)

    # stop monitor
    daemon._stop_ip_state_monitor()

    assert found_removed, "Expected IP to be removed by two-stage monitor"
