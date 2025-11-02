#!/usr/bin/env python3
"""
Menu Types and Data Classes

Defines the core data structures used by the Azazel TUI menu system.
"""

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class MenuAction:
    """Represents a menu action item."""
    title: str
    description: str
    action: Callable
    requires_root: bool = False
    danger_level: int = 0  # 0=safe, 1=caution, 2=dangerous
    dangerous: bool = False  # For backward compatibility


@dataclass 
class MenuCategory:
    """Represents a menu category containing multiple actions."""
    title: str
    description: str
    actions: list[MenuAction]