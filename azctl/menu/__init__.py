#!/usr/bin/env python3
"""
Modular TUI Menu System for Azazel-Pi

This module provides a modular terminal user interface for managing the Azazel-Pi system.
"""

from azctl.menu.core import AzazelTUIMenu
from azctl.menu.types import MenuAction, MenuCategory
from azctl.menu.wifi import WiFiManager
from azctl.menu.network import NetworkModule
from azctl.menu.defense import DefenseModule
from azctl.menu.services import ServicesModule
from azctl.menu.monitoring import MonitoringModule
from azctl.menu.system import SystemModule
from azctl.menu.emergency import EmergencyModule

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