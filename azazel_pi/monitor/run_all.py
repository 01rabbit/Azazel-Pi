import threading
import signal
import sys
import time
import logging
import subprocess
from datetime import datetime, timedelta

from ..core import notify_config as notice
from ..core.enforcer.traffic_control import get_traffic_control_engine
from ..utils.mattermost import send_alert_to_mattermost
import os
from ..utils.wan_state import get_active_wan_interface
from . import main_suricata
from . import main_opencanary

# ログ設定（Suricata/OpenCanaryと揃える）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# グローバル変数
last_attack_time = datetime.now(notice.TZ)
is_normal_mode = False

# notice.pyから設定読み込み
INACTIVITY_LIMIT = timedelta(minutes=notice.INACTIVITY_MINUTES)
threads = []

# ─────────────────────────────────────
def run_suricata():
    main_suricata.main()

def run_opencanary():
    main_opencanary.main()

def notify_attack_detected():
    """攻撃検知時に呼び出す関数"""
    global last_attack_time, is_normal_mode
    last_attack_time = datetime.now(notice.TZ)
    is_normal_mode = False

def reset_network_config():
    logging.info("Flushing NAT rules and resetting network config via integrated system...")
    # Prefer explicit environment override, then runtime WAN manager helper, then fallback
    wan_iface = os.environ.get("AZAZEL_WAN_IF") or get_active_wan_interface()

    # ① 統合トラフィック制御システムで全制御ルールをクリア
    try:
        traffic_engine = get_traffic_control_engine()
        active_rules = traffic_engine.get_active_rules()
        
        cleared_count = 0
        for src_ip in list(active_rules.keys()):
            if traffic_engine.remove_rules_for_ip(src_ip):
                cleared_count += 1
                logging.info(f"Cleared traffic control rules for {src_ip}")
        
        if cleared_count > 0:
            logging.info(f"Integrated system cleared {cleared_count} rule sets")
        else:
            logging.info("No active traffic control rules to clear")
            
    except Exception as e:
        logging.error(f"Integrated system cleanup failed: {e}")
        # フォールバック: 従来のtc直接実行
        result = subprocess.run(["tc", "qdisc", "show", "dev", wan_iface], capture_output=True, text=True)
        if "prio" in result.stdout or "netem" in result.stdout:
            subprocess.run(["tc", "qdisc", "del", "dev", wan_iface, "root"], check=False)
            logging.info("Fallback: tc qdisc deleted directly")

    # ② NATテーブルの全ルールを一旦削除
    subprocess.run(["iptables", "-t", "nat", "-F"], check=False)

    # ③ 内部LAN(172.16.0.0/24)からWAN出口(wlan1)へのMASQUERADEを再設定
    subprocess.run(["iptables", "-t", "nat", "-A", "POSTROUTING",
                    "-s", "172.16.0.0/24", "-o", wan_iface, "-j", "MASQUERADE"], check=True)

    logging.info("Internal LAN to WAN routing re-established.")
    logging.info("Network reset completed via integrated system.")
    
    now_str = datetime.now(notice.TZ).strftime("%Y-%m-%d %H:%M:%S")
    send_alert_to_mattermost("Suricata", {
        "timestamp": now_str,
        "signature": "🟢 通常態勢復帰",
        "severity": 3,
        "src_ip": "-",
        "dest_ip": "-",
        "proto": "-",
        "details": f"{notice.INACTIVITY_MINUTES}分間攻撃が観測されなかったため、通常態勢に復帰しました。",
        "confidence": "Low"
    })
    logging.info("通常態勢復帰メッセージ送信済み。")

def inactivity_watcher():
    global last_attack_time, is_normal_mode
    while True:
        now = datetime.now(notice.TZ)
        if now - last_attack_time > INACTIVITY_LIMIT:
            if not is_normal_mode:
                logging.info(f"No attacks detected for {notice.INACTIVITY_MINUTES} minutes. Resetting network settings...")
                reset_network_config()
                is_normal_mode = True
        time.sleep(30)

def signal_handler(sig, frame):
    logging.info("✋ Ctrl+C detected. Shutting down gracefully...")
    sys.exit(0)

# ─────────────────────────────────────
if __name__ == "__main__":
    logging.info("🚀 Starting unified monitor...")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    main_suricata.NOTIFY_CALLBACK = notify_attack_detected
    
    t1 = threading.Thread(target=run_suricata, daemon=True)
    t2 = threading.Thread(target=run_opencanary, daemon=True)
    t3 = threading.Thread(target=inactivity_watcher, daemon=True)

    threads.extend([t1, t2, t3])

    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("✋ KeyboardInterrupt caught. Exiting...")
        sys.exit(0)
