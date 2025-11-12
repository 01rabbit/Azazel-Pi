"""Dynamic WAN interface selection and orchestration logic."""
from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml
from azazel_pi.utils.cmd_runner import run as run_cmd

from azazel_pi.utils.wan_state import (
    InterfaceSnapshot,
    WANState,
    load_wan_state,
    save_wan_state,
    update_wan_state,
)

LOG = logging.getLogger("azazel.wan_manager")


def _repo_root() -> Path:
    # Path(__file__) -> .../azazel_pi/core/network/wan_manager.py
    # parents indices: 0=network,1=core,2=azazel_pi,3=<repo root>
    return Path(__file__).resolve().parents[3]


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProbeResult:
    """Container describing single interface health check."""

    name: str
    exists: bool
    link_up: bool
    ip_address: Optional[str]
    speed_mbps: Optional[int]
    score: float
    reason: str

    def to_snapshot(self) -> InterfaceSnapshot:
        return InterfaceSnapshot(
            name=self.name,
            link_up=self.link_up,
            ip_address=self.ip_address,
            speed_mbps=self.speed_mbps,
            score=self.score,
            reason=self.reason,
            last_checked=_now_iso(),
        )


class WANManager:
    """Monitor candidate interfaces, select the healthiest WAN and reconfigure services."""

    def __init__(
        self,
        *,
        config_path: Optional[Path] = None,
        candidates: Optional[Sequence[str]] = None,
        poll_interval: float = 20.0,
        lan_cidr: str = "172.16.0.0/24",
        state_path: Optional[Path] = None,
        services_to_restart: Optional[Sequence[str]] = None,
        traffic_init_script: Optional[Path] = None,
    ) -> None:
        self.repo_root = _repo_root()
        self.config_path = (
            Path(config_path)
            if config_path
            else Path("/etc/azazel/azazel.yaml")
        )
        # Priority for candidates:
        # 1) explicit candidates argument
        # 2) AZAZEL_WAN_CANDIDATES env var (comma-separated)
        # 3) config file (interfaces.external or interfaces.wan)
        # 4) fallback to canonical list
        if candidates:
            self.candidates = list(candidates)
        else:
            env_cands = os.environ.get("AZAZEL_WAN_CANDIDATES")
            if env_cands:
                # parse comma/space separated list
                parsed = [c.strip() for c in env_cands.replace(',', ' ').split() if c.strip()]
                self.candidates = parsed
            else:
                self.candidates = self._load_candidates()

        if not self.candidates:
            # As an absolute fallback, consider the two canonical interfaces
            self.candidates = ["wlan1", "eth0"]
        self.poll_interval = poll_interval
        self.lan_cidr = lan_cidr
        self.state_path = state_path
        self.traffic_init_script = (
            Path(traffic_init_script)
            if traffic_init_script
            else self.repo_root / "bin" / "azazel-traffic-init.sh"
        )
        self.services_to_restart = list(
            services_to_restart
            if services_to_restart
            else ["suricata.service", "azctl-unified.service"]
        )
        self.current_interface: Optional[str] = load_wan_state(
            self.state_path
        ).active_interface

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self, once: bool = False) -> int:
        """Start monitoring loop (or run a single evaluation if once=True)."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
        LOG.info(
            "Starting WAN manager (candidates=%s, interval=%ss)",
            ", ".join(self.candidates),
            self.poll_interval,
        )
        self._evaluate_cycle(initial=True)
        if once:
            return 0
        try:
            while True:
                time.sleep(self.poll_interval)
                self._evaluate_cycle(initial=False)
        except KeyboardInterrupt:
            LOG.info("WAN manager stopped via signal")
            return 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_candidates(self) -> List[str]:
        """Read external interface candidates from config file."""
        try:
            with self.config_path.open("r", encoding="utf-8") as handle:
                config = yaml.safe_load(handle) or {}
        except FileNotFoundError:
            return []
        except Exception as exc:  # pragma: no cover - config errors reported but ignored
            LOG.warning("Failed to load %s: %s", self.config_path, exc)
            return []

        interfaces = config.get("interfaces", {})
        arr = interfaces.get("external") or []
        if isinstance(arr, list) and arr:
            return [str(entry) for entry in arr]
        # Fallback to explicit WAN entry if defined
        if interfaces.get("wan"):
            return [str(interfaces["wan"])]
        return []

    def _evaluate_cycle(self, *, initial: bool) -> None:
        snapshots: List[ProbeResult] = []
        for iface in self.candidates:
            snapshots.append(self._probe_interface(iface))
        best = self._choose_best(snapshots)
        candidate_snapshots = [snap.to_snapshot() for snap in snapshots]

        if not best:
            msg = "No viable WAN interface detected"
            update_wan_state(
                status="degraded",
                message=msg,
                candidates=candidate_snapshots,
                active_interface=None,
                path=self.state_path,
            )
            LOG.warning(msg)
            self.current_interface = None
            return

        if self.current_interface != best.name:
            LOG.info(
                "Switching WAN interface from %s to %s (%s)",
                self.current_interface or "none",
                best.name,
                best.reason,
            )
            update_wan_state(
                active_interface=best.name,
                status="reconfiguring",
                message=f"Applying network policy for {best.name}",
                candidates=candidate_snapshots,
                path=self.state_path,
            )
            self._apply_interface(best.name)
            update_wan_state(
                active_interface=best.name,
                status="ready",
                message=f"{best.name} active ({best.reason})",
                candidates=candidate_snapshots,
                path=self.state_path,
            )
            self.current_interface = best.name
        else:
            # Refresh state to confirm readiness
            update_wan_state(
                active_interface=best.name,
                status="ready",
                message=f"{best.name} healthy ({best.reason})",
                candidates=candidate_snapshots,
                path=self.state_path,
            )
            if not initial:
                LOG.debug("WAN interface %s remains active", best.name)

    def _probe_interface(self, iface: str) -> ProbeResult:
        """Gather health data for the interface."""
        exists = False
        link_up = False
        ip_addr: Optional[str] = None

        try:
            res = run_cmd(["ip", "link", "show", iface], capture_output=True, text=True, timeout=2, check=False)
            exists = res.returncode == 0
            if exists:
                link_up = "state UP" in (res.stdout or "") or "state UNKNOWN" in (res.stdout or "")
        except Exception as exc:
            LOG.debug("ip link show %s failed: %s", iface, exc)

        if exists:
            try:
                res = run_cmd(["ip", "-4", "addr", "show", iface], capture_output=True, text=True, timeout=2, check=False)
                for line in (res.stdout or "").splitlines():
                    if "inet " in line:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            ip_addr = parts[1].split("/")[0]
                            break
            except Exception as exc:
                LOG.debug("ip addr show %s failed: %s", iface, exc)

        speed = self._determine_speed(iface)
        score, reason = self._score_interface(
            iface,
            exists=exists,
            link_up=link_up,
            has_ip=ip_addr is not None,
            speed_mbps=speed,
        )

        return ProbeResult(
            name=iface,
            exists=exists,
            link_up=link_up,
            ip_address=ip_addr,
            speed_mbps=speed,
            score=score,
            reason=reason,
        )

    def _determine_speed(self, iface: str) -> Optional[int]:
        """Try multiple strategies to estimate link speed (best-effort)."""
        sysfs_path = Path(f"/sys/class/net/{iface}/speed")
        if sysfs_path.exists():
            try:
                val = sysfs_path.read_text().strip()
                if val and val.isdigit():
                    return int(val)
            except Exception:
                pass

        # ethtool fallback (mostly for wired NICs)
        try:
            res = run_cmd(["ethtool", iface], capture_output=True, text=True, timeout=2, check=False)
            for line in (res.stdout or "").splitlines():
                if "Speed:" in line and "Mb/s" in line:
                    tokens = "".join(ch for ch in line if ch.isdigit())
                    if tokens:
                        return int(tokens)
        except FileNotFoundError:
            pass
        except Exception:
            pass

        # Wi-Fi bitrate via `iw`
        try:
            res = run_cmd(["iw", "dev", iface, "link"], capture_output=True, text=True, timeout=2, check=False)
            for line in (res.stdout or "").splitlines():
                if "tx bitrate" in line.lower():
                    parts = line.split()
                    for idx, token in enumerate(parts):
                        if token.lower().startswith("mbit/s"):
                            try:
                                return int(float(parts[idx - 1]))
                            except Exception:
                                continue
        except FileNotFoundError:
            pass
        except Exception:
            pass
        return None

    def _score_interface(
        self,
        iface: str,
        *,
        exists: bool,
        link_up: bool,
        has_ip: bool,
        speed_mbps: Optional[int],
    ) -> Tuple[float, str]:
        """Generate a simple availability score and explanation."""
        reason_bits: List[str] = []
        score = 0.0
        if not exists:
            return 0.0, "interface missing"
        score += 20
        reason_bits.append("detected")

        if link_up:
            score += 40
            reason_bits.append("link up")
        else:
            reason_bits.append("link down")

        if has_ip:
            score += 25
            reason_bits.append("IP assigned")
        else:
            reason_bits.append("no IP")

        if speed_mbps:
            score += min(speed_mbps, 1000) / 10.0
            reason_bits.append(f"{speed_mbps}Mbps")

        return score, ", ".join(reason_bits)

    def _choose_best(self, probes: Iterable[ProbeResult]) -> Optional[ProbeResult]:
        best: Optional[ProbeResult] = None
        for probe in probes:
            if not probe.exists:
                continue
            if best is None or probe.score > best.score:
                best = probe
            elif best and probe.score == best.score:
                # Tie-breaker: prefer interface with IP, then higher speed
                if probe.ip_address and not (best.ip_address):
                    best = probe
                elif (
                    probe.speed_mbps or 0
                ) > (best.speed_mbps or 0):
                    best = probe
        return best

    def _apply_interface(self, iface: str) -> None:
        """Reconfigure traffic control, NAT, and dependent services."""
        self._ensure_traffic_control(iface)
        self._reapply_nat(iface)
        self._restart_services()

    def _ensure_traffic_control(self, iface: str) -> None:
        if not self.traffic_init_script.exists():
            LOG.warning("Traffic init script %s missing", self.traffic_init_script)
            return
        env = os.environ.copy()
        env["WAN_IF_OVERRIDE"] = iface
        try:
            run_cmd([str(self.traffic_init_script)], cwd=str(self.repo_root), env=env, check=True, text=True)
            LOG.info("Re-applied traffic control on %s", iface)
        except subprocess.CalledProcessError as exc:
            LOG.error("Traffic control initialization failed: %s", exc)

    def _reapply_nat(self, iface: str) -> None:
        try:
            run_cmd(["iptables", "-t", "nat", "-F"], check=True)
            run_cmd([
                    "iptables",
                    "-t",
                    "nat",
                    "-A",
                    "POSTROUTING",
                    "-s",
                    self.lan_cidr,
                    "-o",
                    iface,
                    "-j",
                    "MASQUERADE",
                ], check=True)
            LOG.info("NAT POSTROUTING updated for %s", iface)
        except FileNotFoundError:
            LOG.warning("iptables not available; skipping NAT reapply")
        except subprocess.CalledProcessError as exc:
            LOG.error("Failed to apply NAT rule: %s", exc)

    def _restart_services(self) -> None:
        for svc in self.services_to_restart:
            try:
                run_cmd(["systemctl", "try-restart", svc], check=False, timeout=30)
                LOG.info("Triggered restart for %s", svc)
            except FileNotFoundError:
                LOG.warning("systemctl not found while restarting %s", svc)
            except Exception as exc:
                LOG.error("Failed to restart %s: %s", svc, exc)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Dynamic WAN manager")
    parser.add_argument("--config", help="Path to azazel.yaml", default=None)
    parser.add_argument(
        "--candidate",
        action="append",
        dest="candidates",
        help="Explicit WAN candidate (can be repeated)",
    )
    parser.add_argument("--interval", type=float, default=20.0, help="Polling interval seconds")
    parser.add_argument("--lan-cidr", default="172.16.0.0/24")
    parser.add_argument("--state-file", help="Override WAN state file path")
    parser.add_argument("--once", action="store_true", help="Run a single evaluation and exit")
    args = parser.parse_args()

    manager = WANManager(
        config_path=Path(args.config) if args.config else None,
        candidates=args.candidates,
        poll_interval=args.interval,
        lan_cidr=args.lan_cidr,
        state_path=Path(args.state_file) if args.state_file else None,
    )
    return manager.run(once=args.once)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
