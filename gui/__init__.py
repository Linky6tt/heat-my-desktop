"""
GUI package for CPU Thermal Controller & Warmup Widget.
"""

from .widget import ThermalWidget
from .settings_dialog import SettingsDialog
from .titlebar import CustomTitleBar
from .style import MAIN_STYLESHEET, PALETTE, get_icon

__all__ = [
    "ThermalWidget",
    "SettingsDialog",
    "CustomTitleBar",
    "MAIN_STYLESHEET",
    "PALETTE",
    "get_icon",
]
