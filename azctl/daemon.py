"""Runtime daemon glue for Azazel."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
import threading
import time
import math
from pathlib import Path
from typing import Iterable, List

from azazel_pi.core.scorer import ScoreEvaluator
from azazel_pi.core.state_machine import Event, StateMachine
from azazel_pi.core.enforcer.traffic_control import get_traffic_control_engine
from azazel_pi.core.hybrid_threat_evaluator import evaluate_with_hybrid_system
try:
    from azazel_pi.core.notify import MattermostNotifier
except Exception:
    MattermostNotifier = None


@dataclass
class AzazelDaemon:
    machine: StateMachine
    scorer: ScoreEvaluator
    # Default decisions log path aligned with CLI expectations
    decisions_log: Path = field(default_factory=lambda: Path("/var/log/azazel/decisions.log"))
    # Optional integrations
    traffic_engine: object | None = field(default_factory=lambda: get_traffic_control_engine())
    notifier: object | None = field(default_factory=lambda: MattermostNotifier() if MattermostNotifier is not None else None)

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
        # Build alert dict from Event for AI evaluators
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

        # Try hybrid AI evaluation
        try:
            ai_result = evaluate_with_hybrid_system(alert_data)
            # hybrid returns 'score' in 0-100 or 'risk' in 1-5; normalize to 0-100
            if isinstance(ai_result.get("score"), (int, float)):
                score = int(ai_result.get("score"))
            else:
                # convert risk 1-5 -> 0-100
                risk = int(ai_result.get("risk", 1))
                score = (risk - 1) * 25
            classification = ai_result.get("category", "ai")
        except Exception:
            # AI failed: fallback to legacy scorer
            try:
                score = self.scorer.evaluate([event])
                classification = self.scorer.classify(score)
            except Exception:
                score = 0
                classification = "unknown"

        evaluation = self.machine.apply_score(score)
        actions = self.machine.get_actions_preset()
        entry = {
            "event": event.name,
            "score": score,
            "classification": classification,
            "average": evaluation["average"],
            "desired_mode": evaluation["desired_mode"],
            "target_mode": evaluation["target_mode"],
            "mode": evaluation["applied_mode"],
            "actions": actions,
        }
        self._append_decisions([entry])

        # If we have a source IP, attempt to apply traffic control based on the applied mode
        try:
            target_ip = getattr(event, "src_ip", None)
            applied_mode = evaluation.get("applied_mode") or self.machine.current_state.name
            if target_ip and self.traffic_engine:
                # Apply or remove rules according to mode
                if applied_mode and applied_mode != "normal":
                    try:
                        self.traffic_engine.apply_combined_action(target_ip, applied_mode)
                    except Exception as e:
                        # Log but continue
                        try:
                            import logging

                            logging.getLogger(__name__).error(f"Traffic apply failed: {e}")
                        except Exception:
                            pass
                else:
                    try:
                        self.traffic_engine.remove_rules_for_ip(target_ip)
                    except Exception:
                        pass

            # Send a notification about the event and applied action
            if self.notifier:
                try:
                    summary = {
                        "event": event.name,
                        "src_ip": getattr(event, "src_ip", None),
                        "mode": applied_mode,
                        "score": score,
                        "actions": actions,
                    }
                    # Use signature+ip as suppression key when possible
                    key = f"{getattr(event, 'signature', '')}:{getattr(event, 'src_ip', '')}"
                    self.notifier.notify(summary, key=key)
                except Exception:
                    pass
        except Exception:
            # Keep daemon robust even if integrations fail
            pass

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
                    if last_ts <= 0.0 or getattr(self, '_last_entry', None) is None:
                        # Nothing written yet; wait
                        time.sleep(check_interval)
                        continue

                    age = max(0.0, now - last_ts)
                    # If no new writes for at least check_interval, compute decayed average
                    if age >= check_interval:
                        try:
                            base_avg = float(self._last_entry.get("average", 0.0))
                        except Exception:
                            base_avg = 0.0
                        # Exponential decay
                        try:
                            decayed = base_avg * math.exp(-age / float(decay_tau or 1.0))
                        except Exception:
                            decayed = base_avg
                        # Only append if decayed value is meaningfully different
                        if abs(decayed - base_avg) > 1e-3:
                            new_entry = dict(self._last_entry)
                            new_entry["event"] = "decay"
                            new_entry["score"] = decayed
                            new_entry["average"] = decayed
                            new_entry["classification"] = "decay"
                            # Timestamp in ISO UTC
                            try:
                                from datetime import datetime, timezone

                                new_entry["timestamp"] = datetime.now(timezone.utc).isoformat()
                            except Exception:
                                pass
                            # Persist the synthetic decay entry
                            try:
                                self._append_decisions([new_entry])
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
