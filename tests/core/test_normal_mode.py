"""
Normal mode implementation tests
仕様書セクション8に基づくテスト実装
"""
import pytest
from azazel_edge.core.state_machine import StateMachine
from azazel_edge.core.enforcer.traffic_control import TrafficControlEngine


class TestNormalModeStateMachine:
    """状態機械のnormalモード境界値テスト"""
    
    def test_boundary_normal_to_portal(self, tmp_path):
        """境界値テスト: score=19→normal, score=20→portal"""
        # 一時設定ファイル作成
        config_file = tmp_path / "azazel.yaml"
        config_file.write_text("""
thresholds:
  t0_normal: 20
  t1_shield: 50
  t2_lockdown: 80
actions:
  normal: { delay_ms: 0, shape_kbps: null, block: false }
  portal: { delay_ms: 100, shape_kbps: 1000, block: false }
  shield: { delay_ms: 500, shape_kbps: 500, block: false }
  lockdown: { delay_ms: 0, shape_kbps: null, block: true }
time_window: 300
mode: state_machine
soc:
  denylist_ips: []
  critical_signatures: []
""")
        
        from azazel_edge.core.state_machine import State
        
        # score=19 → normal (新しいインスタンス)
        sm1 = StateMachine(
            initial_state=State("normal_state", "Normal Mode"),
            config_path=str(config_file)
        )
        sm1.reload_config()
        result = sm1.evaluate_window(19.0)
        assert result["desired_mode"] == "normal", f"Expected 'normal' for score=19, got '{result['desired_mode']}'"
        
        # score=20 → portal (新しいインスタンス)
        sm2 = StateMachine(
            initial_state=State("normal_state", "Normal Mode"),
            config_path=str(config_file)
        )
        sm2.reload_config()
        result = sm2.evaluate_window(20.0)
        assert result["desired_mode"] == "portal", f"Expected 'portal' for score=20, got '{result['desired_mode']}'"
    
    def test_boundary_portal_to_shield(self, tmp_path):
        """境界値テスト: score=49→portal, score=50→shield"""
        config_file = tmp_path / "azazel.yaml"
        config_file.write_text("""
thresholds:
  t0_normal: 20
  t1_shield: 50
  t2_lockdown: 80
actions:
  normal: { delay_ms: 0, shape_kbps: null, block: false }
  portal: { delay_ms: 100, shape_kbps: 1000, block: false }
  shield: { delay_ms: 500, shape_kbps: 500, block: false }
  lockdown: { delay_ms: 0, shape_kbps: null, block: true }
time_window: 300
mode: state_machine
soc:
  denylist_ips: []
  critical_signatures: []
""")
        
        from azazel_edge.core.state_machine import State
        
        # score=49 → portal (新しいインスタンス)
        sm1 = StateMachine(
            initial_state=State("normal_state", "Normal Mode"),
            config_path=str(config_file)
        )
        sm1.reload_config()
        result = sm1.evaluate_window(49.0)
        assert result["desired_mode"] == "portal", f"Expected 'portal' for score=49, got '{result['desired_mode']}'"
        
        # score=50 → shield (新しいインスタンス)
        sm2 = StateMachine(
            initial_state=State("normal_state", "Normal Mode"),
            config_path=str(config_file)
        )
        sm2.reload_config()
        result = sm2.evaluate_window(50.0)
        assert result["desired_mode"] == "shield", f"Expected 'shield' for score=50, got '{result['desired_mode']}'"
    
    def test_boundary_shield_to_lockdown(self, tmp_path):
        """境界値テスト: score=79→shield, score=80→lockdown"""
        config_file = tmp_path / "azazel.yaml"
        config_file.write_text("""
thresholds:
  t0_normal: 20
  t1_shield: 50
  t2_lockdown: 80
actions:
  normal: { delay_ms: 0, shape_kbps: null, block: false }
  portal: { delay_ms: 100, shape_kbps: 1000, block: false }
  shield: { delay_ms: 500, shape_kbps: 500, block: false }
  lockdown: { delay_ms: 0, shape_kbps: null, block: true }
time_window: 300
mode: state_machine
soc:
  denylist_ips: []
  critical_signatures: []
""")
        
        from azazel_edge.core.state_machine import State
        
        # score=79 → shield (新しいインスタンス)
        sm1 = StateMachine(
            initial_state=State("normal_state", "Normal Mode"),
            config_path=str(config_file)
        )
        sm1.reload_config()
        result = sm1.evaluate_window(79.0)
        assert result["desired_mode"] == "shield", f"Expected 'shield' for score=79, got '{result['desired_mode']}'"
        
        # score=80 → lockdown (新しいインスタンス)
        sm2 = StateMachine(
            initial_state=State("normal_state", "Normal Mode"),
            config_path=str(config_file)
        )
        sm2.reload_config()
        result = sm2.evaluate_window(80.0)
        assert result["desired_mode"] == "lockdown", f"Expected 'lockdown' for score=80, got '{result['desired_mode']}'"


class TestNormalModeTransitions:
    """normalモードへの遷移テスト"""
    
    def test_direct_transition_to_normal(self, tmp_path):
        """直接遷移テスト: portal→normal, shield→normal, lockdown→normal"""
        config_file = tmp_path / "azazel.yaml"
        config_file.write_text("""
thresholds:
  t0_normal: 20
  t1_shield: 50
  t2_lockdown: 80
actions:
  normal: { delay_ms: 0, shape_kbps: null, block: false }
  portal: { delay_ms: 100, shape_kbps: 1000, block: false }
  shield: { delay_ms: 500, shape_kbps: 500, block: false }
  lockdown: { delay_ms: 0, shape_kbps: null, block: true }
time_window: 300
mode: state_machine
soc:
  denylist_ips: []
  critical_signatures: []
""")
        
        from azazel_edge.core.state_machine import State
        sm = StateMachine(
            initial_state=State("normal_state", "Normal Mode"),
            config_path=str(config_file)
        )
        
        # portal → normal
        sm.current_state = State("portal_state", "Portal Mode")
        result = sm.evaluate_window(15.0)  # score < 20
        assert result["desired_mode"] == "normal", f"Expected 'normal' from portal, got '{result['desired_mode']}'"
        
        # shield → normal
        sm.current_state = State("shield_state", "Shield Mode")
        result = sm.evaluate_window(10.0)
        assert result["desired_mode"] == "normal", f"Expected 'normal' from shield, got '{result['desired_mode']}'"
        
        # lockdown → normal
        sm.current_state = State("lockdown_state", "Lockdown Mode")
        result = sm.evaluate_window(5.0)
        assert result["desired_mode"] == "normal", f"Expected 'normal' from lockdown, got '{result['desired_mode']}'"


class TestExceptionBlocking:
    """例外遮断機能のテスト"""
    
    def test_denylist_detection(self):
        """Denylist IPの検出テスト"""
        from azazel_edge.monitor.main_suricata import check_exception_block
        from azazel_edge.monitor import main_suricata
        
        # Denylist IPを設定（モジュールレベル変数はset型）
        main_suricata.DENYLIST_IPS.clear()
        main_suricata.DENYLIST_IPS.update(["192.168.1.100", "10.0.0.50"])
        
        alert = {
            "src_ip": "192.168.1.100",
            "signature": "Benign Traffic"
        }
        
        assert check_exception_block(alert) == True, "Denylist IP should trigger exception block"
    
    def test_critical_signature_detection(self):
        """Critical signatureの検出テスト"""
        from azazel_edge.monitor.main_suricata import check_exception_block
        from azazel_edge.monitor import main_suricata
        
        # Critical signaturesを設定（list型なので再代入）
        main_suricata.CRITICAL_SIGNATURES.clear()
        main_suricata.CRITICAL_SIGNATURES.extend(["ET EXPLOIT", "ET MALWARE"])
        
        alert = {
            "src_ip": "192.168.1.50",
            "signature": "ET EXPLOIT SQL Injection Attempt"
        }
        
        assert check_exception_block(alert) == True, "Critical signature should trigger exception block"
    
    def test_no_exception_for_benign(self):
        """通常トラフィックは例外遮断しないことを確認"""
        from azazel_edge.monitor.main_suricata import check_exception_block
        from azazel_edge.monitor import main_suricata
        
        main_suricata.DENYLIST_IPS.clear()
        main_suricata.CRITICAL_SIGNATURES.clear()
        main_suricata.CRITICAL_SIGNATURES.extend(["ET EXPLOIT", "ET MALWARE"])
        
        alert = {
            "src_ip": "192.168.1.200",
            "signature": "HTTP Request to /api/data"
        }
        
        assert check_exception_block(alert) == False, "Benign traffic should not trigger exception block"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
