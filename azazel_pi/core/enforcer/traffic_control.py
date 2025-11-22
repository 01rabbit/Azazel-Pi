#!/usr/bin/env python3
# coding: utf-8
"""
統合トラフィック制御システム
DNAT転送、tc遅延、QoS制御を統合管理
"""

import logging
import subprocess
import time
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import yaml
import threading

# 統合システムでは actions モジュールは使用しない（直接tc/nftコマンド実行）
from ...utils.delay_action import (
    load_opencanary_ip, OPENCANARY_IP, ensure_nft_table_and_chain
)
from ...utils.wan_state import get_active_wan_interface
import os

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
        # Respect AZAZEL_WAN_IF environment override first, then WAN manager helper
        self.interface = os.environ.get("AZAZEL_WAN_IF") or get_active_wan_interface()
        self._testing = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        self.active_rules: Dict[str, List[TrafficControlRule]] = {}
        # lock protecting active_rules and related operations
        self._rules_lock = threading.Lock()
        self._ensure_tc_setup()

        if not self._testing:
            # Restore any persisted nft handles into in-memory active_rules mapping so
            # deletions by handle will work across restarts.
            try:
                self._restore_persisted_diversions()
            except Exception:
                logger.exception('Failed restoring persisted nft handles at startup')
            # Validate persisted entries and prune stale ones
            try:
                self._validate_and_clean_persisted_diversions()
            except Exception:
                logger.exception('Failed validating persisted nft handles at startup')

        # Start background cleanup thread (uses config.rules.cleanup_interval_seconds)
        try:
            conf = self._load_config()
            rules_cfg = conf.get("rules", {}) if isinstance(conf, dict) else {}
            self._cleanup_interval = int(rules_cfg.get("cleanup_interval_seconds", 60) or 60)
            self._max_rule_age = int(rules_cfg.get("max_age_seconds", 3600) or 3600)
        except Exception:
            self._cleanup_interval = 60
            self._max_rule_age = 3600

        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True, name="azazel-tc-cleanup")
        self._cleanup_thread.start()
        
    def _load_config(self) -> Dict:
        """設定ファイルを読み込み"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Config load failed: {e}")
            return {}

    # --- safe subprocess result accessors ---
    def _safe_stdout(self, proc) -> str:
        """Return stdout as str, tolerating Mock objects or None."""
        try:
            return str(getattr(proc, 'stdout', '') or '')
        except Exception:
            try:
                # Some mocks may be simple callables/objects; coerce to str
                return str(proc)
            except Exception:
                return ""

    def _safe_stderr(self, proc) -> str:
        """Return stderr as str, tolerating Mock objects or None."""
        try:
            return str(getattr(proc, 'stderr', '') or '')
        except Exception:
            try:
                return str(proc)
            except Exception:
                return ""

    def _run_cmd(self, cmd, capture_output=True, text=True, timeout=None, check=False):
        """Centralized subprocess runner to make testing/mocking easier.

        - Uses an injectable runner if tests set `self._subprocess_runner` (callable).
        - Normalizes unexpected/mocked returns to CompletedProcess-like objects.
        """
        runner = getattr(self, '_subprocess_runner', subprocess.run)
        try:
            return runner(cmd, capture_output=capture_output, text=text, timeout=timeout, check=check)
        except TypeError:
            # Some test doubles may be simple callables that accept only (cmd,) positional.
            try:
                res = runner(cmd)
                return res
            except Exception:
                # Fall through to creating a safe CompletedProcess
                return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="")
        except Exception as e:
            # Ensure we always return a CompletedProcess-like object to callers
            try:
                return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=str(e))
            except Exception:
                # Last resort
                class _Dummy:
                    returncode = 1
                    stdout = ""
                    stderr = ""
                return _Dummy()

    def set_subprocess_runner(self, runner_callable):
        """Set a custom subprocess runner.

        Tests can inject a lightweight runner (callable) that accepts the same
        parameters as subprocess.run or at least (cmd,) and return an object
        with attributes: returncode, stdout, stderr.

        Example:
            engine.set_subprocess_runner(lambda cmd, **kw: make_completed_process(cmd, 0, stdout='ok'))
        """
        setattr(self, '_subprocess_runner', runner_callable)


    # --- diversion persistence helpers ---
    def _diversion_state_path(self) -> Path:
        return Path('/var/lib/azazel') / 'diversions.json'

    def _load_persisted_diversions(self) -> Dict[str, Dict]:
        path = self._diversion_state_path()
        try:
            if not path.exists():
                return {}
            with path.open('r') as fh:
                return json.load(fh)
        except Exception:
            logger.exception('Failed loading persisted nft handles')
            return {}

    def _validate_and_clean_persisted_diversions(self) -> None:
        """Verify persisted diversion metadata actually exists and remove stale entries."""
        try:
            data = self._load_persisted_diversions()
            if not data:
                return

            # Track IPs whose persisted rules are no longer valid so we can
            # also drop any in-memory active_rules entries for them.
            stale_ips: List[str] = []

            for ip, meta in list(data.items()):
                backend = meta.get('backend')
                action = meta.get('action')
                remove = False

                # Only iptables entries are supported now
                if backend == 'iptables' and action in ('redirect', 'block'):
                    table = meta.get('table', 'nat' if action == 'redirect' else 'filter')
                    chain = meta.get('chain', 'PREROUTING' if action == 'redirect' else 'INPUT')
                    spec = meta.get('rule_spec')
                    if not spec:
                        remove = True
                    else:
                        try:
                            res = self._run_cmd(
                                ["iptables", "-t", table, "-C", chain, *spec],
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            if res.returncode != 0:
                                remove = True
                        except Exception:
                            remove = True
                else:
                    # anything else is obsolete
                    remove = True

                if remove:
                    stale_ips.append(ip)
                    del data[ip]

            self._save_persisted_diversions(data)

            # Keep in-memory state consistent with cleaned persistence: if an IP
            # no longer has a valid underlying iptables rule, drop its rules from
            # active_rules so future operations (apply/remove) don't see ghost
            # entries that never actually apply at the kernel level.
            if stale_ips:
                with self._rules_lock:
                    for ip in stale_ips:
                        if ip in self.active_rules:
                            del self.active_rules[ip]

        except Exception:
            logger.exception('Error validating persisted nft handles')

    def _save_persisted_diversions(self, data: Dict[str, Dict]) -> None:
        path = self._diversion_state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix('.tmp')
            with tmp.open('w') as fh:
                json.dump(data, fh)
            tmp.replace(path)
        except Exception:
            logger.exception('Failed saving persisted nft handles')

    def _persist_diversion_entry(self, target_ip: str, action: str, metadata: Dict[str, Any]) -> None:
        try:
            data = self._load_persisted_diversions()
            entry = metadata.copy()
            entry['action'] = action
            data[target_ip] = entry
            self._save_persisted_diversions(data)
        except Exception:
            logger.exception('Failed persisting nft handle entry')

    def _remove_persisted_diversion(self, target_ip: str) -> None:
        try:
            data = self._load_persisted_diversions()
            if target_ip in data:
                del data[target_ip]
                self._save_persisted_diversions(data)
        except Exception:
            logger.exception('Failed removing persisted nft handle entry')

    def _restore_persisted_diversions(self) -> None:
        """Load persisted diversion metadata and populate active_rules so deletions work after restart."""
        try:
            data = self._load_persisted_diversions()
            if not data:
                return
            with self._rules_lock:
                for ip, meta in data.items():
                    action = meta.get('action')
                    backend = meta.get('backend', 'nft')
                    dest_port = meta.get('dest_port')
                    if action == 'redirect':
                        params = {
                            'backend': backend,
                            'dest_port': dest_port,
                            'canary_ip': meta.get('canary_ip')
                        }
                        if backend == 'nft':
                            params.update({
                                'nft_family': meta.get('family'),
                                'nft_table': meta.get('table'),
                                'nft_handle': meta.get('handle')
                            })
                        elif backend == 'iptables':
                            params.update({
                                'iptables_table': meta.get('table', 'nat'),
                                'iptables_chain': meta.get('chain', 'PREROUTING'),
                                'iptables_rule': meta.get('rule_spec')
                            })
                        rule = TrafficControlRule(
                            target_ip=ip,
                            action_type='redirect',
                            parameters=params
                        )
                        self.active_rules.setdefault(ip, []).append(rule)
                    elif action == 'block':
                        params = {
                            'backend': backend,
                            'method': meta.get('method', 'nft_drop'),
                            'nft_handle': meta.get('handle'),
                            'nft_family': meta.get('family'),
                            'nft_table': meta.get('table')
                        }
                        rule = TrafficControlRule(
                            target_ip=ip,
                            action_type='block',
                            parameters=params
                        )
                        self.active_rules.setdefault(ip, []).append(rule)
        except Exception:
            logger.exception('Failed restoring persisted nft handles')
    
    def _ensure_tc_setup(self):
        """tc qdisc/class構造を初期化"""
        try:
            # 既存のqdiscがあるか確認して、なければ作成する（冪等化）
            qdisc_show = self._run_cmd([
                "tc", "qdisc", "show", "dev", self.interface
            ], capture_output=True, text=True, timeout=10)

            if "htb 1:" not in self._safe_stdout(qdisc_show):
                # HTB qdisc作成（replace を優先して冪等化）
                res = self._run_cmd([
                    "tc", "qdisc", "replace", "dev", self.interface, "root",
                    "handle", "1:", "htb", "default", "30"
                ], capture_output=True, text=True, timeout=10)
                if res.returncode != 0:
                    # replace が失敗した場合は add を試す代わりに存在チェックとログ出力に留める
                    if "File exists" in self._safe_stderr(res):
                        logger.debug("HTB qdisc already exists according to tc output")
                    else:
                        logger.warning(f"tc qdisc replace failed (continuing): {self._safe_stderr(res)}")
            
            # ルートクラス作成
            config = self._load_config()
            uplink = config.get("profiles", {}).get("lte", {}).get("uplink_kbps", 5000)
            
            # ルート/デフォルト/疑わしいクラスを作成（replace を使い冪等化）
            def _ensure_class(classid: str, args: List[str]):
                try:
                    # replace を優先して実行し、存在していれば上書きすることで File exists を避ける
                    cmd = ["tc", "class", "replace", "dev", self.interface] + args
                    res = self._run_cmd(cmd, capture_output=True, text=True, timeout=10)
                    if res.returncode != 0:
                        # replace failed: log and continue. Avoid unconditional `add` to prevent RTNETLINK File exists races.
                        if "File exists" in self._safe_stderr(res):
                            logger.debug(f"TC class {classid} already exists according to tc output")
                        else:
                            logger.warning(f"tc class replace failed for {classid}: {self._safe_stderr(res)}")
                except Exception as e:
                    logger.exception(f"Failed ensuring class {classid}: {e}")

            _ensure_class("1:1", ["parent", "1:", "classid", "1:1", "htb", "rate", f"{uplink}kbit"])
            _ensure_class("1:30", ["parent", "1:1", "classid", "1:30", "htb", "rate", f"{uplink//2}kbit", "ceil", f"{uplink}kbit"])
            suspect_rate = uplink // 10  # 10%
            _ensure_class("1:40", ["parent", "1:1", "classid", "1:40", "htb", "rate", f"{suspect_rate}kbit", "ceil", f"{suspect_rate * 2}kbit", "prio", "4"])
            
            logger.info(f"TC setup completed for {self.interface}")
            
        except Exception as e:
            logger.error(f"TC setup failed: {e}")
    
    def apply_delay(self, target_ip: str, delay_ms: int) -> bool:
        """指定IPに遅延を適用"""
        try:
            # 既存の同種ルールがあれば再適用しない（冪等化）
            if target_ip in self.active_rules and any(r.action_type == "delay" for r in self.active_rules[target_ip]):
                logger.info(f"Delay already applied to {target_ip}, skip")
                return True
            # netem遅延qdisc作成
            classid = "1:41"  # 遅延専用クラス
            
            # 遅延クラス作成（replace で作成/更新、存在すればスキップ）
            cp = self._run_cmd([
                "tc", "class", "show", "dev", self.interface, "classid", classid
            ], capture_output=True, text=True, timeout=5)
            if not (cp.returncode == 0 and classid in self._safe_stdout(cp)):
                res = self._run_cmd([
                    "tc", "class", "replace", "dev", self.interface, "parent", "1:1",
                    "classid", classid, "htb", "rate", "64kbit", "ceil", "128kbit"
                ], capture_output=True, text=True, timeout=10)
                if res.returncode != 0:
                    if "File exists" in self._safe_stderr(res):
                        logger.debug(f"TC class {classid} appears to already exist")
                    else:
                        logger.warning(f"tc class replace failed for {classid}: {self._safe_stderr(res)}")

            # netem遅延qdisc追加（replace を使い冪等化）
            qdisc_show = self._run_cmd(["tc", "qdisc", "show", "dev", self.interface], capture_output=True, text=True, timeout=5)
            if f"parent {classid}" not in self._safe_stdout(qdisc_show) or "netem" not in self._safe_stdout(qdisc_show):
                res = self._run_cmd([
                    "tc", "qdisc", "replace", "dev", self.interface, "parent", classid,
                    "handle", "41:", "netem", "delay", f"{delay_ms}ms"
                ], capture_output=True, text=True, timeout=10)
                if res.returncode != 0:
                    if "File exists" in self._safe_stderr(res):
                        logger.debug("netem qdisc already exists for class")
                    else:
                        logger.warning(f"tc qdisc replace failed for netem on {classid}: {self._safe_stderr(res)}")

            # フィルタ作成（IPベース） — 既存フィルタの存在チェック
            filter_list = self._run_cmd([
                "tc", "filter", "show", "dev", self.interface, "parent", "1:"
            ], capture_output=True, text=True, timeout=5)
            if target_ip in self._safe_stdout(filter_list):
                logger.info(f"TC filter for {target_ip} already exists, skip")
            else:
                # try replace first, then fallback to add
                res = self._run_cmd([
                    "tc", "filter", "replace", "dev", self.interface, "protocol", "ip",
                    "parent", "1:", "prio", "1", "u32", "match", "ip", "src", target_ip,
                    "flowid", classid
                ], capture_output=True, text=True, timeout=10)
                if res.returncode != 0:
                    if "File exists" in self._safe_stderr(res):
                        logger.debug("TC filter appears to already exist for target")
                    else:
                        logger.warning(f"tc filter replace failed for {target_ip}: {self._safe_stderr(res)}")
            
            # ルール記録（ロック）
            rule = TrafficControlRule(
                target_ip=target_ip,
                action_type="delay",
                parameters={"delay_ms": delay_ms, "classid": classid, "prio": 1}
            )
            with self._rules_lock:
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
            # 既存の同種ルールがあれば再適用しない（冪等化）
            if target_ip in self.active_rules and any(r.action_type == "shape" for r in self.active_rules[target_ip]):
                logger.info(f"Shaping already applied to {target_ip}, skip")
                return True
            classid = "1:42"  # シェーピング専用クラス
            
            # シェーピングクラス作成（replace を優先、add をフォールバック）
            res = self._run_cmd([
                "tc", "class", "replace", "dev", self.interface, "parent", "1:1",
                "classid", classid, "htb", "rate", f"{rate_kbps}kbit", 
                "ceil", f"{rate_kbps}kbit"
            ], capture_output=True, text=True, timeout=10)
            if res.returncode != 0:
                if "File exists" in self._safe_stderr(res):
                    logger.debug(f"TC class {classid} already exists for shaping")
                else:
                    logger.warning(f"tc class replace failed for shaping {classid}: {self._safe_stderr(res)}")

            # フィルタ作成 (replace -> add)
            resf = self._run_cmd([
                "tc", "filter", "replace", "dev", self.interface, "protocol", "ip",
                "parent", "1:", "prio", "2", "u32", "match", "ip", "src", target_ip,
                "flowid", classid
            ], capture_output=True, text=True, timeout=10)
            if resf.returncode != 0:
                if "File exists" in self._safe_stderr(resf):
                    logger.debug("TC filter already exists for shaping")
                else:
                    logger.warning(f"tc filter replace failed for shaping {target_ip}: {self._safe_stderr(resf)}")
            
            # ルール記録（ロック）
            rule = TrafficControlRule(
                target_ip=target_ip,
                action_type="shape",
                parameters={"rate_kbps": rate_kbps, "classid": classid, "prio": 2}
            )
            with self._rules_lock:
                if target_ip not in self.active_rules:
                    self.active_rules[target_ip] = []
                self.active_rules[target_ip].append(rule)
            
            logger.info(f"Shaping {rate_kbps}kbps applied to {target_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply shaping to {target_ip}: {e}")
            return False

    def _try_add_nft_dnat(self, target_ip: str, canary_ip: str, dest_port: Optional[int]) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        # nft support removed: this function is obsolete
        return False, None, "nft support removed"

    def _try_add_iptables_dnat(self, target_ip: str, canary_ip: str, dest_port: Optional[int]) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Attempt to add DNAT rule via legacy iptables."""
        table = "nat"
        chain = "PREROUTING"
        rule_spec: List[str] = ["-s", target_ip]
        if dest_port:
            rule_spec += ["-p", "tcp", "--dport", str(dest_port)]
            to_dest = f"{canary_ip}:{dest_port}"
        else:
            to_dest = canary_ip
        rule_spec += ["-j", "DNAT", "--to-destination", to_dest]

        try:
            check = self._run_cmd(["iptables", "-t", table, "-C", chain, *rule_spec], capture_output=True, text=True, timeout=5)
            if check.returncode == 0:
                params = {
                    "backend": "iptables",
                    "iptables_table": table,
                    "iptables_chain": chain,
                    "iptables_rule": list(rule_spec),
                    "dest_port": dest_port,
                    "canary_ip": canary_ip,
                }
                return True, params, ""
        except Exception:
            # treat as needing to add rule; actual failure will surface on add
            pass

        try:
            add_cmd = ["iptables", "-t", table, "-I", chain, "1", *rule_spec]
            result = self._run_cmd(add_cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                params = {
                    "backend": "iptables",
                    "iptables_table": table,
                    "iptables_chain": chain,
                    "iptables_rule": list(rule_spec),
                    "dest_port": dest_port,
                    "canary_ip": canary_ip,
                }
                return True, params, ""
            err = self._safe_stderr(result) or self._safe_stdout(result) or "iptables DNAT failed"
            return False, None, err
        except Exception as e:
            return False, None, str(e)

    def _record_redirect_rule(self, target_ip: str, parameters: Dict[str, Any]) -> None:
        """Register redirect rule in memory and persist metadata for cleanup.

        To avoid stale/duplicate redirect entries, we keep at most one
        redirect rule per IP in active_rules and always overwrite with the
        latest parameters.
        """
        rule = TrafficControlRule(
            target_ip=target_ip,
            action_type="redirect",
            parameters=parameters,
        )
        with self._rules_lock:
            existing = self.active_rules.get(target_ip, [])
            # Drop any previous redirect entries for this IP; other action
            # types (delay/shape/block) are left untouched.
            existing = [r for r in existing if r.action_type != "redirect"]
            existing.append(rule)
            self.active_rules[target_ip] = existing
        # Only iptables backend is supported now
        backend = parameters.get("backend", "iptables")
        try:
            if backend == "iptables":
                rule_spec = parameters.get("iptables_rule")
                if rule_spec:
                    self._persist_diversion_entry(target_ip, 'redirect', {
                        'backend': 'iptables',
                        'table': parameters.get('iptables_table', 'nat'),
                        'chain': parameters.get('iptables_chain', 'PREROUTING'),
                        'rule_spec': rule_spec,
                        'dest_port': parameters.get('dest_port'),
                        'canary_ip': parameters.get('canary_ip')
                    })
                    logger.info(f"Persisted iptables redirect metadata for {target_ip} -> {parameters.get('canary_ip')} (rule={rule_spec})")
        except Exception:
            logger.exception('Failed persisting redirect metadata')

    def _remove_iptables_dnat_rule(self, target_ip: str, params: Dict[str, Any]) -> bool:
        table = params.get("iptables_table", "nat")
        chain = params.get("iptables_chain", "PREROUTING")
        rule_spec = params.get("iptables_rule")
        if not rule_spec:
            logger.warning(f"No iptables rule spec stored for {target_ip}")
            return False
        try:
            res = self._run_cmd(["iptables", "-t", table, "-D", chain, *rule_spec], capture_output=True, text=True, timeout=10)
            if res.returncode != 0:
                logger.warning(f"iptables delete failed for {target_ip}: {self._safe_stderr(res)} {self._safe_stdout(res)}")
                return False
            logger.info(f"Removed iptables DNAT rule for {target_ip}")
            return True
        except Exception as e:
            logger.error(f"Failed removing iptables DNAT rule for {target_ip}: {e}")
            return False

    def _remove_iptables_block_rule(self, target_ip: str, params: Dict[str, Any]) -> bool:
        """Remove iptables DROP rule for block action"""
        table = params.get("iptables_table", "filter")
        chain = params.get("iptables_chain", "INPUT")
        rule_spec = params.get("iptables_rule")
        if not rule_spec:
            logger.warning(f"No iptables block rule spec stored for {target_ip}")
            return False
        try:
            res = self._run_cmd(["iptables", "-t", table, "-D", chain, *rule_spec], capture_output=True, text=True, timeout=10)
            if res.returncode != 0:
                logger.warning(f"iptables delete block failed for {target_ip}: {self._safe_stderr(res)} {self._safe_stdout(res)}")
                return False
            logger.info(f"Removed iptables DROP rule for {target_ip}")
            return True
        except Exception as e:
            logger.error(f"Failed removing iptables DROP rule for {target_ip}: {e}")
            return False
    
    def _is_ipv6(self, ip: str) -> bool:
        """Simple IPv6 detection (presence of ':' without IPv4 dot notation)."""
        return ":" in ip and not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip)

    def apply_dnat_redirect(self, target_ip: str, dest_port: Optional[int] = None) -> bool:
        """指定IPをOpenCanaryにDNAT転送"""
        try:
            canary_ip = load_opencanary_ip()

            if self._is_ipv6(target_ip):
                logger.info(f"Skipping DNAT redirect for IPv6 address {target_ip}")
                return False
            # Operate using legacy iptables DNAT only.
            # nft support on this host has been unreliable; prefer deterministic iptables behavior
            # and persist iptables rule metadata for cleanup.
            iptables_ok, iptables_params, iptables_error = self._try_add_iptables_dnat(target_ip, canary_ip, dest_port)
            if iptables_ok and iptables_params:
                self._record_redirect_rule(target_ip, iptables_params)
                logger.info(f"DNAT redirect (iptables): {target_ip} -> {canary_ip}" + (f":{dest_port}" if dest_port else ""))
                return True

            logger.error(f"Failed to apply DNAT redirect to {target_ip} via iptables: {iptables_error}")
            return False
        except Exception as e:
            logger.error(f"Failed to apply DNAT redirect to {target_ip}: {e}")
            return False
    
    def apply_suspect_classification(self, target_ip: str) -> bool:
        """攻撃者IPをsuspectクラスに分類（低優先度・低帯域）"""
        try:
            classid = "1:40"  # suspect クラス（既にsetupで作成済み）
            # フィルタ作成（全トラフィックをsuspectクラスに）
            # 既存フィルタの存在チェック
            filter_list = self._run_cmd([
                "tc", "filter", "show", "dev", self.interface, "parent", "1:"
            ], capture_output=True, text=True, timeout=5)
            if target_ip in self._safe_stdout(filter_list):
                logger.info(f"Suspect TC filter for {target_ip} already exists, skip")
            else:
                # try replace first, then fallback to add (handle File exists gracefully)
                res = self._run_cmd([
                    "tc", "filter", "replace", "dev", self.interface, "protocol", "ip",
                    "parent", "1:", "prio", "4", "u32", "match", "ip", "src", target_ip,
                    "flowid", classid
                ], capture_output=True, text=True, timeout=10)
                if res.returncode != 0:
                    if "File exists" in self._safe_stderr(res):
                        logger.debug("Suspect TC filter already exists according to tc output")
                    else:
                        logger.warning(f"tc filter replace failed for suspect class on {target_ip}: {self._safe_stderr(res)}")
            
            # ルール記録
            rule = TrafficControlRule(
                target_ip=target_ip,
                action_type="suspect_qos",
                parameters={"classid": classid, "priority": 4}
            )
            with self._rules_lock:
                if target_ip not in self.active_rules:
                    self.active_rules[target_ip] = []
                self.active_rules[target_ip].append(rule)
            
            logger.info(f"Suspect classification applied to {target_ip} (low priority/bandwidth)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply suspect classification to {target_ip}: {e}")
            return False

    def apply_block(self, target_ip: str) -> bool:
        """
        即時ブロック適用（例外遮断用）
        delay_ms=0, block=True相当の動作をnftablesで実現
        """
        try:
            # Implement block using iptables DROP rule (INPUT chain)
            # Idempotent check
            rule_spec = ["-s", target_ip, "-j", "DROP"]
            check = self._run_cmd(["iptables", "-t", "filter", "-C", "INPUT", *rule_spec], capture_output=True, text=True, timeout=5)
            if check.returncode == 0:
                logger.info(f"Block rule already exists for {target_ip}")
                # ensure it's recorded in memory
                rule = TrafficControlRule(target_ip=target_ip, action_type="block", parameters={"backend": "iptables", "iptables_table": "filter", "iptables_chain": "INPUT", "iptables_rule": rule_spec})
                with self._rules_lock:
                    self.active_rules.setdefault(target_ip, []).append(rule)
                return True

            # Add DROP rule to INPUT chain
            res = self._run_cmd(["iptables", "-t", "filter", "-I", "INPUT", "1", *rule_spec], capture_output=True, text=True, timeout=10)
            if res.returncode != 0:
                logger.error(f"iptables DROP add failed: {self._safe_stderr(res)} {self._safe_stdout(res)}")
                return False

            logger.info(f"Exception block applied: {target_ip} (iptables DROP)")

            # Record rule and persist
            rule = TrafficControlRule(target_ip=target_ip, action_type="block", parameters={"backend": "iptables", "iptables_table": "filter", "iptables_chain": "INPUT", "iptables_rule": rule_spec})
            with self._rules_lock:
                self.active_rules.setdefault(target_ip, []).append(rule)
            try:
                self._persist_diversion_entry(target_ip, 'block', {
                    'backend': 'iptables',
                    'table': 'filter',
                    'chain': 'INPUT',
                    'rule_spec': rule_spec
                })
            except Exception:
                logger.exception('Failed persisting iptables block rule')

            return True
        
        except subprocess.CalledProcessError as e:
            logger.error(f"nft block failed for {target_ip}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in apply_block for {target_ip}: {e}")
            return False

    def apply_combined_action(self, target_ip: str, mode: str) -> bool:
        """モードに応じた複合アクションを適用"""
        config = self._load_config()
        actions = config.get("actions", {})
        fallback_presets = {
            "shield": {"delay_ms": 200, "shape_kbps": 128},
            "lockdown": {"delay_ms": 150, "shape_kbps": 64},
        }
        preset = actions.get(mode, {}) or fallback_presets.get(mode, {})

        if not preset:
            logger.warning(f"No action preset for mode: {mode}")
            return False
        
        # normal モードの場合は全ルールを削除
        if mode == "normal":
            logger.info(f"Normal mode: removing all rules for {target_ip}")
            return self.remove_rules_for_ip(target_ip)
        
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
        # スレッドセーフに active_rules をスナップして削除
        with self._rules_lock:
            if target_ip not in self.active_rules:
                logger.info(f"No active rules for {target_ip}")
                return True
            rules_to_remove = list(self.active_rules[target_ip])
            del self.active_rules[target_ip]

        success = True
        for rule in rules_to_remove:
            try:
                if rule.action_type in ["delay", "shape"]:
                    # tcルール削除（個別クラス）
                    classid = rule.parameters.get("classid")
                    prio = str(rule.parameters.get("prio", 1 if rule.action_type == "delay" else 2))
                    if classid and classid not in ["1:40"]:  # suspectクラスではない場合のみ削除
                        # フィルタ削除
                        self._run_cmd([
                            "tc", "filter", "del", "dev", self.interface,
                            "protocol", "ip", "parent", "1:", "prio", prio
                        ], capture_output=True, timeout=10)

                        # クラス削除
                        self._run_cmd([
                            "tc", "class", "del", "dev", self.interface,
                            "classid", classid
                        ], capture_output=True, timeout=10)

                elif rule.action_type == "suspect_qos":
                    # suspectクラスフィルタ削除
                    self._run_cmd([
                        "tc", "filter", "del", "dev", self.interface,
                        "protocol", "ip", "parent", "1:", "prio", "4"
                    ], capture_output=True, timeout=10)

                elif rule.action_type == "redirect":
                    backend = rule.parameters.get("backend", "nft")
                    if backend == "iptables":
                        if self._remove_iptables_dnat_rule(target_ip, rule.parameters):
                            try:
                                self._remove_persisted_diversion(target_ip)
                            except Exception:
                                logger.exception('Failed removing persisted iptables diversion')
                        continue
                    else:
                        logger.warning(f"Unknown backend for redirect removal: {backend}")

                elif rule.action_type == "block":
                    # iptables DROP rule removal
                    if self._remove_iptables_block_rule(target_ip, rule.parameters):
                        try:
                            self._remove_persisted_diversion(target_ip)
                        except Exception:
                            logger.exception('Failed removing persisted iptables block after deletion')

            except Exception as e:
                logger.error(f"Failed to remove rule {rule.action_type} for {target_ip}: {e}")
                success = False

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
            # Try both ip nat and inet azazel tables
            candidates = [("ip", "nat"), ("inet", "azazel")]
            import re
            for family, table in candidates:
                try:
                    result = self._run_cmd(["nft", "-a", "list", "table", family, table], capture_output=True, text=True, timeout=10)
                except Exception:
                    continue
                if result.returncode != 0:
                    continue

                for line in self._safe_stdout(result).split('\n'):
                    if search_pattern in line and "handle" in line:
                        part = line.split("handle")[-1].strip()
                        part = part.strip().strip(',;')
                        m = re.search(r"(\d+)", part)
                        if m:
                            handle = m.group(1)
                            try:
                                delete_cmd = ["nft", "delete", "rule", family, table, "prerouting", "handle", handle]
                                self._run_cmd(delete_cmd, capture_output=True, timeout=10)
                                logger.info(f"Deleted nft rule handle {handle} from {family} {table}")
                            except Exception:
                                logger.exception(f"Failed deleting nft rule handle {handle}")
                            return True

            return False
            
        except Exception as e:
            logger.error(f"Failed to remove nft DNAT rule: {e}")
            return False
    
    def _remove_nft_drop_rule(self, target_ip: str) -> bool:
        """nftables dropルールを削除（例外遮断解除用）"""
        try:
            search_pattern = f"ip saddr {target_ip} drop"
            
            # ルール一覧取得
            result = self._run_cmd([
                "nft", "-a", "list", "chain", "inet", "azazel", "prerouting"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                logger.warning(f"nft chain prerouting not found (may not exist)")
                return False
            
            # 該当ルールのハンドルを探す
            for line in self._safe_stdout(result).split('\n'):
                if search_pattern in line and "handle" in line:
                    handle = line.split("handle")[-1].strip()
                    if handle.isdigit():
                        # ルール削除
                        delete_cmd = [
                            "nft", "delete", "rule", "inet", "azazel", "prerouting", 
                            "handle", handle
                        ]
                        self._run_cmd(delete_cmd, check=True, timeout=10)
                        logger.info(f"Removed nft drop rule for {target_ip} (handle {handle})")
                        # remove persisted record if any
                        try:
                            self._remove_persisted_diversion(target_ip)
                        except Exception:
                            logger.exception('Failed removing persisted nft handle after drop deletion')
                        return True
            
            logger.info(f"No drop rule found for {target_ip}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to remove nft drop rule for {target_ip}: {e}")
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
        with self._rules_lock:
            return {k: list(v) for k, v in self.active_rules.items()}

    def _cleanup_loop(self) -> None:
        """Background loop to periodically cleanup expired rules."""
        while True:
            try:
                time.sleep(self._cleanup_interval)
                try:
                    cleaned = self.cleanup_expired_rules(max_age_seconds=self._max_rule_age)
                    if cleaned:
                        logger.info(f"Periodic cleanup removed {cleaned} rule sets")
                except Exception:
                    logger.exception("Error during periodic cleanup")
            except Exception:
                # Protect thread from dying on unexpected errors
                logger.exception("Cleanup loop encountered an error; continuing")
    
    def get_stats(self) -> Dict[str, any]:
        """統計情報を取得"""
        total_rules = sum(len(rules) for rules in self.active_rules.values())
        
        return {
            "active_ips": len(self.active_rules),
            "total_rules": total_rules,
            "interface": self.interface,
            "tracked_diversions": len(self.active_rules),
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


def make_completed_process(cmd, returncode=0, stdout="", stderr=""):
    """Convenience factory that returns a subprocess.CompletedProcess-like object
    suitable for injecting into tests. Uses subprocess.CompletedProcess under the hood.

    Args:
        cmd: the command list or string (kept in the CompletedProcess.args)
        returncode: integer exit code
        stdout: string to present as stdout
        stderr: string to present as stderr

    Returns:
        subprocess.CompletedProcess instance
    """
    try:
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)
    except Exception:
        # Fallback to a tiny dummy object if CompletedProcess construction fails
        class _Dummy:
            def __init__(self, args, rc, out, err):
                self.args = args
                self.returncode = rc
                self.stdout = out
                self.stderr = err

        return _Dummy(cmd, returncode, stdout, stderr)
