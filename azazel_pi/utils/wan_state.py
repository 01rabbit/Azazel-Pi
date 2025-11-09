"""Helper utilities for reading/writing active WAN interface state."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _repo_root() -> Path:
    """Best-effort detection of repository root for runtime fallback path."""
    return Path(__file__).resolve().parents[2]


def _candidate_state_paths() -> List[Path]:
    """Return preferred search order for the WAN state file."""
    candidates: List[Path] = []
    env_path = os.environ.get("AZAZEL_WAN_STATE_PATH")
    if env_path:
        candidates.append(Path(env_path))

    # Runtime paths used on deployed systems
    candidates.append(Path("/var/run/azazel/wan_state.json"))
    candidates.append(Path("/run/azazel/wan_state.json"))

    # Repository fallback for development environments
    candidates.append(_repo_root() / "runtime" / "wan_state.json")

    # Deduplicate while preserving order
    deduped: List[Path] = []
    for path in candidates:
        if path not in deduped:
            deduped.append(path)
    return deduped


def resolve_state_path(create: bool = False) -> Path:
    """Locate the WAN state file path, optionally ensuring its parent exists."""
    for path in _candidate_state_paths():
        if path.exists():
            return path

    # If nothing exists yet, return the first candidate and ensure parent dir if requested
    target = _candidate_state_paths()[0]
    if create:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # If we cannot create the system path (e.g. /var/run) due to
            # permission restrictions in development environments, fall
            # back to a repository-local runtime path to allow non-root
            # testing without failing.
            repo_fallback = _repo_root() / "runtime" / "wan_state.json"
            repo_fallback.parent.mkdir(parents=True, exist_ok=True)
            return repo_fallback
    return target


_UNSET = object()


@dataclass
class InterfaceSnapshot:
    """Represents the most recent health snapshot for a WAN candidate."""

    name: str
    link_up: bool = False
    ip_address: Optional[str] = None
    speed_mbps: Optional[int] = None
    score: float = 0.0
    reason: Optional[str] = None
    last_checked: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InterfaceSnapshot":
        return cls(
            name=data.get("name", "unknown"),
            link_up=bool(data.get("link_up", False)),
            ip_address=data.get("ip_address"),
            speed_mbps=data.get("speed_mbps"),
            score=float(data.get("score", 0.0)),
            reason=data.get("reason"),
            last_checked=data.get("last_checked")
            or datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "link_up": self.link_up,
            "ip_address": self.ip_address,
            "speed_mbps": self.speed_mbps,
            "score": self.score,
            "reason": self.reason,
            "last_checked": self.last_checked,
        }


@dataclass
class WANState:
    """Structured representation of the WAN manager state file."""

    active_interface: Optional[str] = None
    status: str = "unknown"
    message: Optional[str] = None
    last_changed: Optional[str] = None
    candidates: List[InterfaceSnapshot] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WANState":
        return cls(
            active_interface=data.get("active_interface"),
            status=data.get("status", "unknown"),
            message=data.get("message"),
            last_changed=data.get("last_changed"),
            candidates=[
                InterfaceSnapshot.from_dict(item)
                for item in data.get("candidates", [])
            ],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_interface": self.active_interface,
            "status": self.status,
            "message": self.message,
            "last_changed": self.last_changed,
            "candidates": [snap.to_dict() for snap in self.candidates],
        }


def load_wan_state(path: Optional[Path] = None) -> WANState:
    """Load WAN state data from disk (or return defaults if missing)."""
    path = path or resolve_state_path(create=False)
    if not path.exists():
        return WANState()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return WANState.from_dict(data)
    except Exception:
        # If the file is unreadable (e.g., truncated), fall back to defaults
        return WANState()


def save_wan_state(state: WANState, path: Optional[Path] = None) -> None:
    """Persist WAN state to disk with an atomic write."""
    target = path or resolve_state_path(create=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(state.to_dict(), handle, ensure_ascii=False, indent=2)
    tmp_path.replace(target)


def get_active_wan_interface(default: str = "wlan1") -> str:
    """Convenience accessor for the current active WAN interface."""
    state = load_wan_state()
    return state.active_interface or default


def update_wan_state(
    *,
    active_interface=_UNSET,
    status: Optional[str] = None,
    message: Optional[str] = None,
    candidates: Optional[List[InterfaceSnapshot]] = None,
    path: Optional[Path] = None,
) -> WANState:
    """Update the WAN state file, returning the resulting state."""
    state = load_wan_state(path)
    if active_interface is not _UNSET:
        state.active_interface = active_interface  # type: ignore[assignment]
        state.last_changed = datetime.now(timezone.utc).isoformat()
    if status is not None:
        state.status = status
    if message is not None:
        state.message = message
    if candidates is not None:
        state.candidates = candidates
    save_wan_state(state, path=path)
    return state
