#!/usr/bin/env python3
# coding: utf-8
"""
Mattermost通知機能 - Azazel-Pi用
"""

import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# ログ設定
logger = logging.getLogger(__name__)


def _load_notify_config() -> Dict[str, Any]:
    """通知設定を読み込む"""
    repo_root = Path(__file__).resolve().parents[2]
    config_paths = [
        Path("/etc/azazel/notify.yaml"),
        repo_root / "configs" / "notify.yaml",
    ]
    
    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    if config:
                        return config
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")
                continue
    
    # デフォルト設定
    return {
        "mattermost_webhook_url": None,
        "enabled": False,
        "timeout": 10
    }


def format_alert_message(source: str, alert_data: Dict[str, Any]) -> str:
    """アラートデータを整形されたメッセージに変換"""
    timestamp = alert_data.get("timestamp", datetime.now().isoformat())
    signature = alert_data.get("signature", "Unknown Alert")
    severity = alert_data.get("severity", 3)
    src_ip = alert_data.get("src_ip", "Unknown")
    dest_ip = alert_data.get("dest_ip", "Unknown")
    proto = alert_data.get("proto", "Unknown")
    details = alert_data.get("details", "")
    confidence = alert_data.get("confidence", "Unknown")
    
    # 重要度に応じた絵文字
    severity_emoji = {
        1: "🚨",  # Critical
        2: "⚠️",   # High
        3: "📢",   # Medium
        4: "ℹ️",   # Low
        5: "📝"    # Info
    }.get(severity, "📊")
    
    # メッセージフォーマット
    message = f"{severity_emoji} **[{source}]** {signature}\n\n"
    message += f"**時刻:** {timestamp}\n"
    message += f"**送信元IP:** `{src_ip}`\n"
    message += f"**宛先IP:** `{dest_ip}`\n"
    message += f"**プロトコル:** {proto}\n"
    message += f"**信頼度:** {confidence}\n"
    
    if details:
        message += f"**詳細:** {details}\n"
    
    return message


def send_alert_to_mattermost(source: str, alert_data: Dict[str, Any]) -> bool:
    """
    Mattermostにアラートを送信
    
    Args:
        source: アラートの送信元 (例: "Suricata", "OpenCanary")
        alert_data: アラートデータの辞書
        
    Returns:
        bool: 送信成功/失敗
    """
    config = _load_notify_config()
    
    # 通知が無効またはWebhook URLが設定されていない場合
    mattermost_config = config.get("mattermost", {})
    enabled = mattermost_config.get("enabled", config.get("enabled", False))
    # 新旧両方のキー名をサポート（互換性のため）
    webhook_url = (mattermost_config.get("webhook_url") or 
                  config.get("mattermost_webhook_url") or
                  config.get("webhook_url"))
    
    if not enabled or not webhook_url:
        logger.debug("Mattermost notifications disabled or webhook URL not configured")
        return True  # 設定無効は正常な状態として扱う
    
    # webhook_url = config["mattermost_webhook_url"]  # この行は上で取得済み
    timeout = config.get("timeout", 10)
    
    try:
        # メッセージを整形
        message = format_alert_message(source, alert_data)
        
        # Mattermostペイロード作成（最小構成）
        # botユーザのWebhookを使用し、@ユーザー通知で個別通知
        notify_users = mattermost_config.get("notify_users", [])
        
        # ユーザー通知部分を追加
        user_mentions = ""
        if notify_users:
            mentions = [f"@{user}" for user in notify_users]
            user_mentions = f"**通知対象:** {', '.join(mentions)}\n\n"
        
        # メッセージにユーザーメンション追加
        final_message = user_mentions + message
        
        payload = {
            "text": final_message,
            "props": {
                "severity": alert_data.get("severity", 3),
                "source": source,
                "timestamp": alert_data.get("timestamp", datetime.now().isoformat())
            }
        }
        
        # JSON エンコード
        data = json.dumps(payload).encode('utf-8')
        
        # HTTPリクエスト作成
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Azazel-Pi/1.0'
        }
        
        request = urllib.request.Request(
            webhook_url, 
            data=data, 
            headers=headers
        )
        
        # 送信実行
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status == 200:
                logger.info(f"Alert sent to Mattermost: {source}")
                return True
            else:
                logger.error(f"Mattermost returned status {response.status}")
                return False
                
    except urllib.error.URLError as e:
        logger.error(f"Network error sending to Mattermost: {e}")
        return False
    except json.JSONEncodeError as e:
        logger.error(f"JSON encoding error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending to Mattermost: {e}")
        return False


def send_simple_message(message: str, level: str = "info") -> bool:
    """
    シンプルなテキストメッセージをMattermostに送信
    既存のcore/notify/mattermost.pyとの互換性のために提供
    
    Args:
        message: 送信するメッセージ
        level: ログレベル ("info", "warn", "error", "critical")
        
    Returns:
        bool: 送信成功/失敗
    """
    # レベルに応じた重要度マッピング
    level_severity = {
        "critical": 1,
        "error": 2,
        "warn": 3,
        "warning": 3,
        "info": 4,
        "debug": 5
    }
    
    alert_data = {
        "timestamp": datetime.now().isoformat(),
        "signature": message,
        "severity": level_severity.get(level.lower(), 4),
        "src_ip": "-",
        "dest_ip": "-",
        "proto": "-",
        "details": "",
        "confidence": "System"
    }
    
    return send_alert_to_mattermost("System", alert_data)


# 既存のcore/notify/mattermost.pyとの互換性のための関数
def send_alert_to_mattermost_legacy(message: str, level: str = "info") -> None:
    """
    既存のcore/notify/mattermost.pyとの完全な互換性のためのラッパー関数
    
    Args:
        message: 送信するメッセージ
        level: ログレベル
    """
    send_simple_message(message, level)


def test_mattermost_connection() -> bool:
    """Mattermost接続をテスト"""
    config = _load_notify_config()
    
    mattermost_config = config.get("mattermost", {})
    enabled = mattermost_config.get("enabled", config.get("enabled", False))
    # 新旧両方のキー名をサポート（互換性のため）
    webhook_url = (mattermost_config.get("webhook_url") or 
                  config.get("mattermost_webhook_url") or
                  config.get("webhook_url"))
    notify_users = mattermost_config.get("notify_users", [])
    
    print(f"通知設定確認:")
    print(f"  有効フラグ: {enabled}")
    print(f"  Webhook URL: {'設定済み' if webhook_url else '未設定'}")
    print(f"  通知対象ユーザー: {notify_users if notify_users else '設定なし'}")
    
    if not enabled:
        print("❌ Mattermost通知が無効です")
        return False
    
    if not webhook_url:
        print("❌ Webhook URLが設定されていません")
        return False
    
    # テストメッセージを送信
    test_message = "🧪 Azazel-Pi Mattermost接続テスト（最小構成）"
    success = send_simple_message(test_message, "info")
    
    if success:
        print("✅ Mattermost通知テスト成功")
        if notify_users:
            print(f"   📢 {', '.join([f'@{user}' for user in notify_users])} に通知されました")
    else:
        print("❌ Mattermost通知テスト失敗")
    
    return success


if __name__ == "__main__":
    # テスト実行
    print("Mattermost通知機能テスト")
    print("-" * 40)
    
    # 設定読み込みテスト
    config = _load_notify_config()
    print(f"設定読み込み: {config}")
    
    # 接続テスト
    test_mattermost_connection()
    
    # アラート送信テスト
    test_alert = {
        "timestamp": datetime.now().isoformat(),
        "signature": "テスト用アラート",
        "severity": 2,
        "src_ip": "192.168.1.200",
        "dest_ip": "192.168.1.1",
        "proto": "TCP",
        "details": "これはテスト用のアラートです",
        "confidence": "High"
    }
    
    success = send_alert_to_mattermost("Test", test_alert)
    print(f"アラート送信テスト: {'成功' if success else '失敗'}")
