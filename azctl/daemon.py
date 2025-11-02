"""Runtime daemon glue for Azazel."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
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
