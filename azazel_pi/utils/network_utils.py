#!/usr/bin/env python3
# coding: utf-8
"""
共通ネットワークユーティリティ

WLANステータス取得、プロファイル情報取得など、
複数のモジュールで使用される共通ネットワーク機能を提供
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional, Any
import yaml

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_wlan_ap_status(interface: str = "wlan0") -> Dict[str, Any]:
    """
    WLAN APインターフェースのステータス取得
    
    Args:
        interface: チェック対象のインターフェース名
        
    Returns:
        Dict: APステータス情報
    """
    status = {
        "interface": interface,
        "is_ap": None,
        "ssid": None,
        "channel": None,
        "stations": None,
        "ip_address": None,
        "status": "unknown"
    }
    
    try:
        # インターフェース存在確認
        result = subprocess.run(
            ["ip", "link", "show", interface], 
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            status["status"] = "not_found"
            return status
            
        # IPアドレス取得
        result = subprocess.run(
            ["ip", "addr", "show", interface], 
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if "inet " in line and "scope global" in line:
                    status["ip_address"] = line.split()[1].split('/')[0]
                    break
        
        # AP情報取得
        result = subprocess.run(
            ["iw", "dev", interface, "info"], 
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if "type AP" in line:
                    status["is_ap"] = True
                elif "type managed" in line:
                    status["is_ap"] = False
                elif "channel" in line:
                    try:
                        status["channel"] = int(line.split()[1])
                    except (ValueError, IndexError):
                        pass
        
        # SSID取得（hostapd経由）
        if status["is_ap"]:
            try:
                result = subprocess.run(
                    ["hostapd_cli", "-i", interface, "status"], 
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if line.startswith("ssid="):
                            status["ssid"] = line.split('=', 1)[1]
                        elif line.startswith("num_sta="):
                            try:
                                status["stations"] = int(line.split('=')[1])
                            except ValueError:
                                pass
            except Exception:
                pass
        
        status["status"] = "active" if status["is_ap"] is not None else "inactive"
        
    except Exception as e:
        logger.error(f"WLAN AP status check failed for {interface}: {e}")
        status["status"] = "error"
    
    return status


def get_wlan_link_info(interface: str = "wlan1") -> Dict[str, Any]:
    """
    WLAN STAインターフェースのリンク情報取得
    
    Args:
        interface: チェック対象のインターフェース名
        
    Returns:
        Dict: リンク情報
    """
    info = {
        "interface": interface,
        "connected": None,
        "ssid": None,
        "signal": None,
        "frequency": None,
        "ip_address": None,
        "status": "unknown"
    }
    
    try:
        # インターフェース存在確認
        result = subprocess.run(["ip", "link", "show", interface], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            info["status"] = "not_found"
            # ensure compatibility keys exist
            info.setdefault("ip4", None)
            info.setdefault("signal_dbm", None)
            return info

        # IPv4 アドレス取得（第一の inet 行を使用）
        result = subprocess.run(["ip", "-4", "addr", "show", interface], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "inet " in line:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        info["ip_address"] = parts[1].split("/")[0]
                        break

        # 接続情報取得（iw経由）
        result = subprocess.run(["iw", "dev", interface, "link"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            out = result.stdout or ""
            if "Connected to" in out:
                info["connected"] = True
                for line in out.splitlines():
                    line = line.strip()
                    if line.startswith("SSID:"):
                        info["ssid"] = line.split("SSID:", 1)[1].strip()
                    elif line.startswith("freq:"):
                        try:
                            info["frequency"] = int(line.split("freq:", 1)[1].strip().split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif "signal:" in line:
                        # typical: 'signal: -45.00 dBm'
                        try:
                            info["signal"] = float(line.split("signal:", 1)[1].strip().split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif "signal_dbm" in line:
                        try:
                            # fallback parsing for alternate formats
                            info["signal"] = float(line.split("signal_dbm", 1)[1].strip().split()[0])
                        except (ValueError, IndexError):
                            pass
            else:
                info["connected"] = False

        info["status"] = "connected" if info["connected"] else "disconnected"

    except Exception as e:
        logger.error(f"WLAN link info check failed for {interface}: {e}")
        info["status"] = "error"

    # Backwards-compatible aliases expected by CLI/menu code
    if info.get("ip_address"):
        info["ip4"] = info.get("ip_address")
    else:
        info.setdefault("ip4", None)

    if info.get("signal") is not None:
        try:
            info["signal_dbm"] = int(round(info.get("signal")))
        except Exception:
            info["signal_dbm"] = None
    else:
        info.setdefault("signal_dbm", None)

    return info
def get_active_profile() -> Optional[str]:
    """
    現在アクティブなネットワークプロファイル取得
    
    Returns:
        Optional[str]: アクティブプロファイル名
    """
    config_paths = [
        Path("/etc/azazel/azazel.yaml"),
        Path(__file__).parent.parent.parent / "configs" / "network" / "azazel.yaml",
    ]
    
    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    profiles = config.get('profiles', {})
                    return profiles.get('active')
            except Exception as e:
                logger.warning(f"Failed to read config from {config_path}: {e}")
                continue
    
    return None


def get_network_interfaces_stats() -> Dict[str, Dict[str, int]]:
    """
    ネットワークインターフェース統計取得
    
    Returns:
        Dict: インターフェース別統計情報
    """
    stats = {}
    
    try:
        with open('/proc/net/dev', 'r') as f:
            lines = f.readlines()
            
        # ヘッダーをスキップ
        for line in lines[2:]:
            if ':' in line:
                interface, data = line.split(':', 1)
                interface = interface.strip()
                values = data.split()
                
                if len(values) >= 16:
                    stats[interface] = {
                        'rx_bytes': int(values[0]),
                        'rx_packets': int(values[1]),
                        'rx_errors': int(values[2]),
                        'rx_dropped': int(values[3]),
                        'tx_bytes': int(values[8]),
                        'tx_packets': int(values[9]),
                        'tx_errors': int(values[10]),
                        'tx_dropped': int(values[11])
                    }
                    
    except Exception as e:
        logger.error(f"Failed to read network interface stats: {e}")
    
    return stats


def format_bytes(bytes_value: int) -> str:
    """
    バイト値を人間が読みやすい形式にフォーマット
    
    Args:
        bytes_value: バイト値
        
    Returns:
        str: フォーマットされた文字列
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def get_comprehensive_network_status() -> Dict[str, Any]:
    """
    包括的なネットワークステータス取得
    
    Returns:
        Dict: 包括的ネットワーク情報
    """
    return {
        "wlan0_ap": get_wlan_ap_status("wlan0"),
        "wlan1_sta": get_wlan_link_info("wlan1"),
        "active_profile": get_active_profile(),
        "interface_stats": get_network_interfaces_stats(),
        "timestamp": subprocess.run(["date", "+%Y-%m-%d %H:%M:%S"], 
                                   capture_output=True, text=True).stdout.strip()
    }


# レガシー関数は完全に統合関数に移行されました


if __name__ == "__main__":
    # テスト実行
    print("=== ネットワークユーティリティテスト ===")
    
    # WLAN AP ステータス
    ap_status = get_wlan_ap_status("wlan0")
    print(f"WLAN0 AP Status: {ap_status}")
    
    # WLAN STA リンク情報
    link_info = get_wlan_link_info("wlan1")
    print(f"WLAN1 Link Info: {link_info}")
    
    # アクティブプロファイル
    profile = get_active_profile()
    print(f"Active Profile: {profile}")
    
    # インターフェース統計
    stats = get_network_interfaces_stats()
    print(f"Interface Stats: {list(stats.keys())}")
    
    # 包括的ステータス
    comprehensive = get_comprehensive_network_status()
    print(f"Comprehensive Status Keys: {list(comprehensive.keys())}")