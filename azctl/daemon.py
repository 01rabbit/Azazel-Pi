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


@dataclass
class AzazelDaemon:
    machine: StateMachine
    scorer: ScoreEvaluator
    # Default decisions log path aligned with CLI expectations
    decisions_log: Path = field(default_factory=lambda: Path("/var/log/azazel/decisions.log"))

    def process_events(self, events: Iterable[Event]) -> None:
        entries: List[dict] = []
        for event in events:
            score = self.scorer.evaluate([event])
            classification = self.scorer.classify(score)
            evaluation = self.machine.apply_score(score)
            actions = self.machine.get_actions_preset()
            entries.append(
                {
                    "event": event.name,
                    "score": score,
                    "classification": classification,
                    "average": evaluation["average"],
                    "desired_mode": evaluation["desired_mode"],
                    "target_mode": evaluation["target_mode"],
                    "mode": evaluation["applied_mode"],
                    "actions": actions,
                }
            )

            # Persist each entry immediately so long-running consumers have up-to-date state
            self._append_decisions([entries[-1]])

    def process_event(self, event: Event) -> None:
        """Process a single Event and append a decision entry immediately."""
        score = self.scorer.evaluate([event])
        classification = self.scorer.classify(score)
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
