#!/usr/bin/env python3
# coding: utf-8
"""
Suricata eve.json を監視し Mattermost へ通知、必要に応じ DNAT 遅滞行動を発動
"""

import json, time, logging, sys
from datetime import datetime
from collections import defaultdict
from pathlib import Path

from ..core import notify_config as notice
from ..core.state_machine import StateMachine, State, Event, Transition
from ..core.scorer import ScoreEvaluator
from ..utils.mattermost import send_alert_to_mattermost
from ..utils.delay_action import divert_to_opencanary, remove_divert_rule, OPENCANARY_IP

EVE_FILE           = Path(notice.SURICATA_EVE_JSON_PATH)
FILTER_SIG_CATEGORY = [
    "Attack Response","DNS","DOS","Exploit","FTP","ICMP","IMAP","Malware",
    "NETBIOS","Phishing","POP3","RPC","SCAN","Shellcode","SMTP","SNMP",
    "SQL","TELNET","TFTP","Web Client","Web Server","Web Specific Apps","WORM"
]
NOTIFY_CALLBACK = None

cooldown_seconds   = 60          # 同一シグネチャ抑止時間
summary_interval   = 60          # サマリ送信間隔
evaluation_interval = 30         # 脅威レベル評価間隔

last_alert_times  = {}
suppressed_alerts = defaultdict(int)
last_summary_time = time.time()
last_evaluation_time = time.time()

# 状態管理とスコアリング
portal_state = State("portal", "通常モード")
shield_state = State("shield", "警戒モード（遅延適用）")
lockdown_state = State("lockdown", "封鎖モード（DNAT転送）")

state_machine = StateMachine(
    initial_state=portal_state,
    transitions=[
        Transition(portal_state, shield_state, lambda e: e.name == "shield"),
        Transition(portal_state, lockdown_state, lambda e: e.name == "lockdown"),
        Transition(shield_state, portal_state, lambda e: e.name == "portal"),
        Transition(shield_state, lockdown_state, lambda e: e.name == "lockdown"),
        Transition(lockdown_state, shield_state, lambda e: e.name == "shield"),
        Transition(lockdown_state, portal_state, lambda e: e.name == "portal"),
    ]
)

scorer = ScoreEvaluator()
active_diversions = {}  # {src_ip: port} の転送中IPリスト

# ────────────────────────────────────────────────────────────
def follow(fp: Path, skip_existing=True):
    pos = None
    try:
        while True:
            if not fp.exists():
                time.sleep(1)
                continue

            size = fp.stat().st_size
            with fp.open() as f:
                if pos is None:
                    if skip_existing:
                        f.seek(0, 2)
                    pos = f.tell()

                if size < pos:
                    pos = 0
                f.seek(pos)

                for line in f:
                    yield line.rstrip("\n")
                pos = f.tell()
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n✋ Suricata monitor interrupted, exiting...")
        sys.exit(0)

# ────────────────────────────────────────────────────────────
def parse_alert(line: str):
    try:
        data = json.loads(line)
        if data.get("event_type") != "alert":
            return None

        alert      = data["alert"]
        signature  = alert["signature"]
        category   = signature.split(" ", 2)[1] if signature.startswith("ET ") else None

        if category and category in FILTER_SIG_CATEGORY:
            return {
                "timestamp" : data["timestamp"],
                "signature" : signature,
                "severity"  : alert.get("severity", 3),
                "src_ip"    : data.get("src_ip",""),
                "dest_ip"   : data.get("dest_ip",""),
                "proto"     : data.get("proto",""),
                "dest_port" : data.get("dest_port"),
                "details"   : alert,
                "confidence": alert.get("metadata",{}).get("confidence",["Unknown"])[0],
            }
    except json.JSONDecodeError:
        pass
    return None

# ────────────────────────────────────────────────────────────
def should_notify(key: str) -> bool:
    now  = datetime.now(notice.TZ)
    last = last_alert_times.get(key)
    if not last or (now-last).total_seconds() > cooldown_seconds:
        last_alert_times[key] = now
        return True
    return False

def send_summary():
    if not suppressed_alerts:
        return
    now_str = datetime.now(notice.TZ).strftime("%Y-%m-%d %H:%M")
    body = "\n".join(f"- {sig}: {cnt} times" for sig,cnt in suppressed_alerts.items())
    send_alert_to_mattermost("Suricata",{
        "timestamp": now_str,
        "signature": "Summary",
        "severity" : 3,
        "src_ip": "-", "dest_ip": "-", "proto": "-",
        "details": f"📃 **[Suricata Summary - {now_str}]**\n\n{body}",
        "confidence": "Low"
    })
    suppressed_alerts.clear()

# ────────────────────────────────────────────────────────────
def evaluate_threat_level():
    """現在の脅威レベルを評価し、必要に応じて状態遷移を実行"""
    global last_evaluation_time
    
    # 最近のアラート活動から脅威レベルを計算
    now = time.time()
    recent_activity = 0
    
    # 過去5分間のアラート数をカウント
    recent_threshold = now - 300  # 5分
    for alert_time in last_alert_times.values():
        if isinstance(alert_time, datetime):
            alert_timestamp = alert_time.timestamp()
            if alert_timestamp > recent_threshold:
                recent_activity += 1
    
    # 脅威スコア計算（アクティブな転送数も考慮）
    threat_score = recent_activity * 10 + len(active_diversions) * 5
    
    # 状態管理に脅威スコアを適用
    evaluation = state_machine.apply_score(threat_score)
    current_mode = state_machine.current_state.name
    
    logging.info(f"🔍 脅威評価: score={threat_score}, activity={recent_activity}, "
                f"diversions={len(active_diversions)}, mode={current_mode}")
    
    # モード変更時の処理
    if evaluation.get("target_mode") != evaluation.get("applied_mode"):
        mode_transition_action(current_mode, evaluation)
    
    return evaluation

def mode_transition_action(new_mode: str, evaluation: dict):
    """モード遷移時のアクション実行"""
    if new_mode == "portal":
        # 通常モード復帰：すべてのDNAT転送を停止
        restore_normal_mode()
        send_alert_to_mattermost("Azazel", {
            "timestamp": datetime.now().isoformat(),
            "signature": "✅ 通常モード復帰",
            "severity": 3,
            "src_ip": "-",
            "dest_ip": "-", 
            "proto": "-",
            "details": f"脅威レベル低下により通常運用に復帰しました。(スコア: {evaluation.get('average', 0):.1f})",
            "confidence": "High"
        })
        logging.info("🟢 [モード遷移] 通常モードに復帰")
        
    elif new_mode == "lockdown":
        send_alert_to_mattermost("Azazel", {
            "timestamp": datetime.now().isoformat(),
            "signature": "🚨 封鎖モード発動",
            "severity": 1,
            "src_ip": "-",
            "dest_ip": "-",
            "proto": "-", 
            "details": f"高脅威レベルにより封鎖モードを発動。(スコア: {evaluation.get('average', 0):.1f})",
            "confidence": "High"
        })
        logging.info("🔴 [モード遷移] 封鎖モード発動")

def restore_normal_mode():
    """通常モード復帰：すべてのDNAT転送を停止"""
    removed_count = 0
    for src_ip, port in list(active_diversions.items()):
        try:
            if remove_divert_rule(src_ip, port):
                removed_count += 1
                logging.info(f"🟢 DNAT解除: {src_ip}:{port}")
        except Exception as e:
            logging.error(f"DNAT解除エラー {src_ip}:{port}: {e}")
    
    active_diversions.clear()
    if removed_count > 0:
        logging.info(f"✅ 通常モード復帰: {removed_count}件のDNAT転送を解除")

def main():
    global last_summary_time, last_evaluation_time
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s")

    logging.info(f"🚀 Monitoring eve.json: {EVE_FILE}")
    logging.info(f"🛡️ 初期状態: {state_machine.current_state.name}")
    
    for line in follow(EVE_FILE):
        alert = parse_alert(line)
        if not alert:
            continue

        sig, src_ip, dport = alert["signature"], alert["src_ip"], alert["dest_port"]
        key = f"{sig}:{src_ip}"

        trigger = ("nmap" in sig.lower()) or (
            alert["proto"] == "TCP" and dport in (22, 80, 5432)
        )

        # ── 攻撃検知時の処理 ──────────────────
        if trigger:
            if should_notify(key):
                # 高脅威イベントとして記録
                threat_event = Event(name="attack_detected", severity=20)
                state_machine.dispatch(threat_event)
                
                send_alert_to_mattermost("Suricata",{
                    **alert,
                    "signature":"⚠️ 偵察／攻撃を検知",
                    "severity":1,
                    "details":sig,
                    "confidence":"High"
                })
                logging.info(f"Notify & DNAT: {sig}")

                try:
                    # DNAT転送実行
                    if divert_to_opencanary(src_ip, dport):
                        active_diversions[src_ip] = dport
                        
                        if 'NOTIFY_CALLBACK' in globals():
                            NOTIFY_CALLBACK()

                        send_alert_to_mattermost("Suricata",{
                            "timestamp": alert["timestamp"],
                            "signature": "🛡️ 遅滞行動発動（DNAT）",
                            "severity": 2,
                            "src_ip": src_ip,
                            "dest_ip": f"{OPENCANARY_IP}:{dport}",
                            "proto": alert["proto"],
                            "details": "攻撃元の通信を OpenCanary へ転送しました。",
                            "confidence": "High"
                        })
                        logging.info(f"[遅滞行動] {src_ip}:{dport} -> {OPENCANARY_IP}:{dport}")

                except Exception as e:
                    logging.error(f"DNAT error: {e}")
            else:
                suppressed_alerts[sig] += 1
            continue

        # ── 通常通知 ──────────────────
        if should_notify(key):
            # 通常のアラートとして記録
            normal_event = Event(name="alert", severity=alert["severity"])
            state_machine.dispatch(normal_event)
            send_alert_to_mattermost("Suricata", alert)
        else:
            suppressed_alerts[sig] += 1

        # ── 定期評価・サマリ ────────────────────
        now = time.time()
        if now - last_evaluation_time >= evaluation_interval:
            evaluate_threat_level()
            last_evaluation_time = now
            
        if now - last_summary_time >= summary_interval:
            send_summary()
            last_summary_time = now

def watch_suricata():
    """Suricata監視を開始（外部から呼び出し可能な関数）"""
    return main()


if __name__ == "__main__":
    main()
