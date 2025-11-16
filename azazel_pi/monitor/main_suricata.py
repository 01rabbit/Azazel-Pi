#!/usr/bin/env python3
# coding: utf-8
"""
Suricata eve.json を監視し Mattermost へ通知、必要に応じ DNAT 遅滞行動を発動
"""

import json, time, logging, sys, threading
from datetime import datetime
from collections import defaultdict, deque
from pathlib import Path

from ..core import notify_config as notice
from ..core.state_machine import StateMachine, State, Event, Transition
from ..core.enforcer.traffic_control import get_traffic_control_engine
from ..core.offline_ai_evaluator import evaluate_with_offline_ai
from ..core.hybrid_threat_evaluator import evaluate_with_hybrid_system
from ..utils.mattermost import send_alert_to_mattermost

EVE_FILE           = Path(notice.SURICATA_EVE_JSON_PATH)
FILTER_SIG_CATEGORY = [
    "Attack Response","DNS","DOS","Exploit","FTP","ICMP","IMAP","Malware",
    "NETBIOS","Phishing","POP3","RPC","SCAN","Shellcode","SMTP","SNMP",
    "SQL","TELNET","TFTP","Web Client","Web Server","Web Specific Apps","WORM"
]
NOTIFY_CALLBACK = None

# 設定読込（allow/denyカテゴリ）
def _load_main_config() -> dict:
    import yaml
    candidates = [
        Path("/etc/azazel/azazel.yaml"),
        Path.cwd() / "configs" / "network" / "azazel.yaml",
        Path.cwd() / "configs" / "azazel.yaml",
    ]
    for p in candidates:
        try:
            if p.exists():
                return yaml.safe_load(p.read_text()) or {}
        except Exception:
            continue
    return {}

_cfg = _load_main_config()
_soc = _cfg.get("soc", {}) if isinstance(_cfg, dict) else {}
_allow = _soc.get("allowed_categories")
_deny = _soc.get("denied_categories")

# Denylist と Critical Signatures の読み込み
DENYLIST_IPS = set(_soc.get("denylist_ips", []))
CRITICAL_SIGNATURES = _soc.get("critical_signatures", [])

# allow/deny は正規化（lower/underscore→space）。allowがNoneなら全許可（denyのみ適用）
def _norm_cat(x: str) -> str:
    return x.replace("_", " ").lower()

ALLOWED_SIG_CATEGORIES = None if not _allow else { _norm_cat(c) for c in _allow }
DENIED_SIG_CATEGORIES = set()
if _deny:
    DENIED_SIG_CATEGORIES = { _norm_cat(c) for c in _deny }
if ALLOWED_SIG_CATEGORIES is None:
    # 既定は既存リストを許可（後方互換）
    ALLOWED_SIG_CATEGORIES = { _norm_cat(c) for c in FILTER_SIG_CATEGORY }

cooldown_seconds   = 60          # 同一シグネチャ抑止時間
summary_interval   = 60          # サマリ送信間隔

last_alert_times  = {}
suppressed_alerts = defaultdict(int)
last_summary_time = time.time()
last_cleanup_time = time.time()

# 独立した頻度カウンタ: signature×src_ip の時系列（epoch秒）
recent_events = defaultdict(lambda: deque(maxlen=1000))

def record_event(signature: str, src_ip: str, ts: float | None = None):
    if ts is None:
        ts = time.time()
    key = f"{signature}:{src_ip}"
    recent_events[key].append(ts)

def count_recent(signature: str, src_ip: str, within_seconds: int = 300) -> int:
    key = f"{signature}:{src_ip}"
    now = time.time()
    dq = recent_events.get(key, deque())
    # 古いものを落としながらカウント
    while dq and (now - dq[0]) > within_seconds:
        dq.popleft()
    return len(dq)

def check_exception_block(alert: dict) -> bool:
    """
    例外遮断チェック: denylistまたはcritical signatureに該当するか
    
    Returns:
        True if should be immediately blocked
    """
    src_ip = alert.get("src_ip", "")
    signature = alert.get("signature", "")
    
    # Denylist IP チェック
    if src_ip in DENYLIST_IPS:
        logging.warning(f"[EXCEPTION BLOCK] Denylist IP detected: {src_ip}")
        return True
    
    # Critical Signature チェック
    for critical_pattern in CRITICAL_SIGNATURES:
        if critical_pattern.upper() in signature.upper():
            logging.warning(f"[EXCEPTION BLOCK] Critical signature detected: {signature}")
            return True
    
    return False

# 状態管理とスコアリング
normal_state = State("normal", "通常モード（制御なし）")
portal_state = State("portal", "監視モード")
shield_state = State("shield", "警戒モード（遅延適用）")
lockdown_state = State("lockdown", "封鎖モード（DNAT転送）")

state_machine = StateMachine(
    initial_state=portal_state,
    transitions=[
        Transition(normal_state, portal_state, lambda e: e.name == "portal"),
        Transition(normal_state, shield_state, lambda e: e.name == "shield"),
        Transition(normal_state, lockdown_state, lambda e: e.name == "lockdown"),
        Transition(portal_state, normal_state, lambda e: e.name == "normal"),
        Transition(portal_state, shield_state, lambda e: e.name == "shield"),
        Transition(portal_state, lockdown_state, lambda e: e.name == "lockdown"),
        Transition(shield_state, normal_state, lambda e: e.name == "normal"),
        Transition(shield_state, portal_state, lambda e: e.name == "portal"),
        Transition(shield_state, lockdown_state, lambda e: e.name == "lockdown"),
        Transition(lockdown_state, normal_state, lambda e: e.name == "normal"),
        Transition(lockdown_state, shield_state, lambda e: e.name == "shield"),
        Transition(lockdown_state, portal_state, lambda e: e.name == "portal"),
    ]
)

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
        raw_cat    = signature.split(" ", 2)[1] if signature.startswith("ET ") else None
        category_norm = raw_cat.replace("_", " ").lower() if raw_cat else None

        # deny優先→allow（allow不在時は後方互換の既定を使用）
        if category_norm and category_norm in DENIED_SIG_CATEGORIES:
            return None
        if category_norm and (ALLOWED_SIG_CATEGORIES and category_norm not in ALLOWED_SIG_CATEGORIES):
            return None
        # 上記を通過したら通す
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

def calculate_threat_score(alert: dict, signature: str, use_ai: bool = True) -> tuple[int, dict]:
    """
    AI強化型脅威スコア計算 (既存のルールベース + LLM評価)
    
    Args:
        alert: Suricataアラート情報
        signature: シグネチャ文字列
        use_ai: AI評価を使用するかどうか
    
    Returns:
        tuple: (脅威スコア (0-100), AI評価詳細)
    """
    
    # ハイブリッドAI評価の実行 (Legacy + Mock LLM統合)
    ai_result = {"ai_used": False}
    if use_ai:
        try:
            # ハイブリッドシステムを使用
            ai_result = evaluate_with_hybrid_system(alert)
            ai_score = ai_result["score"]  # 直接0-100スケールで取得
            logging.info(f"Hybrid評価: risk={ai_result['risk']}, score={ai_score}, category={ai_result['category']}, method={ai_result.get('evaluation_method', 'unknown')}")
            
            # ハイブリッド評価が利用可能な場合、そのスコアを使用
            base_score = ai_score
        except Exception as e:
            logging.warning(f"Hybrid AI評価エラー、Mock LLMフォールバック: {e}")
            try:
                # フォールバック: Mock LLMのみ
                ai_result = evaluate_with_offline_ai(alert)
                ai_score = (ai_result["risk"] - 1) * 25
                base_score = ai_score
                logging.info(f"Mock LLM評価 (フォールバック): risk={ai_result['risk']}, score={ai_score}")
            except Exception as e2:
                logging.warning(f"Mock LLM評価もエラー、Legacyフォールバック: {e2}")
                use_ai = False
    
    if not use_ai or not ai_result.get("ai_used", False):
        # 従来のルールベース評価
        base_score = 0
        
        # 1. Suricata severity (1=最高危険, 4=低危険) を基準スコアに変換
        suricata_severity = alert.get("severity", 3)
        severity_mapping = {1: 25, 2: 15, 3: 8, 4: 3}
        base_score = severity_mapping.get(suricata_severity, 5)
    
    # 2. シグネチャパターンベースのスコア加算
    sig_lower = signature.lower()
    
    # 高危険度攻撃パターン (+20-30)
    if any(pattern in sig_lower for pattern in ["exploit", "malware", "trojan", "backdoor"]):
        base_score += 30
    elif any(pattern in sig_lower for pattern in ["shellcode", "injection", "overflow"]):
        base_score += 25
    elif any(pattern in sig_lower for pattern in ["nmap", "scan", "probe", "reconnaissance"]):
        base_score += 20
    
    # 中危険度パターン (+10-15)
    elif any(pattern in sig_lower for pattern in ["dos", "ddos", "flood"]):
        base_score += 15
    elif any(pattern in sig_lower for pattern in ["brute", "bruteforce", "dictionary"]):
        base_score += 12
    elif any(pattern in sig_lower for pattern in ["suspicious", "anomal", "unusual"]):
        base_score += 10
    
    # 3. 対象ポートベースの加算
    dest_port = alert.get("dest_port")
    critical_ports = [22, 80, 443, 3389, 5432, 3306, 1433]  # SSH, HTTP, HTTPS, RDP, PostgreSQL, MySQL, MSSQL
    if dest_port in critical_ports:
        base_score += 8
    
    # 4. プロトコルベースの調整
    proto = alert.get("proto", "").upper()
    if proto == "TCP":
        base_score += 3  # TCPは一般的に重要
    elif proto == "ICMP":
        base_score += 1  # ICMPは偵察に使用されることが多い
    
    # 5. メタデータからの情報（存在する場合）
    metadata = alert.get("details", {}).get("metadata", {})
    if isinstance(metadata, dict):
        # 攻撃対象カテゴリ
        if metadata.get("attack_target"):
            base_score += 5
        # 既知の脅威グループ/ファミリー
        if metadata.get("malware_family") or metadata.get("former_category"):
            base_score += 10
    
    # 6. 頻度ベースの動的調整
    # 独立カウンタに基づく頻度評価（5分）
    recent_same_sig = count_recent(signature, alert.get("src_ip", ""), within_seconds=300)
    
    if recent_same_sig > 5:  # 5分以内に同じシグネチャが5回以上
        base_score += 15  # 集中攻撃の可能性
    elif recent_same_sig > 2:
        base_score += 8
    
    # 7. スコアの正規化 (0-100の範囲)
    final_score = min(max(base_score, 0), 100)
    
    logging.debug(f"脅威スコア計算: {signature[:50]}... -> {final_score} "
                 f"(AI:{ai_result.get('ai_used', False)}, "
                 f"port:{dest_port}, freq:{recent_same_sig})")
    
    return final_score, ai_result

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


def _run_ai_analysis_and_notify(alert: dict) -> None:
    """Mock LLM / Ollama分析を制御フローから切り離してMattermost通知する"""
    try:
        analysis = evaluate_with_hybrid_system(alert)
        method = analysis.get("evaluation_method", "hybrid")
    except Exception as e:
        logging.warning(f"Hybrid AI評価に失敗。オフラインAIへフォールバック: {e}")
        try:
            analysis = evaluate_with_offline_ai(alert)
            method = analysis.get("evaluation_method", "offline_ai")
        except Exception as e2:
            logging.error(f"AI分析すら実行できませんでした: {e2}")
            return

    details_parts = [
        f"method={method}",
        f"risk={analysis.get('risk', 'n/a')}",
    ]
    if analysis.get("score") is not None:
        details_parts.append(f"score={analysis.get('score')}")
    if analysis.get("category"):
        details_parts.append(f"category={analysis.get('category')}")

    details_text = " / ".join(details_parts)

    try:
        send_alert_to_mattermost("Suricata", {
            **alert,
            "signature": "🔎 AI分析結果 (参考)",
            "severity": 2,
            "details": details_text,
            "confidence": analysis.get("confidence", "Info"),
        })
    except Exception as e:
        logging.error(f"AI分析結果の通知に失敗: {e}")


def notify_ai_analysis_async(alert: dict) -> None:
    threading.Thread(target=_run_ai_analysis_and_notify, args=(alert,), daemon=True).start()

def restore_normal_mode():
    """通常モード復帰：すべての制御ルールを停止"""
    traffic_engine = get_traffic_control_engine()
    active_rules = traffic_engine.get_active_rules()
    
    removed_count = 0
    for src_ip in list(active_rules.keys()):
        try:
            if traffic_engine.remove_rules_for_ip(src_ip):
                removed_count += 1
                logging.info(f"🟢 制御解除: {src_ip}")
        except Exception as e:
            logging.error(f"制御解除エラー {src_ip}: {e}")
    
    # 従来のactive_diversions辞書もクリア（後方互換性）
    if 'active_diversions' in globals():
        active_diversions.clear()
    
    if removed_count > 0:
        logging.info(f"✅ 通常モード復帰: {removed_count}件の制御ルールを解除")

def main():
    global last_summary_time, last_cleanup_time
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s")

    # Ensure fresh metrics and portal mode at service start
    state_machine.reset()

    logging.info(f"🚀 Monitoring eve.json: {EVE_FILE}")
    logging.info(f"🛡️ 初期状態: {state_machine.current_state.name}")
    logging.info("⚠️ スコアリングは一時的に無効化。検知トラフィックは即座にOpenCanaryへ転送します。")

    for line in follow(EVE_FILE):
        alert = parse_alert(line)
        if not alert:
            continue

        sig, src_ip, dport = alert["signature"], alert["src_ip"], alert["dest_port"]
        key = f"{sig}:{src_ip}"

        # ── 例外遮断チェック（評価前に即時ブロック） ──────────────────
        if check_exception_block(alert):
            try:
                traffic_engine = get_traffic_control_engine()
                # 即時ブロック適用（block=True, delay_ms=0）
                if traffic_engine.apply_block(src_ip):
                    logging.warning(f"[EXCEPTION BLOCK] Immediate block applied: {src_ip}")
                    send_alert_to_mattermost("Suricata",{
                        **alert,
                        "signature":"🚨 例外遮断発動",
                        "severity":1,
                        "details":f"Denylist/Critical signature detected: {sig}",
                        "confidence":"Critical"
                    })
            except Exception as e:
                logging.error(f"例外遮断エラー: {e}")
            # 例外遮断したIPは通常評価をスキップ
            continue

        # 通知可否に関係なく頻度カウンタに記録
        try:
            # timestamp がISOの可能性もあるため、現在時刻で代替
            record_event(sig, src_ip)
        except Exception:
            pass

        # AI分析は制御から切り離し、通知のみ実施
        notify_ai_analysis_async(alert)

        # ── 通知（クールダウン制御あり） ──────────────────
        if should_notify(key):
            send_alert_to_mattermost("Suricata", {
                **alert,
                "signature": "⚠️ 偵察／攻撃を検知",
                "severity": 1,
                "details": sig,
                "confidence": "High"
            })
            logging.info(f"Notify attack: {sig}")
        else:
            suppressed_alerts[sig] += 1

        # ── 無条件のOpenCanary転送 ──────────────────
        try:
            traffic_engine = get_traffic_control_engine()
            active_ips = set(traffic_engine.get_active_rules().keys())
            already_active = src_ip in active_ips

            redirected = traffic_engine.apply_dnat_redirect(src_ip, dport)
            if redirected:
                active_diversions[src_ip] = dport
                if state_machine.current_state.name != "shield":
                    state_machine.dispatch(Event(name="shield", severity=0))

                if should_notify(key + ":action") and not already_active:
                    dest_info = f"OpenCanary:{dport}" if dport else "OpenCanary"
                    send_alert_to_mattermost("Suricata", {
                        "timestamp": alert["timestamp"],
                        "signature": "🛡️ OpenCanary転送を開始",
                        "severity": 2,
                        "src_ip": src_ip,
                        "dest_ip": dest_info,
                        "proto": alert["proto"],
                        "details": "検知した通信をOpenCanaryへ即時転送しました（追加の遅延/帯域制御なし）",
                        "confidence": "High"
                    })

                logging.info(f"[OpenCanary転送] {src_ip} -> OpenCanary" + (f":{dport}" if dport else ""))
            else:
                logging.error(f"DNAT redirect failed for {src_ip}")
        except Exception as e:
            logging.error(f"OpenCanary転送エラー: {e}")

        # ── サマリとクリーンアップ ────────────────────
        now = time.time()

        if now - last_summary_time >= summary_interval:
            send_summary()
            last_summary_time = now

        if now - last_cleanup_time >= 600:
            try:
                engine = get_traffic_control_engine()
                engine.cleanup_expired_rules(max_age_seconds=3600)
                if not engine.get_active_rules() and state_machine.current_state.name != "portal":
                    state_machine.dispatch(Event(name="portal", severity=0))
            except Exception:
                pass
            last_cleanup_time = now

def watch_suricata():
    """Suricata監視を開始（外部から呼び出し可能な関数）"""
    return main()


if __name__ == "__main__":
    main()
