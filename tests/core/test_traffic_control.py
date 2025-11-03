#!/usr/bin/env python3
# coding: utf-8
"""
統合トラフィック制御システムのテスト
"""

import pytest
import time
from unittest.mock import Mock, patch, call
from azazel_pi.core.enforcer.traffic_control import (
    TrafficControlEngine, TrafficControlRule, get_traffic_control_engine
)


@pytest.fixture
def traffic_engine():
    """テスト用トラフィック制御エンジン"""
    with patch('azazel_pi.core.enforcer.traffic_control.subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)
        engine = TrafficControlEngine()
        return engine


def test_traffic_control_rule_creation():
    """TrafficControlRuleの生成テスト"""
    rule = TrafficControlRule(
        target_ip="192.168.1.100",
        action_type="delay",
        parameters={"delay_ms": 200, "classid": "1:41"}
    )
    
    assert rule.target_ip == "192.168.1.100"
    assert rule.action_type == "delay"
    assert rule.parameters["delay_ms"] == 200
    assert rule.interface == "wlan1"
    assert rule.created_at > 0


def test_apply_delay(traffic_engine):
    """遅延適用テスト"""
    with patch('azazel_pi.core.enforcer.traffic_control.subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)
        
        result = traffic_engine.apply_delay("192.168.1.100", 200)
        
        assert result is True
        assert "192.168.1.100" in traffic_engine.active_rules
        rule = traffic_engine.active_rules["192.168.1.100"][0]
        assert rule.action_type == "delay"
        assert rule.parameters["delay_ms"] == 200


def test_apply_shaping(traffic_engine):
    """帯域制限適用テスト"""
    with patch('azazel_pi.core.enforcer.traffic_control.subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)
        
        result = traffic_engine.apply_shaping("192.168.1.100", 128)
        
        assert result is True
        assert "192.168.1.100" in traffic_engine.active_rules
        rule = traffic_engine.active_rules["192.168.1.100"][0]
        assert rule.action_type == "shape"
        assert rule.parameters["rate_kbps"] == 128


def test_apply_dnat_redirect(traffic_engine):
    """DNAT転送適用テスト"""
    with patch('azazel_pi.core.enforcer.traffic_control.subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)
        with patch('azazel_pi.core.enforcer.traffic_control.load_opencanary_ip') as mock_load:
            mock_load.return_value = "192.168.1.200"
            with patch('azazel_pi.core.enforcer.traffic_control.ensure_nft_table_and_chain') as mock_ensure:
                mock_ensure.return_value = True
                
                result = traffic_engine.apply_dnat_redirect("192.168.1.100", 22)
                
                assert result is True
                assert "192.168.1.100" in traffic_engine.active_rules
                rule = traffic_engine.active_rules["192.168.1.100"][0]
                assert rule.action_type == "redirect"
                assert rule.parameters["dest_port"] == 22


def test_apply_suspect_classification(traffic_engine):
    """suspect分類適用テスト"""
    with patch('azazel_pi.core.enforcer.traffic_control.subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)
        
        result = traffic_engine.apply_suspect_classification("192.168.1.100")
        
        assert result is True
        assert "192.168.1.100" in traffic_engine.active_rules
        rule = traffic_engine.active_rules["192.168.1.100"][0]
        assert rule.action_type == "suspect_qos"
        assert rule.parameters["classid"] == "1:40"


def test_apply_combined_action_shield(traffic_engine):
    """shield モード複合アクションテスト"""
    with patch('azazel_pi.core.enforcer.traffic_control.subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)
        with patch('azazel_pi.core.enforcer.traffic_control.load_opencanary_ip') as mock_load:
            mock_load.return_value = "192.168.1.200"
            with patch('azazel_pi.core.enforcer.traffic_control.ensure_nft_table_and_chain') as mock_ensure:
                mock_ensure.return_value = True
                
                result = traffic_engine.apply_combined_action("192.168.1.100", "shield")
                
                assert result is True
                assert "192.168.1.100" in traffic_engine.active_rules
                
                # 複数ルールが適用されているか確認
                rules = traffic_engine.active_rules["192.168.1.100"]
                action_types = [rule.action_type for rule in rules]
                assert "redirect" in action_types
                assert "suspect_qos" in action_types
                assert "delay" in action_types
                assert "shape" in action_types


def test_apply_combined_action_lockdown(traffic_engine):
    """lockdown モード複合アクションテスト"""
    with patch('azazel_pi.core.enforcer.traffic_control.subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)
        with patch('azazel_pi.core.enforcer.traffic_control.load_opencanary_ip') as mock_load:
            mock_load.return_value = "192.168.1.200"
            with patch('azazel_pi.core.enforcer.traffic_control.ensure_nft_table_and_chain') as mock_ensure:
                mock_ensure.return_value = True
                
                result = traffic_engine.apply_combined_action("192.168.1.100", "lockdown")
                
                assert result is True
                
                # lockdownモードの設定値確認
                rules = traffic_engine.active_rules["192.168.1.100"]
                delay_rule = [r for r in rules if r.action_type == "delay"][0]
                shape_rule = [r for r in rules if r.action_type == "shape"][0]
                
                assert delay_rule.parameters["delay_ms"] == 300
                assert shape_rule.parameters["rate_kbps"] == 64


def test_remove_rules_for_ip(traffic_engine):
    """IPアドレス別ルール削除テスト"""
    # まずルールを追加
    with patch('azazel_pi.core.enforcer.traffic_control.subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)
        with patch('azazel_pi.core.enforcer.traffic_control.load_opencanary_ip') as mock_load:
            mock_load.return_value = "192.168.1.200"
            with patch('azazel_pi.core.enforcer.traffic_control.ensure_nft_table_and_chain') as mock_ensure:
                mock_ensure.return_value = True
                
                traffic_engine.apply_combined_action("192.168.1.100", "shield")
                assert "192.168.1.100" in traffic_engine.active_rules
                
                # ルール削除
                result = traffic_engine.remove_rules_for_ip("192.168.1.100")
                
                assert result is True
                assert "192.168.1.100" not in traffic_engine.active_rules


def test_cleanup_expired_rules(traffic_engine):
    """期限切れルールクリーンアップテスト"""
    # 古いルールを追加
    old_rule = TrafficControlRule(
        target_ip="192.168.1.100",
        action_type="delay",
        parameters={"delay_ms": 100},
        created_at=time.time() - 7200  # 2時間前
    )
    traffic_engine.active_rules["192.168.1.100"] = [old_rule]
    
    with patch('azazel_pi.core.enforcer.traffic_control.subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)
        
        cleaned_count = traffic_engine.cleanup_expired_rules(max_age_seconds=3600)  # 1時間
        
        assert cleaned_count == 1
        assert "192.168.1.100" not in traffic_engine.active_rules


def test_get_stats(traffic_engine):
    """統計情報取得テスト"""
    # いくつかルール追加
    rule1 = TrafficControlRule("192.168.1.100", "delay", {"delay_ms": 100})
    rule2 = TrafficControlRule("192.168.1.101", "shape", {"rate_kbps": 128})
    
    traffic_engine.active_rules["192.168.1.100"] = [rule1]
    traffic_engine.active_rules["192.168.1.101"] = [rule2]
    
    stats = traffic_engine.get_stats()
    
    assert stats["active_ips"] == 2
    assert stats["total_rules"] == 2
    assert stats["interface"] == "wlan1"
    assert "uptime" in stats


def test_singleton_engine():
    """シングルトンエンジンテスト"""
    with patch('azazel_pi.core.enforcer.traffic_control.subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)
        
        engine1 = get_traffic_control_engine()
        engine2 = get_traffic_control_engine()
        
        assert engine1 is engine2  # 同じインスタンスである


def test_config_loading(traffic_engine):
    """設定ファイル読み込みテスト"""
    with patch('builtins.open', create=True) as mock_open:
        mock_file = Mock()
        mock_file.read.return_value = """
actions:
  shield:
    delay_ms: 200
    shape_kbps: 128
  lockdown:
    delay_ms: 300
    shape_kbps: 64
"""
        mock_open.return_value.__enter__.return_value = mock_file
        
        with patch('yaml.safe_load') as mock_yaml:
            mock_yaml.return_value = {
                "actions": {
                    "shield": {"delay_ms": 200, "shape_kbps": 128},
                    "lockdown": {"delay_ms": 300, "shape_kbps": 64}
                }
            }
            
            config = traffic_engine._load_config()
            
            assert config["actions"]["shield"]["delay_ms"] == 200
            assert config["actions"]["lockdown"]["shape_kbps"] == 64


if __name__ == "__main__":
    pytest.main([__file__, "-v"])