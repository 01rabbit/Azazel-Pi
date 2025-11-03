#!/usr/bin/env python3
# coding: utf-8
"""
遅滞行動機能: 不審なトラフィックをOpenCanaryに転送
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

# OpenCanary IP address (デフォルト値、設定ファイルから上書き可能)
OPENCANARY_IP = "192.168.1.100"

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_opencanary_ip() -> str:
    """設定ファイルからOpenCanaryのIPアドレスを読み込む"""
    global OPENCANARY_IP
    
    # 設定ファイルの候補パス
    config_paths = [
        Path("/etc/azazel/azazel.yaml"),
        Path(__file__).parent.parent.parent / "configs" / "network" / "azazel.yaml",
    ]
    
    for config_path in config_paths:
        if config_path.exists():
            try:
                import yaml
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    
                # OpenCanaryのIPアドレス設定を探す
                canary_ip = config.get('canary', {}).get('ip')
                if not canary_ip:
                    # デフォルトでローカルIPレンジの.100を使用
                    canary_ip = "192.168.1.100"
                    
                OPENCANARY_IP = canary_ip
                logger.info(f"OpenCanary IP loaded from config: {OPENCANARY_IP}")
                break
            except Exception as e:
                logger.warning(f"Config load error from {config_path}: {e}")
                continue
    
    return OPENCANARY_IP


def check_nft_table_exists(table_name: str = "azazel") -> bool:
    """nftablesテーブルが存在するかチェック"""
    try:
        result = subprocess.run(
            ["nft", "list", "table", "inet", table_name],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Failed to check nft table: {e}")
        return False


def ensure_nft_table_and_chain():
    """必要なnftablesテーブルとチェーンを作成"""
    try:
        # テーブル作成（既存の場合は無視）
        subprocess.run(
            ["nft", "add", "table", "inet", "azazel"],
            capture_output=True, timeout=10
        )
        
        # DNATチェーン作成
        subprocess.run([
            "nft", "add", "chain", "inet", "azazel", "prerouting",
            "{ type nat hook prerouting priority -100; }"
        ], capture_output=True, timeout=10)
        
        logger.info("nftables table and chain ensured")
        return True
        
    except Exception as e:
        logger.error(f"Failed to ensure nft table/chain: {e}")
        return False


def divert_to_opencanary(src_ip: str, dest_port: Optional[int] = None) -> bool:
    """
    指定されたIPアドレスからのトラフィックをOpenCanaryに転送
    
    Args:
        src_ip: 転送対象の送信元IPアドレス
        dest_port: 対象ポート（指定しない場合は全ポート）
        
    Returns:
        bool: 転送ルール追加の成功/失敗
    """
    if not src_ip:
        logger.error("Source IP is required")
        return False
    
    # OpenCanary IPを読み込み
    canary_ip = load_opencanary_ip()
    
    # nftablesテーブル/チェーンを確保
    if not ensure_nft_table_and_chain():
        return False
    
    try:
        # DNATルールを構築
        if dest_port:
            # 特定ポートのみ転送
            rule_match = f"ip saddr {src_ip} tcp dport {dest_port}"
            rule_action = f"dnat to {canary_ip}:{dest_port}"
        else:
            # 全ポート転送
            rule_match = f"ip saddr {src_ip}"
            rule_action = f"dnat to {canary_ip}"
        
        # nftables DNAT ルール追加
        cmd = [
            "nft", "add", "rule", "inet", "azazel", "prerouting",
            rule_match, rule_action
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        
        if result.returncode == 0:
            logger.info(f"DNAT rule added: {src_ip} -> {canary_ip}" + 
                       (f":{dest_port}" if dest_port else ""))
            return True
        else:
            logger.error(f"nft rule add failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("nft command timeout")
        return False
    except Exception as e:
        logger.error(f"Failed to add DNAT rule: {e}")
        return False


def remove_divert_rule(src_ip: str, dest_port: Optional[int] = None) -> bool:
    """
    指定されたIPアドレスの転送ルールを削除
    
    Args:
        src_ip: 削除対象の送信元IPアドレス
        dest_port: 対象ポート（指定しない場合は全ポート）
        
    Returns:
        bool: ルール削除の成功/失敗
    """
    try:
        # 該当するルールのハンドルを検索して削除
        if dest_port:
            search_pattern = f"ip saddr {src_ip} tcp dport {dest_port}"
        else:
            search_pattern = f"ip saddr {src_ip}"
        
        # ルール一覧取得
        result = subprocess.run([
            "nft", "-a", "list", "table", "inet", "azazel"
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            logger.warning("Failed to list nft rules")
            return False
        
        # 該当ルールのハンドルを探す
        for line in result.stdout.split('\n'):
            if search_pattern in line and "handle" in line:
                # ハンドル番号を抽出
                handle = line.split("handle")[-1].strip()
                if handle.isdigit():
                    # ルール削除
                    delete_cmd = [
                        "nft", "delete", "rule", "inet", "azazel", "prerouting", 
                        "handle", handle
                    ]
                    delete_result = subprocess.run(delete_cmd, capture_output=True, timeout=10)
                    
                    if delete_result.returncode == 0:
                        logger.info(f"DNAT rule removed: {src_ip}")
                        return True
        
        logger.warning(f"No matching DNAT rule found for {src_ip}")
        return False
        
    except Exception as e:
        logger.error(f"Failed to remove DNAT rule: {e}")
        return False


def list_active_diversions() -> list:
    """現在アクティブな転送ルールのリストを取得"""
    try:
        result = subprocess.run([
            "nft", "list", "table", "inet", "azazel"
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            return []
        
        diversions = []
        for line in result.stdout.split('\n'):
            if "dnat to" in line and "ip saddr" in line:
                diversions.append(line.strip())
        
        return diversions
        
    except Exception as e:
        logger.error(f"Failed to list active diversions: {e}")
        return []


def cleanup_expired_rules(max_age_minutes: int = 60) -> int:
    """期限切れの転送ルールをクリーンアップ（実装例）"""
    # 実際の実装では、ルール作成時刻を記録し、期限切れのものを削除
    # この例では簡略化
    logger.info(f"Cleanup rules older than {max_age_minutes} minutes (placeholder)")
    return 0


if __name__ == "__main__":
    # テスト実行
    print(f"OpenCanary IP: {load_opencanary_ip()}")
    print("Testing DNAT rule addition...")
    
    # テスト用のIPアドレス
    test_ip = "192.168.1.200"
    test_port = 22
    
    if divert_to_opencanary(test_ip, test_port):
        print("✓ DNAT rule added successfully")
        
        # アクティブな転送ルール一覧
        active = list_active_diversions()
        print(f"Active diversions: {len(active)}")
        for rule in active:
            print(f"  {rule}")
        
        # ルール削除テスト
        if remove_divert_rule(test_ip, test_port):
            print("✓ DNAT rule removed successfully")
        else:
            print("✗ Failed to remove DNAT rule")
    else:
        print("✗ Failed to add DNAT rule")