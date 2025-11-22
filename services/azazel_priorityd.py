#!/usr/bin/env python3
"""Adaptive internal priority daemon (Phase 1 stub).
Reads scores from runtime/scores.json and maps them to QoS classes based on
config thresholds and dynamic bias. Future work will apply nft marks directly.
"""
from __future__ import annotations
import json, yaml, time, os, sys
from typing import Dict

CFG = "configs/network/azazel.yaml"
SCORES = "runtime/scores.json"
INTERVAL = int(os.getenv("PRIORITY_INTERVAL", "5"))


def load_yaml(path: str) -> Dict:
    with open(path, "r") as h:
        return yaml.safe_load(h)


def load_json(path: str) -> Dict:
    with open(path, "r") as h:
        return json.load(h)


def pri2cls(p: int, thr: Dict) -> str:
    if p >= 90:
        return thr["ge_90"]
    if p >= 60:
        return thr["ge_60"]
    if p >= 30:
        return thr["ge_30"]
    return thr["lt_30"]


def compute_assignments(scores: Dict[str, float], cfg: Dict) -> Dict[str, str]:
    bias = cfg.get("dynamic_bias", {})
    thr = cfg.get("priority_thresholds") or cfg.get("thresholds", {})
    factor = bias.get("factor", 0.5)
    max_delta = bias.get("max_delta", 80)
    min_priority = bias.get("min_priority", 10)
    assigns: Dict[str, str] = {}
    for ip, raw in scores.items():
        try:
            s = float(raw)
        except ValueError:
            continue
        base = 100.0
        delta = min(max_delta, factor * s)
        pri = max(min_priority, base - delta)
        assigns[ip] = pri2cls(int(pri), thr)
    return assigns


def main_loop(interval: int) -> None:
    while True:
        try:
            cfg = load_yaml(CFG)
            scores = load_json(SCORES) if os.path.exists(SCORES) else {}
            assigns = compute_assignments(scores, cfg)
            # Phase 1: just print mapping (future: nft vmap/class adjustments)
            print(f"assignments={assigns}")
        except Exception as e:  # pragma: no cover - resilience path
            print(f"error:{e}", file=sys.stderr)
        time.sleep(interval)


if __name__ == "__main__":
    main_loop(INTERVAL)
