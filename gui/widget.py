"""
Main GUI Widget for CPU Thermal Controller & Warmup.
Frameless, rounded-corner GNOME-style window with live gauges, controls,
pulsating heating indicator, and system tray support.
"""

import math
from typing import Optional

from PyQt6.QtCore import (
    QObject,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from thermal.config import ConfigConstraints, ThermalConfig
from thermal.engine import EngineState, ThermalEngine, ThermalStatus
from thermal.monitor import TemperatureMonitor
from .settings_dialog import SettingsDialog
from .style import MAIN_STYLESHEET, PALETTE, get_icon
from .titlebar import CustomTitleBar


class EngineSignalBridge(QObject):
    """Bridge to marshal ThermalEngine callbacks safely onto the Qt GUI thread."""
    status_updated = pyqtSignal(object)


class PulsingFlameBadge(QWidget):
    """
    Visual desktop indicator that pulses with an animated glow and flame
    when the CPU heating process is active.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(54, 54)
        self._glow_alpha = 0.0
        self._is_active = False

        # Pulse timer
        self._pulse_direction = 1
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(40)  # ~25 FPS
        self._pulse_timer.timeout.connect(self._animate_pulse)

    def set_active(self, active: bool) -> None:
        if self._is_active == active:
            return
        self._is_active = active
        if active:
            self._pulse_timer.start()
        else:
            self._pulse_timer.stop()
            self._glow_alpha = 0.0
            self.update()

    def _animate_pulse(self) -> None:
        self._glow_alpha += 0.04 * self._pulse_direction
        if self._glow_alpha >= 1.0:
            self._glow_alpha = 1.0
            self._pulse_direction = -1
        elif self._glow_alpha <= 0.2:
            self._glow_alpha = 0.2
            self._pulse_direction = 1
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(4, 4, -4, -4)
        center = rect.center()

        if self._is_active:
            # Pulsating outer glow ring
            alpha_int = int(self._glow_alpha * 180)
            glow_color = QColor(255, 120, 0, alpha_int)
            painter.setBrush(glow_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(center, 22, 22)

            # Core badge
            painter.setBrush(QColor(224, 27, 36))
            painter.drawEllipse(center, 17, 17)

            # Flame icon
            icon = get_icon("flame_hot", 20)
            icon.paint(painter, self.rect().adjusted(17, 17, -17, -17))
        else:
            # Idle badge
            painter.setBrush(QColor(42, 42, 42))
            painter.setPen(QColor(60, 60, 60))
            painter.drawEllipse(center, 17, 17)

            icon = get_icon("flame", 18)
            icon.paint(painter, self.rect().adjusted(18, 18, -18, -18))

        painter.end()


class ToastNotification(QLabel):
    """
    Modern floating pill toast notification that displays temporary warnings/messages
    and smoothly fades away.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "background-color: rgba(30, 30, 30, 245);"
            "color: #ffcc00;"
            "border: 1px solid rgba(255, 204, 0, 0.4);"
            "border-radius: 14px;"
            "padding: 6px 14px;"
            "font-size: 11px;"
            "font-weight: bold;"
        )
        self.setWordWrap(True)
        self.hide()

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(220)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

    def show_toast(self, message: str, duration_ms: int = 2800) -> None:
        self.setText(message)
        self.adjustSize()

        parent = self.parentWidget()
        if parent:
            parent_rect = parent.rect()
            toast_w = min(self.sizeHint().width() + 16, parent_rect.width() - 32)
            toast_h = self.sizeHint().height() + 4
            self.resize(toast_w, toast_h)
            x = (parent_rect.width() - toast_w) // 2
            y = parent_rect.height() - toast_h - 20
            self.move(x, y)

        self.show()
        self.raise_()

        self._fade_anim.stop()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

        self._hide_timer.start(duration_ms)

    def _fade_out(self) -> None:
        self._fade_anim.stop()
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()


class ThermalWidget(QWidget):
    """
    Main rounded frameless widget for CPU Thermal Controller.
    """

    def __init__(self, config: Optional[ThermalConfig] = None) -> None:
        super().__init__()
        self.config = config or ThermalConfig.load_from_file()

        # Initialize backend
        self._extreme_unlocked: bool = False
        self._prompting_extreme: bool = False
        self.bridge = EngineSignalBridge()
        self.bridge.status_updated.connect(self._on_status_received)
        self.monitor = TemperatureMonitor(preferred_sensor=self.config.sensor_name)
        self.engine = ThermalEngine(
            config=self.config,
            monitor=self.monitor,
            on_tick=self.bridge.status_updated.emit
        )

        # Frameless window settings
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(MAIN_STYLESHEET)
        self.setWindowIcon(get_icon("flame", 64))
        self.setMinimumWidth(420)

        # Polling timer for idle monitor readings
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(int(ConfigConstraints.SAMPLE_INTERVAL_SECONDS * 1000))
        self.idle_timer.timeout.connect(self._poll_idle_temperature)

        self._init_ui()
        self._init_tray_icon()
        self._sync_inputs_from_config()
        self.idle_timer.start()

    def _init_ui(self) -> None:
        # Outer container with drop shadow
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)

        self.root_container = QWidget(self)
        self.root_container.setObjectName("RootContainer")

        shadow = QGraphicsDropShadowEffect(self.root_container)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
        self.root_container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(self.root_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 1. Custom Title Bar (Top 10%)
        self.title_bar = CustomTitleBar(self, title="CPU Thermal Controller")
        self.title_bar.close_requested.connect(self.close)
        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.extend_requested.connect(self._toggle_compact)
        self.title_bar.settings_requested.connect(self._open_settings)
        container_layout.addWidget(self.title_bar)

        # 2. Main Body Container (90% Dark Grey)
        self.main_body = QWidget(self.root_container)
        self.main_body.setObjectName("MainBody")
        body_layout = QVBoxLayout(self.main_body)
        body_layout.setContentsMargins(16, 14, 16, 16)
        body_layout.setSpacing(12)

        # --- Hero Display Card ---
        self.hero_card = QFrame(self.main_body)
        self.hero_card.setProperty("class", "CardFrame")
        hero_layout = QHBoxLayout(self.hero_card)
        hero_layout.setContentsMargins(14, 12, 14, 12)
        hero_layout.setSpacing(12)

        # Pulsing heating indicator
        self.flame_badge = PulsingFlameBadge(self.hero_card)
        hero_layout.addWidget(self.flame_badge)

        # Temperature stats column
        temp_col = QVBoxLayout()
        temp_col.setSpacing(2)

        self.temp_label = QLabel("--.-°C", self.hero_card)
        self.temp_label.setProperty("class", "ValueDisplay")
        temp_col.addWidget(self.temp_label)

        self.status_sublabel = QLabel("Idle • Ready to warm up", self.hero_card)
        self.status_sublabel.setProperty("class", "MutedLabel")
        temp_col.addWidget(self.status_sublabel)

        hero_layout.addLayout(temp_col)
        hero_layout.addStretch()

        # Worker count badge
        self.worker_badge = QLabel("0 Workers", self.hero_card)
        self.worker_badge.setStyleSheet(
            f"background-color: #333333; color: {PALETTE['accent_blue']}; border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: bold;"
        )
        hero_layout.addWidget(self.worker_badge, alignment=Qt.AlignmentFlag.AlignVCenter)

        body_layout.addWidget(self.hero_card)

        # Trajectory Progress Bar
        self.progress_bar = QProgressBar(self.main_body)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        body_layout.addWidget(self.progress_bar)

        # --- Controls Container ---
        self.controls_card = QFrame(self.main_body)
        self.controls_card.setProperty("class", "CardFrame")
        controls_layout = QVBoxLayout(self.controls_card)
        controls_layout.setContentsMargins(14, 12, 14, 12)
        controls_layout.setSpacing(10)

        # Target Temperature Row
        temp_header_layout = QHBoxLayout()
        self.temp_title = QLabel("Target Temperature", self.controls_card)
        self.temp_title.setStyleSheet("font-size: 12px; font-weight: bold;")
        temp_header_layout.addWidget(self.temp_title)
        temp_header_layout.addStretch()

        self.target_spin = QDoubleSpinBox(self.controls_card)
        self.target_spin.setRange(ConfigConstraints.MIN_TARGET_TEMP_C, ConfigConstraints.EXTREME_MAX_TARGET_TEMP_C)
        self.target_spin.setSingleStep(0.5)
        self.target_spin.setSuffix(" °C")
        self.target_spin.valueChanged.connect(self._on_target_spin_changed)
        temp_header_layout.addWidget(self.target_spin)
        controls_layout.addLayout(temp_header_layout)

        # Target Temp Slider (default range 30 to 90°C)
        self.target_slider = QSlider(Qt.Orientation.Horizontal, self.controls_card)
        self.target_slider.setRange(int(ConfigConstraints.MIN_TARGET_TEMP_C), int(ConfigConstraints.MAX_TARGET_TEMP_C))
        self.target_slider.valueChanged.connect(self._on_target_slider_changed)
        controls_layout.addWidget(self.target_slider)

        # Warmup Duration Row
        dur_layout = QHBoxLayout()
        dur_title = QLabel("Warmup Time Frame", self.controls_card)
        dur_title.setStyleSheet("font-size: 12px; font-weight: bold;")
        dur_layout.addWidget(dur_title)
        dur_layout.addStretch()

        # Minutes spinbox
        self.dur_min_spin = QSpinBox(self.controls_card)
        self.dur_min_spin.setRange(0, 60)
        self.dur_min_spin.setSuffix(" m")
        self.dur_min_spin.valueChanged.connect(self._on_duration_changed)
        dur_layout.addWidget(self.dur_min_spin)

        # Seconds spinbox
        self.dur_sec_spin = QSpinBox(self.controls_card)
        self.dur_sec_spin.setRange(0, 59)
        self.dur_sec_spin.setSuffix(" s")
        self.dur_sec_spin.valueChanged.connect(self._on_duration_changed)
        dur_layout.addWidget(self.dur_sec_spin)

        controls_layout.addLayout(dur_layout)

        # Maintain Temperature Checkbox
        self.maintain_toggle = QCheckBox("Maintain temperature after warmup", self.controls_card)
        self.maintain_toggle.setChecked(self.config.maintain_after_warmup)
        self.maintain_toggle.toggled.connect(self._on_maintain_toggled)
        controls_layout.addWidget(self.maintain_toggle)

        body_layout.addWidget(self.controls_card)

        # --- Big Action Button ---
        self.action_btn = QPushButton("Start Warmup", self.main_body)
        self.action_btn.setProperty("class", "PrimaryButton")
        self.action_btn.clicked.connect(self._toggle_engine)
        body_layout.addWidget(self.action_btn)

        container_layout.addWidget(self.main_body)
        outer_layout.addWidget(self.root_container)

        # Floating toast notification overlay
        self.toast = ToastNotification(self.root_container)

    def _init_tray_icon(self) -> None:
        self.tray_icon = QSystemTrayIcon(get_icon("flame", 24), self)
        self.tray_icon.setToolTip("CPU Thermal Controller")

        tray_menu = QMenu()
        show_action = tray_menu.addAction("Show Widget")
        show_action.triggered.connect(self._restore_window)

        self.tray_start_action = tray_menu.addAction("Start Warmup")
        self.tray_start_action.triggered.connect(self._toggle_engine)

        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(self._safe_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_icon_activated)
        self.tray_icon.show()

    def _restore_window(self) -> None:
        """Restores and brings the main window to the foreground if minimized or hidden."""
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handles clicks on the system tray icon. Left click restores the window if minimized."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._restore_window()

    def _sync_inputs_from_config(self) -> None:
        self.target_spin.setValue(self.config.target_temp_c)
        self.target_slider.setValue(int(self.config.target_temp_c))

        total_secs = self.config.duration_seconds
        mins = total_secs // 60
        secs = total_secs % 60
        self.dur_min_spin.setValue(mins)
        self.dur_sec_spin.setValue(secs)
        self.maintain_toggle.setChecked(self.config.maintain_after_warmup)

    def _prompt_extreme_mode_unlock(self) -> bool:
        """Prompts the user with a warning dialog before unlocking >90°C extreme mode."""
        if self._prompting_extreme:
            return False

        self._prompting_extreme = True
        try:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("Extreme Stress Testing Warning")
            msg_box.setText("USE AT YOUR OWN RISK - NOT RECOMMENDED")
            msg_box.setInformativeText(
                "You are attempting to set a target temperature above 90.0°C (up to 100.0°C).\n\n"
                "• This will DISABLE the automatic 90.0°C safety kill-switch.\n"
                "• This is strictly for extreme stress testing and is NOT recommended.\n"
                "• Operating at these temperatures can cause silicon degradation, crashes, or permanent hardware damage.\n"
                "• This option cannot be saved as a default and only applies to this single session.\n\n"
                "Do you want to unlock the 100°C extreme limit for this session?"
            )
            unlock_btn = msg_box.addButton("Unlock Extreme Mode", QMessageBox.ButtonRole.AcceptRole)
            cancel_btn = msg_box.addButton("Cancel (Keep Safe 90°C Limit)", QMessageBox.ButtonRole.RejectRole)
            msg_box.setDefaultButton(cancel_btn)
            msg_box.exec()

            if msg_box.clickedButton() == unlock_btn:
                self._extreme_unlocked = True
                self.config.allow_extreme_temp = True
                self.target_slider.blockSignals(True)
                self.target_slider.setRange(int(ConfigConstraints.MIN_TARGET_TEMP_C), int(ConfigConstraints.EXTREME_MAX_TARGET_TEMP_C))
                self.target_slider.blockSignals(False)
                self._update_extreme_mode_ui(True)
                return True
            else:
                self._extreme_unlocked = False
                self.config.allow_extreme_temp = False
                self.target_slider.blockSignals(True)
                self.target_slider.setRange(int(ConfigConstraints.MIN_TARGET_TEMP_C), int(ConfigConstraints.MAX_TARGET_TEMP_C))
                self.target_slider.setValue(int(ConfigConstraints.MAX_TARGET_TEMP_C))
                self.target_slider.blockSignals(False)
                self.target_spin.blockSignals(True)
                self.target_spin.setValue(ConfigConstraints.MAX_TARGET_TEMP_C)
                self.target_spin.blockSignals(False)
                self.config.target_temp_c = ConfigConstraints.MAX_TARGET_TEMP_C
                self._update_extreme_mode_ui(False)
                return False
        finally:
            self._prompting_extreme = False

    def _update_extreme_mode_ui(self, is_extreme: bool) -> None:
        if is_extreme:
            self.temp_title.setText("Target Temp (EXTREME >90°C)")
            self.temp_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #ff5555;")
        else:
            self.temp_title.setText("Target Temperature")
            self.temp_title.setStyleSheet("font-size: 12px; font-weight: bold;")

    def _on_target_spin_changed(self, val: float) -> None:
        if round(val, 2) > 90.0:
            if not self._extreme_unlocked:
                if not self._prompt_extreme_mode_unlock():
                    return
        elif round(val, 2) <= 90.0 and self._extreme_unlocked:
            # If user dials back down to safe range, re-lock extreme status
            self._extreme_unlocked = False
            self.config.allow_extreme_temp = False
            self.target_slider.blockSignals(True)
            self.target_slider.setRange(int(ConfigConstraints.MIN_TARGET_TEMP_C), int(ConfigConstraints.MAX_TARGET_TEMP_C))
            self.target_slider.blockSignals(False)
            self._update_extreme_mode_ui(False)

        if self.target_slider.value() != int(val):
            self.target_slider.blockSignals(True)
            self.target_slider.setValue(int(val))
            self.target_slider.blockSignals(False)
        self.config.target_temp_c = val

    def _on_target_slider_changed(self, val: int) -> None:
        if val > 90:
            if not self._extreme_unlocked:
                if not self._prompt_extreme_mode_unlock():
                    return
        elif val <= 90 and self._extreme_unlocked:
            self._extreme_unlocked = False
            self.config.allow_extreme_temp = False
            self.target_slider.blockSignals(True)
            self.target_slider.setRange(int(ConfigConstraints.MIN_TARGET_TEMP_C), int(ConfigConstraints.MAX_TARGET_TEMP_C))
            self.target_slider.blockSignals(False)
            self._update_extreme_mode_ui(False)

        if self.target_spin.value() != float(val):
            self.target_spin.blockSignals(True)
            self.target_spin.setValue(float(val))
            self.target_spin.blockSignals(False)
        self.config.target_temp_c = float(val)

    def _on_duration_changed(self) -> None:
        mins = self.dur_min_spin.value()
        secs = self.dur_sec_spin.value()
        total = max(1, min(ConfigConstraints.MAX_DURATION_SECONDS, mins * 60 + secs))
        self.config.duration_seconds = total

    def _on_maintain_toggled(self, checked: bool) -> None:
        self.config.maintain_after_warmup = checked

    def _toggle_compact(self) -> None:
        is_hidden = self.controls_card.isHidden()
        self.controls_card.setVisible(is_hidden)
        self.adjustSize()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            parent=self,
            current_config=self.config,
            available_sensors=self.monitor.get_available_sensors()
        )
        dialog.config_saved.connect(self._on_config_saved_from_dialog)
        dialog.exec()

    def _on_config_saved_from_dialog(self, new_cfg: ThermalConfig) -> None:
        self.config = new_cfg
        self.monitor.preferred_sensor = new_cfg.sensor_name
        self._sync_inputs_from_config()

    def _poll_idle_temperature(self) -> None:
        if not self.engine.is_running:
            temp = self.monitor.read_cpu_temperature()
            if temp is not None:
                self.temp_label.setText(f"{temp:.1f}°C")
                self.tray_icon.setToolTip(f"CPU Temp: {temp:.1f}°C (Idle)")

    def show_toast(self, message: str) -> None:
        """Displays a floating UI toast notification."""
        if hasattr(self, "toast"):
            self.toast.show_toast(message)

    def _toggle_engine(self) -> None:
        if self.engine.is_running:
            self.engine.stop()
            self._set_ui_stopped()
        else:
            self._on_duration_changed()
            self.config.target_temp_c = self.target_spin.value()
            self.config.maintain_after_warmup = self.maintain_toggle.isChecked()

            # Pre-check: if target temp <= current idle temperature
            current_temp = self.monitor.read_cpu_temperature()
            if current_temp is not None and self.config.target_temp_c <= current_temp:
                self.show_toast("CPU is already at or above target temperature")
                from service.notify import notify_already_at_target
                try:
                    notify_already_at_target(current_temp, self.config.target_temp_c)
                except Exception:
                    pass
                return

            success = self.engine.start(self.config)
            if success:
                self._set_ui_running()
            else:
                self.show_toast("CPU is already at or above target temperature")

    def _set_ui_running(self) -> None:
        self.action_btn.setText("Stop Warmup")
        self.action_btn.setProperty("class", "StopButton")
        self.action_btn.style().unpolish(self.action_btn)
        self.action_btn.style().polish(self.action_btn)

        self.tray_start_action.setText("Stop Warmup")
        self.flame_badge.set_active(True)
        self.target_spin.setEnabled(False)
        self.target_slider.setEnabled(False)
        self.dur_min_spin.setEnabled(False)
        self.dur_sec_spin.setEnabled(False)
        self.maintain_toggle.setEnabled(False)

    def _set_ui_stopped(self) -> None:
        self.action_btn.setText("Start Warmup")
        self.action_btn.setProperty("class", "PrimaryButton")
        self.action_btn.style().unpolish(self.action_btn)
        self.action_btn.style().polish(self.action_btn)

        self.tray_start_action.setText("Start Warmup")
        self.flame_badge.set_active(False)
        self.worker_badge.setText("0 Workers")
        self.target_spin.setEnabled(True)
        self.target_slider.setEnabled(True)
        self.dur_min_spin.setEnabled(True)
        self.dur_sec_spin.setEnabled(True)
        self.maintain_toggle.setEnabled(True)

    def _on_status_received(self, status: ThermalStatus) -> None:
        self.temp_label.setText(f"{status.current_temp_c:.1f}°C")
        self.worker_badge.setText(f"{status.active_workers} Workers")

        # Progress calculation
        if status.total_duration_seconds > 0:
            prog_pct = min(100, int((status.elapsed_seconds / status.total_duration_seconds) * 100))
            self.progress_bar.setValue(prog_pct)

        # Status text update
        if status.state == EngineState.WARMUP:
            self.status_sublabel.setText(
                f"Warming up • Target: {status.target_temp_c:.1f}°C (Exp: {status.expected_temp_c:.1f}°C)"
            )
            self.flame_badge.set_active(status.active_workers > 0)
        elif status.state == EngineState.MAINTAINING:
            self.status_sublabel.setText(f"Maintaining {status.target_temp_c:.1f}°C")
            self.flame_badge.set_active(status.active_workers > 0)
        elif status.state == EngineState.COMPLETED:
            self.status_sublabel.setText("Warmup Completed")
            self._set_ui_stopped()
        elif status.state == EngineState.EMERGENCY_STOP:
            self.status_sublabel.setText(f"⚠️ FAILSAPFE TRIGGERED (>90°C)")
            self.status_sublabel.setStyleSheet(f"color: {PALETTE['accent_red']}; font-weight: bold;")
            self._set_ui_stopped()

        self.tray_icon.setToolTip(f"CPU: {status.current_temp_c:.1f}°C ({status.state.value})")

    def _safe_quit(self) -> None:
        self.idle_timer.stop()
        if self.engine.is_running:
            self.engine.stop()
        self.tray_icon.hide()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        self._safe_quit()
        event.accept()
