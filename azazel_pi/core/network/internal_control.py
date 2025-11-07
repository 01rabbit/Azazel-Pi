"""Internal network control skeleton.

Phase 1 provides in-memory zone management based on config and host scores.
Integration points:
 - Suricata/OpenCanary ingest can call `update_host_score`.
 - Periodic evaluation yields desired zone -> action mapping.
Future: apply nft/fwmark adjustments directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


@dataclass
class HostState:
    ip: str
    zone: str
    score: float = 0.0
    last_update: float = field(default_factory=time.time)


class InternalControlManager:
    def __init__(self, config: Dict):
        self.config = config
        self.hosts: Dict[str, HostState] = {}
        self.default_zone = "guest"
        zones_cfg = config.get("internal_control", {}).get("zones", {})
        if "trusted" not in zones_cfg:
            # minimal default zones if not present
            self.config.setdefault("internal_control", {}).setdefault(
                "zones", {"trusted": {"default_action": "portal"}, "guest": {"default_action": "shield"}, "quarantined": {"default_action": "lockdown"}}
            )

    def current_zone(self, ip: str) -> str:
        return self.hosts.get(ip, HostState(ip, self.default_zone)).zone

    def update_host_score(self, ip: str, score: float) -> None:
        state = self.hosts.get(ip)
        if state is None:
            state = HostState(ip=ip, zone=self.default_zone, score=score)
            self.hosts[ip] = state
        else:
            state.score = score
            state.last_update = time.time()

    def evaluate_transitions(self) -> List[HostState]:
        icfg = self.config.get("internal_control", {})
        esc = icfg.get("escalation", {})
        q_thr = esc.get("guest_to_quarantine", 60)
        release_thr = esc.get("quarantine_release_score", 30)
        changed: List[HostState] = []
        for host in self.hosts.values():
            prev_zone = host.zone
            if host.zone == "guest" and host.score >= q_thr:
                host.zone = "quarantined"
            elif host.zone == "quarantined" and host.score < release_thr:
                host.zone = "guest"
            if host.zone != prev_zone:
                changed.append(host)
        return changed

    def planned_actions(self) -> Dict[str, str]:
        zones_cfg = self.config.get("internal_control", {}).get("zones", {})
        actions: Dict[str, str] = {}
        for ip, hs in self.hosts.items():
            action = zones_cfg.get(hs.zone, {}).get("default_action", "shield")
            actions[ip] = action
        return actions


__all__ = ["InternalControlManager", "HostState"]
