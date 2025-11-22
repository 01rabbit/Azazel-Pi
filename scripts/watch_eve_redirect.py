#!/usr/bin/env python3
"""
Suricataのeve.jsonを監視し、不正SSH検知元をiptablesでOpenCanary(2222/TCP)へREDIRECTするスクリプト。
要件:
  - iptablesのみ使用（nftables非対応）
  - 外部IFはデフォルトeth0（引数で変更可）
  - コメント "SSH_HONEYPOT_<IP>" でルールを識別
  - 一定時間アラートが無ければルール削除
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


COMMENT_PREFIX = "SSH_HONEYPOT_"
ACCEPT_COMMENT = "SSH_HONEYPOT_ACCEPT"
DEFAULT_TARGET = "127.0.0.1:2222"  # fallback
REDIRECT_PORT = 2222
SSH_PORT = 22
# current DNAT target (host:port) – initialized at startup
TARGET_DEST = DEFAULT_TARGET


def log(msg: str, log_file: Optional[Path]) -> None:
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    line = f"[{timestamp}] {msg}"
    print(line)
    if log_file:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:  # best effort
            print(f"[warn] failed to write log file: {e}", file=sys.stderr)


def run_iptables(args: List[str], dry_run: bool) -> subprocess.CompletedProcess:
    if dry_run:
        print("DRY-RUN:", " ".join(args))
        return subprocess.CompletedProcess(args, 0, "", "")
    return subprocess.run(args, capture_output=True, text=True, timeout=10)


def build_rule_spec(ip: str, iface: str) -> List[str]:
    comment = f"{COMMENT_PREFIX}{ip}"
    return [
        "-i",
        iface,
        "-p",
        "tcp",
        "-s",
        ip,
        "--dport",
        str(SSH_PORT),
        "-j",
        "DNAT",
        "--to-destination",
        TARGET_DEST,
        "-m",
        "comment",
        "--comment",
        comment,
    ]


def build_accept_rule_args(iface: str) -> List[str]:
    return [
        "-I",
        "INPUT",
        "1",
        "-i",
        iface,
        "-p",
        "tcp",
        "--dport",
        str(REDIRECT_PORT),
        "-m",
        "conntrack",
        "--ctstate",
        "DNAT",
        "-j",
        "ACCEPT",
        "-m",
        "comment",
        "--comment",
        ACCEPT_COMMENT,
    ]


def rule_exists(ip: str, iface: str, iptables_path: str) -> bool:
    args = [iptables_path, "-t", "nat", "-C", "PREROUTING"] + build_rule_spec(ip, iface)
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode == 0


def accept_rule_exists(iface: str, iptables_path: str) -> bool:
    args = [iptables_path, "-C"] + build_accept_rule_args(iface)[1:]
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode == 0


def ensure_accept_rule(iface: str, iptables_path: str, dry_run: bool, log_file: Optional[Path]) -> None:
    if accept_rule_exists(iface, iptables_path):
        return
    args = [iptables_path] + build_accept_rule_args(iface)
    proc = run_iptables(args, dry_run)
    if proc.returncode == 0:
        log(f"[add] INPUT accept for DNATed 2222 ({iface})", log_file)
    else:
        log(f"[error] failed to ensure INPUT accept: {proc.stderr.strip()}", log_file)


def _detect_container_ip(container: str = "azazel_opencanary") -> Optional[str]:
    try:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}", container],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            ip = proc.stdout.strip()
            if ip:
                return ip
    except Exception:
        return None
    return None


def _parse_target(target: str) -> Tuple[str, str]:
    if ":" in target:
        host, port = target.rsplit(":", 1)
    else:
        host, port = target, str(REDIRECT_PORT)
    return host, port


def _cleanup_rules_with_comment(table: Optional[str], comment: str, iptables_path: str, dry_run: bool, log_file: Optional[Path]) -> int:
    """Remove existing rules that contain the given comment."""
    args = [iptables_path]
    if table:
        args += ["-t", table]
    args += ["-S"]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        log(f"[warn] failed to list rules for cleanup: {e}", log_file)
        return 0

    removed = 0
    for line in proc.stdout.splitlines():
        if comment not in line:
            continue
        try:
            tokens = shlex.split(line.strip())
            if not tokens:
                continue
            tokens[0] = "-D"  # replace -A
            del_args = [iptables_path]
            if table:
                del_args += ["-t", table]
            del_args += tokens
            res = run_iptables(del_args, dry_run)
            if res.returncode == 0:
                removed += 1
        except Exception:
            continue
    if removed:
        log(f"[cleanup] removed {removed} rule(s) with comment '{comment}' from {table or 'filter'}", log_file)
    return removed


def _cleanup_rules_containing(table: Optional[str], needle: str, iptables_path: str, dry_run: bool, log_file: Optional[Path]) -> int:
    """Remove existing rules whose text contains the needle."""
    args = [iptables_path]
    if table:
        args += ["-t", table]
    args += ["-S"]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        log(f"[warn] failed to list rules for cleanup: {e}", log_file)
        return 0

    removed = 0
    for line in proc.stdout.splitlines():
        if needle not in line:
            continue
        try:
            tokens = shlex.split(line.strip())
            if not tokens:
                continue
            tokens[0] = "-D"
            del_args = [iptables_path]
            if table:
                del_args += ["-t", table]
            del_args += tokens
            res = run_iptables(del_args, dry_run)
            if res.returncode == 0:
                removed += 1
        except Exception:
            continue
    if removed:
        log(f"[cleanup] removed {removed} rule(s) containing '{needle}' from {table or 'filter'}", log_file)
    return removed


def cleanup_existing_rules(iptables_path: str, dry_run: bool, log_file: Optional[Path]) -> None:
    """Clear old honeypot redirect/accept rules on startup."""
    _cleanup_rules_with_comment("nat", COMMENT_PREFIX, iptables_path, dry_run, log_file)
    _cleanup_rules_with_comment(None, ACCEPT_COMMENT, iptables_path, dry_run, log_file)
    # Legacy 172.16.10.10 DNAT (bridge IP時代) を除去
    _cleanup_rules_containing("nat", "172.16.10.10", iptables_path, dry_run, log_file)
    # 誤った 127.0.0.1:22 DNAT も除去
    _cleanup_rules_containing("nat", "127.0.0.1:22", iptables_path, dry_run, log_file)


def add_rule(ip: str, iface: str, iptables_path: str, dry_run: bool, log_file: Optional[Path]) -> None:
    args = [iptables_path, "-t", "nat", "-I", "PREROUTING", "1"] + build_rule_spec(ip, iface)
    proc = run_iptables(args, dry_run)
    if proc.returncode == 0:
        log(f"[add] redirect {ip} -> {TARGET_DEST}", log_file)
    else:
        log(f"[error] failed to add rule for {ip}: {proc.stderr.strip()}", log_file)


def delete_rule(ip: str, iface: str, iptables_path: str, dry_run: bool, log_file: Optional[Path]) -> None:
    args = [iptables_path, "-t", "nat", "-D", "PREROUTING"] + build_rule_spec(ip, iface)
    proc = run_iptables(args, dry_run)
    if proc.returncode == 0:
        log(f"[del] redirect removed for {ip}", log_file)
    else:
        log(f"[warn] failed to delete rule for {ip}: {proc.stderr.strip()}", log_file)


def match_alert(data: Dict[str, Any], sigs: set[str], cats: set[str], sids: set[int]) -> bool:
    if data.get("event_type") != "alert":
        return False
    alert = data.get("alert") or {}
    if sigs and str(alert.get("signature") or "").strip() not in sigs:
        return False
    if cats and str(alert.get("category") or "").strip() not in cats:
        return False
    if sids:
        try:
            sid = int(alert.get("signature_id"))
        except Exception:
            return False
        if sid not in sids:
            return False
    return True


def tail_lines(path: Path) -> Iterable[str]:
    """Minimal tail -F behavior (rotation tolerant)."""
    last_inode = None
    offset_end = True
    while True:
        try:
            with path.open("r", encoding="utf-8") as f:
                if offset_end:
                    f.seek(0, os.SEEK_END)
                while True:
                    line = f.readline()
                    if line:
                        yield line
                    else:
                        time.sleep(0.2)
                    # detect rotation
                    try:
                        stat = path.stat()
                        if last_inode is None:
                            last_inode = stat.st_ino
                        elif stat.st_ino != last_inode:
                            last_inode = stat.st_ino
                            offset_end = False
                            break
                    except FileNotFoundError:
                        time.sleep(0.5)
                        break
        except FileNotFoundError:
            time.sleep(0.5)
            continue
        except Exception:
            time.sleep(0.5)
            continue


def cleanup_rules(
    ip_map: OrderedDict[str, float],
    now: float,
    hold_seconds: int,
    iface: str,
    iptables_path: str,
    dry_run: bool,
    log_file: Optional[Path],
) -> None:
    to_delete = [ip for ip, ts in list(ip_map.items()) if now - ts > hold_seconds]
    for ip in to_delete:
        delete_rule(ip, iface, iptables_path, dry_run, log_file)
        ip_map.pop(ip, None)


def enforce_max_ips(
    ip_map: OrderedDict[str, float],
    max_ips: int,
    iface: str,
    iptables_path: str,
    dry_run: bool,
    log_file: Optional[Path],
) -> None:
    while len(ip_map) > max_ips:
        ip, _ = ip_map.popitem(last=False)
        delete_rule(ip, iface, iptables_path, dry_run, log_file)


def main() -> int:
    parser = argparse.ArgumentParser(description="Suricata SSH alert -> iptables redirect to OpenCanary")
    parser.add_argument("--eve-path", default="/var/log/suricata/eve.json")
    parser.add_argument("--iface", default="eth0")
    parser.add_argument("--iptables", default="/sbin/iptables")
    parser.add_argument("--hold-seconds", type=int, default=600)
    parser.add_argument("--max-ips", type=int, default=100)
    parser.add_argument("--signature", action="append", default=[], help="exact match of alert.signature (repeatable)")
    parser.add_argument("--category", action="append", default=[], help="exact match of alert.category (repeatable)")
    parser.add_argument("--sid", type=int, action="append", default=[], help="alert.signature_id (repeatable)")
    parser.add_argument("--log-file", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="do not execute iptables, only log")
    parser.add_argument("--skip-ensure-accept", action="store_true", help="do not add INPUT accept rule for DNATed 2222")
    parser.add_argument("--target", default="auto", help="DNAT target host:port (default: auto -> docker inspect azazel_opencanary, fallback 127.0.0.1:2222)")
    parser.add_argument("--container-name", default="azazel_opencanary", help="container to inspect when target=auto")
    args = parser.parse_args()

    sigs = {s.strip() for s in args.signature if s.strip()}
    cats = {c.strip() for c in args.category if c.strip()}
    sids = {int(s) for s in args.sid if s is not None}

    log_file = args.log_file
    ip_map: OrderedDict[str, float] = OrderedDict()
    eve_path = Path(args.eve_path)
    global TARGET_DEST
    if args.target == "auto":
        auto_ip = _detect_container_ip(args.container_name)
        if auto_ip:
            TARGET_DEST = f"{auto_ip}:{REDIRECT_PORT}"
            log(f"[auto] resolved container {args.container_name} -> {TARGET_DEST}", log_file)
        else:
            TARGET_DEST = DEFAULT_TARGET
            log(f"[auto] failed to resolve {args.container_name}; fallback {TARGET_DEST}", log_file)
    else:
        host, port = _parse_target(args.target)
        TARGET_DEST = f"{host}:{port}"
        log(f"[config] using target {TARGET_DEST}", log_file)

    log(f"start watching {eve_path} (iface={args.iface}, hold={args.hold_seconds}s, max_ips={args.max_ips}, target={TARGET_DEST})", log_file)

    # 初期化: 過去のリダイレクト/ACCEPTルールを掃除
    cleanup_existing_rules(args.iptables, args.dry_run, log_file)

    if not args.skip_ensure_accept:
        ensure_accept_rule(args.iface, args.iptables, args.dry_run, log_file)

    last_cleanup = 0.0
    for line in tail_lines(eve_path):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except Exception:
            continue
        if not match_alert(data, sigs, cats, sids):
            continue

        src_ip = data.get("src_ip") or data.get("srcip")
        if not src_ip:
            continue

        now = time.time()
        # update order: move to end to mark recent
        if src_ip in ip_map:
            ip_map.move_to_end(src_ip)
        ip_map[src_ip] = now

        if not rule_exists(src_ip, args.iface, args.iptables):
            add_rule(src_ip, args.iface, args.iptables, args.dry_run, log_file)

        enforce_max_ips(ip_map, args.max_ips, args.iface, args.iptables, args.dry_run, log_file)

        if now - last_cleanup > 5:
            cleanup_rules(ip_map, now, args.hold_seconds, args.iface, args.iptables, args.dry_run, log_file)
            last_cleanup = now

    return 0


if __name__ == "__main__":
    sys.exit(main())
