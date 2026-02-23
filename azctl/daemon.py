"""Runtime daemon glue for Azazel."""
from __future__ import annotations

import json
import math
import threading
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from azazel_edge.core import notify_config
from azazel_edge.core.enforcer.traffic_control import get_traffic_control_engine
from azazel_edge.core.hybrid_threat_evaluator import evaluate_with_hybrid_system
from azazel_edge.core.scorer import ScoreEvaluator
from azazel_edge.core.state_machine import Event, StateMachine

try:
    from azazel_edge.core.notify import build_default_notifier
except Exception:
    build_default_notifier = None


@dataclass
class AzazelDaemon:
    machine: StateMachine
    scorer: ScoreEvaluator
    # Default decisions log path aligned with CLI expectations
    decisions_log: Path = field(default_factory=lambda: Path("/var/log/azazel/decisions.log"))
    # Optional integrations
    traffic_engine: object | None = field(default_factory=lambda: get_traffic_control_engine())
    notifier: object | None = field(
        default_factory=lambda: build_default_notifier() if build_default_notifier is not None else None
    )

    def __post_init__(self) -> None:
        self._ip_control_modes: Dict[str, str] = {}
        self._diverted_ips: Dict[str, float] = {}
        # Per-IP states: score, mode, last timestamps and timers for canary/suricata
        self._ip_states: Dict[str, Dict[str, any]] = {}
        self._last_mode_snapshot: Dict[str, Any] = {
            "mode": self.machine.current_state.name,
            "average": 0.0,
            "timestamp": time.time(),
        }
        self._opencanary_endpoints = self._detect_opencanary_endpoints()
        cleanup_interval = notify_config.get("network", {}).get("cleanup_interval_seconds", 60)
        try:
            self._traffic_cleanup_interval = max(int(cleanup_interval), 5)
        except Exception:
            self._traffic_cleanup_interval = 60
        self._next_cleanup_at = time.time() + self._traffic_cleanup_interval
        # Two-stage silence timers (seconds). Allow test override via env.
        import os
        # Default silence windows control how long Azazel waits for a canary/suricata
        # observation before considering the diversion stale and removing rules.
        # Increase defaults to 5 minutes to avoid short apply/remove races during
        # active investigations or noisy environments. Operators may override via
        # environment variables AZAZEL_CANARY_SILENCE_SECONDS or AZAZEL_SURICATA_SILENCE_SECONDS.
        try:
            self._canary_silence_seconds = int(os.getenv("AZAZEL_CANARY_SILENCE_SECONDS", "300"))
        except Exception:
            self._canary_silence_seconds = 300
        try:
            self._suricata_silence_seconds = int(os.getenv("AZAZEL_SURICATA_SILENCE_SECONDS", "300"))
        except Exception:
            self._suricata_silence_seconds = 300

        # Start background monitor for per-IP 2-stage timers
        self._start_ip_state_monitor()

    def process_events(self, events: Iterable[Event]) -> None:
        entries: List[dict] = []
        for event in events:
            # Reuse single-event processing for consistent side-effects
            self.process_event(event)

    def process_event(self, event: Event) -> None:
        """Process a single Event and append a decision entry immediately.

        Prefer hybrid AI evaluation (Mock-LLM first, Ollama for low-confidence/unknown).
        Fall back to ScoreEvaluator if AI evaluation is not available or fails.
        """
        is_decay = event.name == "decay_tick"
        if event.name == "trend_sample":
            self._log_trend_snapshot()
            return

        # Handle OpenCanary events specially: update per-IP canary timestamp and return
        if event.name == "canary":
            src = getattr(event, "src_ip", None)
            if src:
                st = self._ip_states.setdefault(src, {})
                st["last_canary_ts"] = time.time()
                # cancel any pending canary evaluation
                st.pop("canary_eval_started_at", None)
            return

        alert_data = None
        if not is_decay:
            alert_data = {
                "timestamp": getattr(event, "timestamp", None),
                "signature": getattr(event, "signature", getattr(event, "name", "")),
                "severity": getattr(event, "severity", None),
                "src_ip": getattr(event, "src_ip", None),
                "dest_ip": getattr(event, "dest_ip", None),
                "proto": getattr(event, "proto", None),
                "dest_port": getattr(event, "dest_port", None),
                "details": getattr(event, "details", None),
                # Provide decisions log path so async deep eval can persist results
                "decisions_log": str(self.decisions_log) if getattr(self, 'decisions_log', None) is not None else None,
            }
            self._notify_threat(alert_data)

        previous_mode = self.machine.current_state.name
        if is_decay:
            score = 0
            classification = "decay"
        else:
            score, classification = self._compute_score(alert_data or {}, event)
            # update per-IP suricata timestamp
            src = getattr(event, "src_ip", None)
            if src:
                st = self._ip_states.setdefault(src, {})
                st["last_suricata_ts"] = time.time()
                # accumulate a simple per-ip score (max of samples)
                try:
                    st_score = int(st.get("score", 0) or 0)
                    st["score"] = max(st_score, int(score))
                except Exception:
                    st["score"] = int(score)
        evaluation = self.machine.apply_score(score)
        actions = self.machine.get_actions_preset()
        applied_mode = evaluation["applied_mode"]
        average = evaluation["average"]
        self._last_mode_snapshot = {
            "mode": applied_mode,
            "average": average,
            "timestamp": time.time(),
        }
        entry = {
            "event": event.name,
            "score": score,
            "classification": classification,
            "average": average,
            "desired_mode": evaluation["desired_mode"],
            "target_mode": evaluation["target_mode"],
            "mode": applied_mode,
            "actions": actions,
            "src_ip": getattr(event, "src_ip", None),
            "mode_snapshot": dict(self._last_mode_snapshot),
        }
        try:
            entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        except Exception:
            entry["timestamp"] = ""
        self._append_decisions([entry])

        src_ip = getattr(event, "src_ip", None)
        # AGGRESSIVE: Force shield (DNAT to OpenCanary) on ANY Suricata alert
        # This ensures immediate honeypot redirection without waiting for score thresholds
        if src_ip and not is_decay and event.name == "alert":
            # For ANY Suricata alert, immediately apply shield (DNAT) to honeypot
            try:
                st = self._ip_states.setdefault(src_ip, {})
                st["score"] = 100  # Mark as high threat for logging
                if self.traffic_engine:
                    self._ensure_diversion(src_ip, event)
                    # Get the dest_port from alert if available, for targeted DNAT
                    dest_port = getattr(event, "dest_port", None)
                    self.traffic_engine.apply_dnat_redirect(src_ip, dest_port=dest_port)
                    self.traffic_engine.apply_combined_action(src_ip, "shield")
                    self._ip_control_modes[src_ip] = "shield"
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"[AGGRESSIVE_SHIELD] Suricata alert → Immediate DNAT redirect for {src_ip} (port {dest_port})")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to apply aggressive shield for {src_ip}: {e}")
        
        # Also apply traditional score-based shield for high-scoring events
        try:
            thresholds = self.machine.get_thresholds()
            t1 = int(thresholds.get("t1", thresholds.get("t1", 50)))
        except Exception:
            t1 = 50
        if src_ip and not is_decay and event.name != "alert":  # Avoid double-processing alerts
            try:
                if classification and classification.lower() in ("exploit", "malware", "trojan") or (isinstance(score, int) and score >= t1):
                    # ensure per-ip record and force shield-mode score
                    st = self._ip_states.setdefault(src_ip, {})
                    st["score"] = max(int(st.get("score", 0) or 0), t1)
                    # apply immediate diversion and shield actions
                    try:
                        if self.traffic_engine:
                            self._ensure_diversion(src_ip, event)
                            self.traffic_engine.apply_combined_action(src_ip, "shield")
                            self._ip_control_modes[src_ip] = "shield"
                    except Exception:
                        pass
                    # Also signal a global shield transition to ensure UI/decisions reflect high threat
                    try:
                        self.machine.dispatch(Event(name="shield", severity=score))
                    except Exception:
                        pass
            except Exception:
                pass
        self._handle_mode_notification(previous_mode, applied_mode, average)
        self._handle_traffic_controls(src_ip, applied_mode, event)
        self._maybe_cleanup_rules()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _compute_score(self, alert_data: Dict[str, Any], event: Event) -> tuple[int, str]:
        """Run hybrid AI scoring, falling back to the legacy scorer."""
        try:
            ai_result = evaluate_with_hybrid_system(alert_data)
            score = self._normalize_ai_score(ai_result)
            classification = ai_result.get("category", "ai")
            return score, classification
        except Exception:
            pass

        try:
            score = self.scorer.evaluate([event])
            classification = self.scorer.classify(score)
        except Exception:
            score = 0
            classification = "unknown"
        return score, classification

    @staticmethod
    def _normalize_ai_score(ai_result: Dict[str, Any]) -> int:
        """Normalize hybrid AI output into a 0-100 integer score."""
        score = ai_result.get("score")
        if isinstance(score, (int, float)):
            return max(0, min(100, int(score)))
        risk = ai_result.get("risk")
        if isinstance(risk, (int, float)):
            return max(0, min(100, int((risk - 1) * 25)))
        raise ValueError("AI result missing score/risk fields")

    def _handle_mode_notification(self, previous: str, current: str, average: float) -> None:
        if not self.notifier or previous == current:
            return
        try:
            self.notifier.notify_mode_change(previous, current, average)
        except Exception:
            pass

    def _handle_traffic_controls(self, target_ip: str | None, applied_mode: str, event: Event | None) -> None:
        if not target_ip or not self.traffic_engine:
            return
        try:
            self._ensure_diversion(target_ip, event)
            current_applied = self._ip_control_modes.get(target_ip)
            if applied_mode == "normal" or not applied_mode:
                if current_applied:
                    self.traffic_engine.remove_rules_for_ip(target_ip)
                    self._ip_control_modes.pop(target_ip, None)
                    if target_ip in self._diverted_ips:
                        self._diverted_ips.pop(target_ip, None)
                        self._notify_redirect_change(target_ip, applied=False, inline_endpoints=self._event_endpoints(event))
                return

            if applied_mode == "portal":
                # Portal mode relies solely on DNAT diversion (no QoS shaping).
                if current_applied:
                    self.traffic_engine.remove_rules_for_ip(target_ip)
                    self._ip_control_modes.pop(target_ip, None)
                    # Re-establish diversion silently after removing QoS rules.
                    self._ensure_diversion(target_ip, event, announce=False)
                return

            if current_applied == applied_mode:
                return

            if current_applied:
                self.traffic_engine.remove_rules_for_ip(target_ip)
                self._ip_control_modes.pop(target_ip, None)

            if self.traffic_engine.apply_combined_action(target_ip, applied_mode):
                self._ip_control_modes[target_ip] = applied_mode
        except Exception:
            pass

    def _ensure_diversion(self, target_ip: str, event: Event | None, announce: bool = True) -> None:
        if not self.traffic_engine:
            return
        now = time.time()
        if target_ip in self._diverted_ips:
            self._diverted_ips[target_ip] = now
            return

        dest_port = getattr(event, "dest_port", None) if event else None
        proto = getattr(event, "proto", None) if event else None
        try:
            applied = self.traffic_engine.apply_dnat_redirect(target_ip, dest_port=dest_port)
            if applied:
                self._diverted_ips[target_ip] = now
                # Clear any previous canary/suricata evaluation timers to avoid
                # an immediate removal race if an evaluation was already in
                # progress for this IP. This can happen when events arrive
                # rapidly and the monitor thread had started an evaluation
                # earlier.
                try:
                    st = self._ip_states.setdefault(target_ip, {})
                    if st.pop('canary_eval_started_at', None) is not None or st.pop('suricata_eval_started_at', None) is not None:
                        # Log a debug message so operators can trace why removals were suppressed
                        try:
                            logger = __import__('logging').getLogger(__name__)
                            logger.debug(f"Cleared pending canary/suricata eval timers for {target_ip} after diversion applied")
                        except Exception:
                            pass
                except Exception:
                    pass
                if announce:
                    endpoints = self._event_endpoints(event, dest_port, proto)
                    self._notify_redirect_change(target_ip, applied=True, inline_endpoints=endpoints)
        except Exception:
            pass

    def _event_endpoints(
        self,
        event: Event | None,
        dest_port: int | None = None,
        proto: str | None = None,
    ) -> List[Dict[str, Any]]:
        if event:
            port_val = dest_port or getattr(event, "dest_port", None)
            if port_val:
                try:
                    port_int = int(port_val)
                except Exception:
                    port_int = None
                if port_int is not None:
                    proto_name = (proto or getattr(event, "proto", None) or "tcp").lower()
                    return [{"protocol": proto_name, "port": port_int}]
        return list(self._opencanary_endpoints or [])

    def _notify_redirect_change(
        self,
        target_ip: str,
        applied: bool,
        inline_endpoints: List[Dict[str, Any]] | None = None,
    ) -> None:
        if not self.notifier:
            return
        try:
            endpoints = inline_endpoints if inline_endpoints else (self._opencanary_endpoints or [])
            self.notifier.notify_redirect_change(target_ip, endpoints, applied)
        except Exception:
            pass

    def _notify_threat(self, alert_data: Dict[str, Any]) -> None:
        if not self.notifier:
            return
        if not alert_data.get("signature") or not alert_data.get("src_ip"):
            return
        try:
            self.notifier.notify_threat_detected(alert_data)
        except Exception:
            pass

    def _maybe_cleanup_rules(self) -> None:
        if not self.traffic_engine or not hasattr(self.traffic_engine, "cleanup_expired_rules"):
            return
        now = time.time()
        if now < getattr(self, "_next_cleanup_at", 0.0):
            return
        try:
            self.traffic_engine.cleanup_expired_rules()
        except Exception:
            pass
        self._next_cleanup_at = now + self._traffic_cleanup_interval

    def _log_trend_snapshot(self) -> None:
        """Persist a snapshot of the current mode/score for Trend displays."""
        metrics = self.machine.get_current_score()
        try:
            average = float(metrics.get("ewma", 0.0))
        except Exception:
            average = 0.0
        current_mode = self.machine.current_state.name
        actions = self.machine.get_actions_preset()
        snapshot = {
            "mode": current_mode,
            "average": average,
            "timestamp": time.time(),
        }
        self._last_mode_snapshot = dict(snapshot)
        entry = {
            "event": "trend_sample",
            "score": average,
            "classification": "trend",
            "average": average,
            "desired_mode": current_mode,
            "target_mode": current_mode,
            "mode": current_mode,
            "actions": actions,
            "src_ip": None,
            "mode_snapshot": dict(snapshot),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._append_decisions([entry])

    def _detect_opencanary_endpoints(self) -> List[Dict[str, Any]]:
        """Infer OpenCanary exposed ports/protocols from compose/config."""
        endpoints: List[Dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        compose_candidates = [
            Path.cwd() / "docker-compose.yaml",
            Path.cwd() / "docker-compose.yml",
            Path(__file__).resolve().parents[1] / "deploy" / "docker-compose.yaml",
            Path(__file__).resolve().parents[1] / "deploy" / "docker-compose.yml",
        ]
        for candidate in compose_candidates:
            try:
                if not candidate.exists():
                    continue
                data = yaml.safe_load(candidate.read_text()) or {}
                opencanary = data.get("services", {}).get("opencanary", {})
                for entry in opencanary.get("ports", []) or []:
                    parsed = self._parse_port_entry(entry)
                    if not parsed:
                        continue
                    key = (parsed["protocol"], parsed["port"])
                    if key in seen:
                        continue
                    seen.add(key)
                    endpoints.append(parsed)
            except Exception:
                continue
        if not endpoints:
            cfg = notify_config.get("opencanary", {}) or {}
            for port in cfg.get("ports", []):
                try:
                    port_int = int(port)
                except Exception:
                    continue
                key = ("tcp", port_int)
                if key in seen:
                    continue
                seen.add(key)
                endpoints.append({"protocol": "tcp", "port": port_int})
        return endpoints

    @staticmethod
    def _parse_port_entry(entry: Any) -> Dict[str, Any] | None:
        """Parse a docker-compose port declaration into protocol/port."""
        proto = "tcp"
        if isinstance(entry, dict):
            proto = str(entry.get("protocol") or "tcp").lower()
            target = entry.get("target") or entry.get("published") or entry.get("container_port")
            if target is None:
                return None
            try:
                return {"protocol": proto, "port": int(target)}
            except Exception:
                return None

        if isinstance(entry, str):
            value = entry
            if "/" in value:
                value, proto = value.split("/", 1)
                proto = proto or "tcp"
            parts = value.split(":")
            try:
                port = int(parts[-1])
            except Exception:
                return None
            return {"protocol": proto.lower(), "port": port}
        return None

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _append_decisions(self, entries: List[dict]) -> None:
        self.decisions_log.parent.mkdir(parents=True, exist_ok=True)
        with self.decisions_log.open("a", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, sort_keys=True))
                handle.write("\n")

                # Record last written entry and timestamp for decay logic
                try:
                    self._last_entry = dict(entry)
                    self._last_written_ts = time.time()
                except Exception:
                    pass

    def start_decay_writer(self, decay_tau: float = 120.0, check_interval: float = 5.0) -> None:
        """Start a background thread that appends decayed display entries to decisions.log.

        This writes synthetic 'decay' entries when no new events are being
        written for some time so that downstream display consumers see a
        gradually decreasing score.
        """
        # If already running, no-op
        if getattr(self, '_decay_thread', None) and getattr(self._decay_thread, 'is_alive', lambda: False)():
            return
        self._decay_stop = threading.Event()

        def _worker():
            while not (self._decay_stop and self._decay_stop.is_set()):
                try:
                    now = time.time()
                    last_ts = float(getattr(self, '_last_written_ts', 0.0) or 0.0)
                    if last_ts <= 0.0:
                        # Nothing written yet; wait
                        time.sleep(check_interval)
                        continue

                    age = max(0.0, now - last_ts)
                    if age >= check_interval:
                        try:
                            self.process_event(Event(name="decay_tick", severity=0))
                        except Exception:
                            pass
                    time.sleep(check_interval)
                except Exception:
                    # Avoid thread death on unexpected errors
                    time.sleep(check_interval)

        t = threading.Thread(target=_worker, daemon=True)
        self._decay_thread = t
        t.start()

    def stop_decay_writer(self) -> None:
        """Stop the background decay writer thread if running."""
        try:
            if getattr(self, '_decay_stop', None):
                self._decay_stop.set()
            if getattr(self, '_decay_thread', None):
                self._decay_thread.join(timeout=2.0)
        except Exception:
            pass

    def start_trend_sampler(self, interval: float = 10.0) -> None:
        """Start a background thread emitting periodic trend samples."""
        if interval <= 0:
            return
        if getattr(self, "_trend_thread", None):
            if getattr(self._trend_thread, "is_alive", lambda: False)():
                return
        self._trend_stop = threading.Event()

        def _worker():
            while not (self._trend_stop and self._trend_stop.is_set()):
                try:
                    time.sleep(interval)
                    self.process_event(Event(name="trend_sample", severity=0))
                except Exception:
                    time.sleep(interval)

        t = threading.Thread(target=_worker, daemon=True, name="azazel-trend-sampler")
        self._trend_thread = t
        t.start()

    def stop_trend_sampler(self) -> None:
        try:
            if getattr(self, "_trend_stop", None):
                self._trend_stop.set()
            if getattr(self, "_trend_thread", None):
                self._trend_thread.join(timeout=2.0)
        except Exception:
            pass

    def start_periodic_cleanup(self, interval_seconds: int = 60, max_age_seconds: int = 3600) -> None:
        """Start a background thread that periodically cleans expired traffic rules.

        This keeps the TrafficControlEngine's active rules trimmed during demos
        without requiring an external scheduler.
        """
        if not getattr(self, '_cleanup_thread', None):
            self._cleanup_stop = threading.Event()

            def _worker():
                while not (self._cleanup_stop and self._cleanup_stop.is_set()):
                    try:
                        if self.traffic_engine:
                            try:
                                self.traffic_engine.cleanup_expired_rules(max_age_seconds)
                            except Exception:
                                pass
                        time.sleep(interval_seconds)
                    except Exception:
                        time.sleep(interval_seconds)

            t = threading.Thread(target=_worker, daemon=True)
            self._cleanup_thread = t
            t.start()

    def stop_periodic_cleanup(self) -> None:
        try:
            if getattr(self, '_cleanup_stop', None):
                self._cleanup_stop.set()
            if getattr(self, '_cleanup_thread', None):
                self._cleanup_thread.join(timeout=2.0)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Per-IP state monitor (2-stage canary -> suricata silence handling)
    # ------------------------------------------------------------------
    def _start_ip_state_monitor(self) -> None:
        if getattr(self, '_ip_state_thread', None) and getattr(self._ip_state_thread, 'is_alive', lambda: False)():
            return
        self._ip_state_stop = threading.Event()

        def _worker():
            while not (self._ip_state_stop and self._ip_state_stop.is_set()):
                try:
                    now = time.time()
                    # iterate copy to avoid mutation during loop
                    for ip, st in list(self._ip_states.items()):
                        try:
                            # If IP is currently diverted, check canary silence
                            diverted = ip in self._diverted_ips
                            last_canary = st.get('last_canary_ts')
                            canary_eval = st.get('canary_eval_started_at')
                            if diverted:
                                # No canary seen for configured interval: start evaluation
                                if last_canary is None or (now - last_canary) > float(self._canary_silence_seconds):
                                    if not canary_eval:
                                        st['canary_eval_started_at'] = now
                                    else:
                                        # evaluation in progress: if elapsed enough, remove diversion
                                        if (now - canary_eval) >= float(self._canary_silence_seconds):
                                            try:
                                                if self.traffic_engine:
                                                    self.traffic_engine.remove_rules_for_ip(ip)
                                            except Exception:
                                                pass
                                            # mark diversion removed and start suricata silence window
                                            self._diverted_ips.pop(ip, None)
                                            st['canary_removed_at'] = now
                                            st.pop('canary_eval_started_at', None)
                                            st['suricata_eval_started_at'] = now

                            # If suricata evaluation is running, check suricata silence
                            sur_eval = st.get('suricata_eval_started_at')
                            last_sur = st.get('last_suricata_ts')
                            if sur_eval is not None:
                                # If no suricata seen since eval started (or ever), and window passed -> reset IP state
                                if last_sur is None or (now - last_sur) >= float(self._suricata_silence_seconds):
                                    if (now - sur_eval) >= float(self._suricata_silence_seconds):
                                        # Final reset: clear per-ip state and notify
                                        try:
                                            # Remove any lingering rules defensively
                                            if self.traffic_engine:
                                                self.traffic_engine.remove_rules_for_ip(ip)
                                        except Exception:
                                            pass
                                        # notify via notifier
                                        try:
                                            if self.notifier:
                                                self.notifier.notify_redirect_change(ip, [], False)
                                        except Exception:
                                            pass
                                        # purge ip state
                                        try:
                                            del self._ip_states[ip]
                                        except Exception:
                                            pass
                        except Exception:
                            # continue looping other IPs
                            continue
                    time.sleep(1.0)
                except Exception:
                    time.sleep(1.0)

        t = threading.Thread(target=_worker, daemon=True, name="azazel-ip-state-monitor")
        self._ip_state_thread = t
        t.start()

    def _stop_ip_state_monitor(self) -> None:
        try:
            if getattr(self, '_ip_state_stop', None):
                self._ip_state_stop.set()
            if getattr(self, '_ip_state_thread', None):
                self._ip_state_thread.join(timeout=2.0)
        except Exception:
            pass
