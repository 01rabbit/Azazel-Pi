"""Light-weight state machine driving Azazel defensive posture changes."""
from __future__ import annotations

import time
from collections import deque
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

import yaml


CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "azazel.yaml"


@dataclass(frozen=True)
class State:
    """Represents a named state of the defensive system."""

    name: str
    description: str = ""


@dataclass(frozen=True)
class Event:
    """An external event that may trigger a transition."""

    name: str
    severity: int = 0


@dataclass
class Transition:
    """Transition from one state to another triggered by an event."""

    source: State
    target: State
    condition: Callable[[Event], bool]
    action: Optional[Callable[[State, State, Event], None]] = None


@dataclass
class StateMachine:
    """Mode-aware state machine with YAML-backed presets."""

    initial_state: State
    transitions: List[Transition] = field(default_factory=list)
    config_path: str | Path | None = None
    window_size: int = 5
    # EWMA time constant in seconds (used for decay / smoothing)
    ewma_tau: float = 60.0
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)
    current_state: State = field(init=False)

    def __post_init__(self) -> None:
        self.current_state = self.initial_state
        self._transition_map: Dict[str, List[Transition]] = {}
        for transition in self.transitions:
            self.add_transition(transition)
        self._config_cache: Dict[str, Any] | None = None
        self._score_window: Deque[int] = deque(maxlen=max(self.window_size, 1))
        # Exponential moving average state
        self._ewma: float = 0.0
        self._last_ewma_ts: float = float(self.clock())
        self._unlock_until: Dict[str, float] = {}
        self._user_mode_until: float = 0.0  # Timer for user intervention modes

    # ------------------------------------------------------------------
    # Transition helpers
    # ------------------------------------------------------------------
    def add_transition(self, transition: Transition) -> None:
        """Register a new transition."""

        bucket = self._transition_map.setdefault(transition.source.name, [])
        bucket.append(transition)

    def dispatch(self, event: Event) -> State:
        """Process an event and advance the state machine if applicable."""

        for transition in self._transition_map.get(self.current_state.name, []):
            if transition.condition(event):
                previous = self.current_state
                self.current_state = transition.target
                self._handle_transition(previous, self.current_state)
                if transition.action:
                    transition.action(previous, self.current_state, event)
                return self.current_state
        return self.current_state

    def reset(self) -> None:
        """Reset to the initial state."""

        self.current_state = self.initial_state
        self._user_mode_until = 0.0

    def summary(self) -> Dict[str, str]:
        """Return a serializable summary of the state machine."""

        status = {
            "state": self.current_state.name,
            "description": self.current_state.description,
        }
        
        # Add user mode information
        if self.is_user_mode():
            remaining = max(0, self._user_mode_until - self.clock())
            status["user_mode"] = "true"
            status["user_timeout_remaining"] = f"{remaining:.1f}"
        else:
            status["user_mode"] = "false"
            
        return status
    
    def is_user_mode(self) -> bool:
        """Check if current state is a user intervention mode."""
        return self.current_state.name.startswith("user_")
    
    def get_base_mode(self) -> str:
        """Get the base mode name (removing user_ prefix if present)."""
        if self.is_user_mode():
            return self.current_state.name[5:]  # Remove "user_" prefix
        return self.current_state.name
    
    def start_user_mode(self, mode: str, duration_minutes: float = 3.0) -> None:
        """Start user intervention mode with timer."""
        user_mode = f"user_{mode}"
        # Set timer before dispatch to ensure _handle_transition doesn't override it
        self._user_mode_until = self.clock() + (duration_minutes * 60)
        self.dispatch(Event(name=user_mode, severity=0))
    
    def check_user_mode_timeout(self) -> bool:
        """Check if user mode has timed out and transition if needed."""
        if not self.is_user_mode():
            return False
            
        if self.clock() >= self._user_mode_until:
            # Timeout - transition to corresponding auto mode
            base_mode = self.get_base_mode()
            timeout_event = f"timeout_{base_mode}"
            self.dispatch(Event(name=timeout_event, severity=0))
            self._user_mode_until = 0.0
            return True
        return False

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------
    def _resolve_config_path(self) -> Path:
        if self.config_path is not None:
            return Path(self.config_path)
        return CONFIG_PATH

    def _load_config(self) -> Dict[str, Any]:
        if self._config_cache is None:
            path = self._resolve_config_path()
            # If the resolved path doesn't exist, try common fallback locations
            if not path.exists():
                alt = Path("/etc/azazel/azazel.yaml")
                if alt.exists():
                    path = alt
                else:
                    # repo では configs/network/azazel.yaml にあるケースを追加で探索
                    cwd_conf = Path.cwd() / "configs" / "azazel.yaml"
                    net_conf = Path.cwd() / "configs" / "network" / "azazel.yaml"
                    if cwd_conf.exists():
                        path = cwd_conf
                    elif net_conf.exists():
                        path = net_conf
                    else:
                        # No configuration file found; use empty defaults
                        self._config_cache = {}
                        return self._config_cache

            data = yaml.safe_load(path.read_text())
            if not isinstance(data, dict):
                raise ValueError("Configuration root must be a mapping")
            self._config_cache = data
        return self._config_cache

    def reload_config(self) -> None:
        """Force re-reading of the YAML configuration."""

        self._config_cache = None

    def get_thresholds(self) -> Dict[str, Any]:
        """Return normal/shield/lockdown thresholds and unlock windows."""

        config = self._load_config()
        thresholds = config.get("thresholds", {})
        unlock = thresholds.get("unlock_wait_secs", {})
        return {
            "t0": int(thresholds.get("t0_normal", 20) or 20),
            "t1": int(thresholds.get("t1_shield", 50) or 50),
            "t2": int(thresholds.get("t2_lockdown", 80) or 80),
            "unlock_wait_secs": {
                "shield": int(unlock.get("shield", 0) or 0),
                "portal": int(unlock.get("portal", 0) or 0),
            },
        }

    def get_actions_preset(self) -> Dict[str, Any]:
        """Return the action plan preset for the current mode."""

        config = self._load_config()
        actions = config.get("actions", {})
        
        # For user modes, use the base mode's configuration
        mode_name = self.get_base_mode()
        preset = actions.get(mode_name, {})
        shape = preset.get("shape_kbps")
        return {
            "delay_ms": int(preset.get("delay_ms", 0) or 0),
            "shape_kbps": int(shape) if shape not in (None, "", False) else None,
            "block": bool(preset.get("block", False)),
        }

    # ------------------------------------------------------------------
    # Score window evaluation
    # ------------------------------------------------------------------
    def evaluate_window(self, severity: int) -> Dict[str, Any]:
        """Append a severity score and compute moving average decisions."""
        # Keep raw recent scores for display/backwards compatibility
        self._score_window.append(max(int(severity), 0))

        # Update EWMA using elapsed time to allow natural decay when events are sparse
        now = self.clock()
        try:
            dt = max(0.0, now - self._last_ewma_ts)
        except Exception:
            dt = 0.0
        tau = float(self.ewma_tau) if getattr(self, "ewma_tau", None) else 60.0
        if tau <= 0 or dt <= 0:
            alpha = 1.0
        else:
            alpha = 1.0 - math.exp(-dt / tau)

        # Initialize EWMA on first sample
        if not hasattr(self, "_ewma") or self._ewma is None or len(self._score_window) == 1:
            self._ewma = float(max(int(severity), 0))
        else:
            self._ewma = alpha * float(max(int(severity), 0)) + (1.0 - alpha) * float(self._ewma)
        self._last_ewma_ts = now

        # Expose the EWMA as the 'average' used for decisions
        average = float(self._ewma)
        thresholds = self.get_thresholds()
        
        # 閾値判定: t0_normal=20の場合、score<20がnormal, 20<=score<50がportal
        desired_mode = "normal"
        if average >= thresholds["t2"]:
            desired_mode = "lockdown"
        elif average >= thresholds["t1"]:
            desired_mode = "shield"
        elif average >= thresholds["t0"]:
            desired_mode = "portal"
        # average < t0 の場合、desired_mode = "normal" のまま
        
        return {"average": average, "desired_mode": desired_mode}

    def get_current_score(self) -> Dict[str, Any]:
        """Return current score metrics (EWMA + window avg/history) for display.

        Returns:
            Dict with keys: 'ewma', 'window_avg', 'history' (list newest-last)
        """
        window_avg = 0.0
        if len(self._score_window) > 0:
            window_avg = sum(self._score_window) / len(self._score_window)
        return {
            "ewma": float(getattr(self, "_ewma", 0.0)),
            "window_avg": float(window_avg),
            "history": list(self._score_window),
        }

    def apply_score(self, severity: int) -> Dict[str, Any]:
        """Evaluate the score window and transition to the appropriate mode."""

        # Check for user mode timeout first
        timeout_occurred = self.check_user_mode_timeout()
        
        evaluation = self.evaluate_window(severity)
        desired_mode = evaluation["desired_mode"]
        now = self.clock()
        
        # Skip automatic transitions if in user mode (unless timeout just occurred)
        if self.is_user_mode() and not timeout_occurred:
            evaluation.update({
                "target_mode": self.current_state.name,
                "applied_mode": self.current_state.name,
                "user_override": True,
                "user_timeout_remaining": max(0, self._user_mode_until - now),
            })
            return evaluation
        
        target_mode = desired_mode
        if desired_mode == "normal":
            target_mode = self._target_for_normal(now)
        elif desired_mode == "portal":
            target_mode = self._target_for_portal(now)
        elif desired_mode == "shield":
            target_mode = self._target_for_shield(now)

        if target_mode != self.current_state.name:
            self.dispatch(Event(name=target_mode, severity=severity))

        evaluation.update({
            "target_mode": target_mode,
            "applied_mode": self.current_state.name,
            "user_override": False,
        })
        return evaluation

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _handle_transition(self, previous: State, current: State) -> None:
        thresholds = self.get_thresholds()
        unlocks = thresholds.get("unlock_wait_secs", {})
        now = self.clock()
        
        # Handle user mode transitions - only set timer if not already set by start_user_mode
        if current.name.startswith("user_") and self._user_mode_until == 0.0:
            user_timeout = thresholds.get("user_mode_timeout_mins", 3.0)
            self._user_mode_until = now + (user_timeout * 60)
        elif previous.name.startswith("user_"):
            # Transitioning from user mode to auto mode
            self._user_mode_until = 0.0
        
        # Handle existing lockdown unlock logic for auto modes only
        current_base = current.name if not current.name.startswith("user_") else current.name[5:]
        if current_base == "lockdown":
            wait_shield = unlocks.get("shield", 0)
            if wait_shield:
                self._unlock_until["shield"] = now + wait_shield
        elif current_base == "shield":
            wait_portal = unlocks.get("portal", 0)
            if wait_portal:
                self._unlock_until["portal"] = now + wait_portal
            self._unlock_until.pop("shield", None)
        elif current_base == "portal":
            self._unlock_until.clear()

    def _target_for_shield(self, now: float) -> str:
        if self.current_state.name == "lockdown":
            unlock_at = self._unlock_until.get("shield", 0.0)
            if now < unlock_at:
                return "lockdown"
        return "shield"

    def _target_for_normal(self, now: float) -> str:
        """Target state when desired mode is normal - handles step-down from higher modes."""
        # Normal mode can be reached from any mode when score is low enough
        # No unlock delays apply when going to normal
        return "normal"

    def _target_for_portal(self, now: float) -> str:
        if self.current_state.name == "lockdown":
            unlock_at = self._unlock_until.get("shield", 0.0)
            if now < unlock_at:
                return "lockdown"
            # Step-down path: lockdown -> shield before portal.
            return "shield"
        if self.current_state.name == "shield":
            unlock_at = self._unlock_until.get("portal", 0.0)
            if now < unlock_at:
                return "shield"
        return "portal"
