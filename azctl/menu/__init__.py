#!/usr/bin/env python3
"""
Modular TUI Menu System for Azazel-Pi

This module provides a modular terminal user interface for managing the Azazel-Pi system.
"""

from .core import AzazelTUIMenu
from .types import MenuAction, MenuCategory
from .wifi import WiFiManager
from .network import NetworkModule
from .defense import DefenseModule
from .services import ServicesModule
from .monitoring import MonitoringModule
from .system import SystemModule
from .emergency import EmergencyModule

__all__ = [
    'AzazelTUIMenu', 
    'MenuAction', 
    'MenuCategory',
    'WiFiManager',
    'NetworkModule',
    'DefenseModule', 
    'ServicesModule',
    'MonitoringModule',
    'SystemModule',
    'EmergencyModule'
]