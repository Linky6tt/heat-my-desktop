"""
Tests for GUI widget and dialog initialization (offscreen).
"""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from gui.widget import ThermalWidget
from gui.settings_dialog import SettingsDialog
from gui.style import get_icon
from thermal.config import ThermalConfig

app = QApplication.instance() or QApplication([])


class TestGUIComponents(unittest.TestCase):

    def test_svg_icon_rendering(self):
        icon = get_icon("flame", 24)
        self.assertFalse(icon.isNull())

    def test_thermal_widget_init(self):
        cfg = ThermalConfig(target_temp_c=58.0, duration_seconds=180, maintain_after_warmup=False)
        widget = ThermalWidget(config=cfg)
        self.assertEqual(widget.target_spin.value(), 58.0)
        self.assertEqual(widget.dur_min_spin.value(), 3)
        self.assertEqual(widget.dur_sec_spin.value(), 0)
        self.assertFalse(widget.maintain_toggle.isChecked())
        widget.close()

    def test_settings_dialog_init(self):
        cfg = ThermalConfig(target_temp_c=62.0, duration_seconds=240, maintain_after_warmup=True)
        dialog = SettingsDialog(current_config=cfg, available_sensors=["k10temp::Tctl", "coretemp::Package"])
        self.assertEqual(dialog.target_spin.value(), 62.0)
        self.assertEqual(dialog.duration_spin.value(), 240)
        self.assertTrue(dialog.maintain_check.isChecked())
        dialog.close()

    def test_toast_notification(self):
        cfg = ThermalConfig(target_temp_c=30.0, duration_seconds=60)
        widget = ThermalWidget(config=cfg)
        widget.show()
        widget.show_toast("CPU is already at or above target temperature")
        self.assertEqual(widget.toast.text(), "CPU is already at or above target temperature")
        self.assertTrue(widget.toast.isVisible())
        widget.close()

    def test_tray_icon_activation_restores_window(self):
        cfg = ThermalConfig(target_temp_c=45.0, duration_seconds=60)
        widget = ThermalWidget(config=cfg)
        widget.showMinimized()
        # Simulate left-click (Trigger) on tray icon
        widget.tray_icon.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
        self.assertFalse(widget.isMinimized())
        widget.close()


if __name__ == "__main__":
    unittest.main()
