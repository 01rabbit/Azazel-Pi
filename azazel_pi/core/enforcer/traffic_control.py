#!/usr/bin/env python3
# coding: utf-8
"""
統合トラフィック制御システム
DNAT転送、tc遅延、QoS制御を統合管理
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import yaml

# 統合システムでは actions モジュールは使用しない（直接tc/nftコマンド実行）
from ...utils.delay_action import (
    load_opencanary_ip, ensure_nft_table_and_chain, 
    list_active_diversions, OPENCANARY_IP
)

# ログ設定
try:
    logger = logging.getLogger(__name__)
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
except Exception:
    import sys
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


@dataclass
class TrafficControlRule:
    """トラフィック制御ルールの統合表現"""
    target_ip: str
    action_type: str  # 'delay', 'shape', 'block', 'redirect'
    parameters: Dict[str, any]
    interface: str = "wlan1"
    handle_id: Optional[str] = None
    created_at: float = 0.0
    
    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()


class TrafficControlEngine:
    """統合トラフィック制御エンジン"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "/home/azazel/Azazel-Pi/configs/network/azazel.yaml"
        self.interface = "wlan1"
        self.active_rules: Dict[str, List[TrafficControlRule]] = {}
        self._ensure_tc_setup()
        
    def _load_config(self) -> Dict:
        """設定ファイルを読み込み"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Config load failed: {e}")
            return {}
    
    def _ensure_tc_setup(self):
        """tc qdisc/class構造を初期化"""
        try:
            # 既存のqdisc削除
            subprocess.run([
                "tc", "qdisc", "del", "dev", self.interface, "root"
            ], capture_output=True, timeout=10)
            
            # HTB qdisc作成
            subprocess.run([
                "tc", "qdisc", "add", "dev", self.interface, "root", 
                "handle", "1:", "htb", "default", "30"
            ], check=True, timeout=10)
            
            # ルートクラス作成
            config = self._load_config()
            uplink = config.get("profiles", {}).get("lte", {}).get("uplink_kbps", 5000)
            
            subprocess.run([
                "tc", "class", "add", "dev", self.interface, "parent", "1:", 
                "classid", "1:1", "htb", "rate", f"{uplink}kbit"
            ], check=True, timeout=10)
            
            # デフォルトクラス
            subprocess.run([
                "tc", "class", "add", "dev", self.interface, "parent", "1:1", 
                "classid", "1:30", "htb", "rate", f"{uplink//2}kbit", 
                "ceil", f"{uplink}kbit"
            ], check=True, timeout=10)
            
            # suspectクラス（低優先度）
            suspect_rate = uplink // 10  # 10%
            subprocess.run([
                "tc", "class", "add", "dev", self.interface, "parent", "1:1", 
                "classid", "1:40", "htb", "rate", f"{suspect_rate}kbit", 
                "ceil", f"{suspect_rate * 2}kbit", "prio", "4"
            ], check=True, timeout=10)
            
            logger.info(f"TC setup completed for {self.interface}")
            
        except Exception as e:
            logger.error(f"TC setup failed: {e}")
    
    def apply_delay(self, target_ip: str, delay_ms: int) -> bool:
        """指定IPに遅延を適用"""
        try:
            # netem遅延qdisc作成
            classid = "1:41"  # 遅延専用クラス
            
            # 遅延クラス作成
            subprocess.run([
                "tc", "class", "add", "dev", self.interface, "parent", "1:1",
                "classid", classid, "htb", "rate", "64kbit", "ceil", "128kbit"
            ], check=True, timeout=10)
            
            # netem遅延qdisc追加
            subprocess.run([
                "tc", "qdisc", "add", "dev", self.interface, "parent", classid, 
                "handle", "41:", "netem", "delay", f"{delay_ms}ms"
            ], check=True, timeout=10)
            
            # フィルタ作成（IPベース）
            subprocess.run([
                "tc", "filter", "add", "dev", self.interface, "protocol", "ip",
                "parent", "1:", "prio", "1", "u32", "match", "ip", "src", target_ip,
                "flowid", classid
            ], check=True, timeout=10)
            
            # ルール記録
            rule = TrafficControlRule(
                target_ip=target_ip,
                action_type="delay", 
                parameters={"delay_ms": delay_ms, "classid": classid}
            )
            
            if target_ip not in self.active_rules:
                self.active_rules[target_ip] = []
            self.active_rules[target_ip].append(rule)
            
            logger.info(f"Delay {delay_ms}ms applied to {target_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply delay to {target_ip}: {e}")
            return False
    
    def apply_shaping(self, target_ip: str, rate_kbps: int) -> bool:
        """指定IPに帯域制限を適用"""
        try:
            classid = "1:42"  # シェーピング専用クラス
            
            # シェーピングクラス作成
            subprocess.run([
                "tc", "class", "add", "dev", self.interface, "parent", "1:1",
                "classid", classid, "htb", "rate", f"{rate_kbps}kbit", 
                "ceil", f"{rate_kbps}kbit"
            ], check=True, timeout=10)
            
            # フィルタ作成
            subprocess.run([
                "tc", "filter", "add", "dev", self.interface, "protocol", "ip",
                "parent", "1:", "prio", "2", "u32", "match", "ip", "src", target_ip,
                "flowid", classid
            ], check=True, timeout=10)
            
            # ルール記録
            rule = TrafficControlRule(
                target_ip=target_ip,
                action_type="shape",
                parameters={"rate_kbps": rate_kbps, "classid": classid}
            )
            
            if target_ip not in self.active_rules:
                self.active_rules[target_ip] = []
            self.active_rules[target_ip].append(rule)
            
            logger.info(f"Shaping {rate_kbps}kbps applied to {target_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply shaping to {target_ip}: {e}")
            return False
    
    def apply_dnat_redirect(self, target_ip: str, dest_port: Optional[int] = None) -> bool:
        """指定IPをOpenCanaryにDNAT転送"""
        try:
            canary_ip = load_opencanary_ip()
            
            # nftablesテーブル確保
            if not ensure_nft_table_and_chain():
                return False
            
            # DNATルール構築
            if dest_port:
                rule_match = f"ip saddr {target_ip} tcp dport {dest_port}"
                rule_action = f"dnat to {canary_ip}:{dest_port}"
            else:
                rule_match = f"ip saddr {target_ip}"
                rule_action = f"dnat to {canary_ip}"
            
            # nftables DNAT ルール追加
            cmd = [
                "nft", "add", "rule", "inet", "azazel", "prerouting",
                rule_match, rule_action
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                # ルール記録
                rule = TrafficControlRule(
                    target_ip=target_ip,
                    action_type="redirect",
                    parameters={"canary_ip": canary_ip, "dest_port": dest_port}
                )
                
                if target_ip not in self.active_rules:
                    self.active_rules[target_ip] = []
                self.active_rules[target_ip].append(rule)
                
                logger.info(f"DNAT redirect: {target_ip} -> {canary_ip}" +
                           (f":{dest_port}" if dest_port else ""))
                return True
            else:
                logger.error(f"nft DNAT failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to apply DNAT redirect to {target_ip}: {e}")
            return False
    
    def apply_suspect_classification(self, target_ip: str) -> bool:
        """攻撃者IPをsuspectクラスに分類（低優先度・低帯域）"""
        try:
            classid = "1:40"  # suspect クラス（既にsetupで作成済み）
            
            # フィルタ作成（全トラフィックをsuspectクラスに）
            subprocess.run([
                "tc", "filter", "add", "dev", self.interface, "protocol", "ip",
                "parent", "1:", "prio", "4", "u32", "match", "ip", "src", target_ip,
                "flowid", classid
            ], check=True, timeout=10)
            
            # ルール記録
            rule = TrafficControlRule(
                target_ip=target_ip,
                action_type="suspect_qos",
                parameters={"classid": classid, "priority": 4}
            )
            
            if target_ip not in self.active_rules:
                self.active_rules[target_ip] = []
            self.active_rules[target_ip].append(rule)
            
            logger.info(f"Suspect classification applied to {target_ip} (low priority/bandwidth)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply suspect classification to {target_ip}: {e}")
            return False

    def apply_combined_action(self, target_ip: str, mode: str) -> bool:
        """モードに応じた複合アクションを適用"""
        config = self._load_config()
        actions = config.get("actions", {})
        preset = actions.get(mode, {})
        
        if not preset:
            logger.warning(f"No action preset for mode: {mode}")
            return False
        
        success = True
        
        # DNAT転送適用
        if not self.apply_dnat_redirect(target_ip):
            success = False
        
        # suspectクラス分類適用（常に適用）
        if not self.apply_suspect_classification(target_ip):
            success = False
        
        # 遅延適用
        delay_ms = preset.get("delay_ms", 0)
        if delay_ms > 0:
            if not self.apply_delay(target_ip, delay_ms):
                success = False
        
        # 帯域制限適用
        shape_kbps = preset.get("shape_kbps")
        if shape_kbps and shape_kbps > 0:
            if not self.apply_shaping(target_ip, shape_kbps):
                success = False
        
        if success:
            logger.info(f"Combined action applied: {target_ip} -> {mode} (DNAT+Suspect+Delay+Shape)")
        else:
            logger.error(f"Partial failure in combined action: {target_ip} -> {mode}")
        
        return success
    
    def remove_rules_for_ip(self, target_ip: str) -> bool:
        """指定IPの全制御ルールを削除"""
        if target_ip not in self.active_rules:
            logger.info(f"No active rules for {target_ip}")
            return True
        
        success = True
        
        for rule in self.active_rules[target_ip]:
            try:
                if rule.action_type in ["delay", "shape"]:
                    # tcルール削除（個別クラス）
                    classid = rule.parameters.get("classid")
                    if classid and classid not in ["1:40"]:  # suspectクラスではない場合のみ削除
                        # フィルタ削除
                        subprocess.run([
                            "tc", "filter", "del", "dev", self.interface, 
                            "protocol", "ip", "parent", "1:", "prio", "1"
                        ], capture_output=True, timeout=10)
                        
                        # クラス削除
                        subprocess.run([
                            "tc", "class", "del", "dev", self.interface, 
                            "classid", classid
                        ], capture_output=True, timeout=10)
                
                elif rule.action_type == "suspect_qos":
                    # suspectクラスフィルタ削除
                    subprocess.run([
                        "tc", "filter", "del", "dev", self.interface,
                        "protocol", "ip", "parent", "1:", "prio", "4"
                    ], capture_output=True, timeout=10)
                        
                elif rule.action_type == "redirect":
                    # nftables DNAT削除
                    self._remove_nft_dnat_rule(target_ip, rule.parameters.get("dest_port"))
                
            except Exception as e:
                logger.error(f"Failed to remove rule {rule.action_type} for {target_ip}: {e}")
                success = False
        
        # アクティブルールリストから削除
        del self.active_rules[target_ip]
        
        logger.info(f"All rules removed for {target_ip}")
        return success
    
    def _remove_nft_dnat_rule(self, target_ip: str, dest_port: Optional[int] = None) -> bool:
        """nftables DNATルールを削除"""
        try:
            if dest_port:
                search_pattern = f"ip saddr {target_ip} tcp dport {dest_port}"
            else:
                search_pattern = f"ip saddr {target_ip}"
            
            # ルール一覧取得
            result = subprocess.run([
                "nft", "-a", "list", "table", "inet", "azazel"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return False
            
            # 該当ルールのハンドルを探す
            for line in result.stdout.split('\n'):
                if search_pattern in line and "handle" in line:
                    handle = line.split("handle")[-1].strip()
                    if handle.isdigit():
                        # ルール削除
                        delete_cmd = [
                            "nft", "delete", "rule", "inet", "azazel", "prerouting", 
                            "handle", handle
                        ]
                        subprocess.run(delete_cmd, capture_output=True, timeout=10)
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to remove nft DNAT rule: {e}")
            return False
    
    def cleanup_expired_rules(self, max_age_seconds: int = 3600) -> int:
        """期限切れルールをクリーンアップ"""
        current_time = time.time()
        cleaned_count = 0
        
        expired_ips = []
        for ip, rules in self.active_rules.items():
            oldest_rule = min(rules, key=lambda r: r.created_at)
            if current_time - oldest_rule.created_at > max_age_seconds:
                expired_ips.append(ip)
        
        for ip in expired_ips:
            if self.remove_rules_for_ip(ip):
                cleaned_count += 1
        
        logger.info(f"Cleaned up {cleaned_count} expired rule sets")
        return cleaned_count
    
    def get_active_rules(self) -> Dict[str, List[TrafficControlRule]]:
        """現在アクティブなルール一覧を取得"""
        return self.active_rules.copy()
    
    def get_stats(self) -> Dict[str, any]:
        """統計情報を取得"""
        total_rules = sum(len(rules) for rules in self.active_rules.values())
        
        return {
            "active_ips": len(self.active_rules),
            "total_rules": total_rules,
            "interface": self.interface,
            "nft_diversions": len(list_active_diversions()),
            "uptime": time.time() - getattr(self, '_start_time', time.time())
        }


# シングルトンインスタンス
_traffic_control_engine = None

def get_traffic_control_engine() -> TrafficControlEngine:
    """トラフィック制御エンジンのシングルトンインスタンスを取得"""
    global _traffic_control_engine
    if _traffic_control_engine is None:
        _traffic_control_engine = TrafficControlEngine()
        _traffic_control_engine._start_time = time.time()
    return _traffic_control_engine


if __name__ == "__main__":
    # テスト実行
    engine = get_traffic_control_engine()
    
    test_ip = "192.168.1.200"
    
    print("Testing combined shield mode action...")
    if engine.apply_combined_action(test_ip, "shield"):
        print("✓ Shield mode applied successfully")
        
        stats = engine.get_stats()
        print(f"Stats: {stats}")
        
        time.sleep(2)
        
        if engine.remove_rules_for_ip(test_ip):
            print("✓ Rules removed successfully")
        else:
            print("✗ Failed to remove rules")
    else:
        print("✗ Failed to apply shield mode")