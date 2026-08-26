"""
Settings overlay and systemd service generation dialog.
"""

from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from service.systemd import (
    disable_user_service,
    enable_user_service,
    generate_service_content,
    get_service_status,
    install_user_service,
    is_service_installed,
    uninstall_user_service,
)
from thermal.config import ConfigConstraints, ThermalConfig
from .style import MAIN_STYLESHEET, PALETTE, get_icon


class SettingsDialog(QDialog):
    """
    Settings dialog allowing users to set startup default preferences
    and generate/install a systemd service unit file for headless boot.
    """

    config_saved = pyqtSignal(ThermalConfig)

    def __init__(self, parent: Optional[QWidget] = None, current_config: Optional[ThermalConfig] = None, available_sensors: Optional[List[str]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings & Startup Daemon")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setMinimumHeight(560)
        self.setStyleSheet(MAIN_STYLESHEET)

        self.current_config = current_config or ThermalConfig.load_from_file()
        self.available_sensors = available_sensors or []

        self._init_ui()
        self._load_values()
        self._update_service_preview()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # Dialog Title Header
        header_layout = QHBoxLayout()
        icon_label = QLabel(self)
        icon_label.setPixmap(get_icon("settings", 20).pixmap(20, 20))
        header_layout.addWidget(icon_label)

        title = QLabel("Application Settings & Systemd Daemon", self)
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Section 1: Default Preferences Card
        pref_card = QFrame(self)
        pref_card.setProperty("class", "CardFrame")
        pref_layout = QVBoxLayout(pref_card)
        pref_layout.setContentsMargins(14, 12, 14, 12)
        pref_layout.setSpacing(10)

        pref_title = QLabel("Startup & Default Preferences", pref_card)
        pref_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #3584e4;")
        pref_layout.addWidget(pref_title)

        # Target temp row
        temp_row = QHBoxLayout()
        temp_lbl = QLabel("Default Target Temp (°C):", pref_card)
        self.target_spin = QDoubleSpinBox(pref_card)
        self.target_spin.setRange(ConfigConstraints.MIN_TARGET_TEMP_C, ConfigConstraints.MAX_TARGET_TEMP_C)
        self.target_spin.setSingleStep(0.5)
        self.target_spin.setSuffix(" °C")
        self.target_spin.valueChanged.connect(self._update_service_preview)
        temp_row.addWidget(temp_lbl)
        temp_row.addStretch()
        temp_row.addWidget(self.target_spin)
        pref_layout.addLayout(temp_row)

        # Duration row
        dur_row = QHBoxLayout()
        dur_lbl = QLabel("Default Duration (seconds):", pref_card)
        self.duration_spin = QSpinBox(pref_card)
        self.duration_spin.setRange(ConfigConstraints.MIN_DURATION_SECONDS, ConfigConstraints.MAX_DURATION_SECONDS)
        self.duration_spin.setSingleStep(30)
        self.duration_spin.setSuffix(" s")
        self.duration_spin.valueChanged.connect(self._update_service_preview)
        dur_row.addWidget(dur_lbl)
        dur_row.addStretch()
        dur_row.addWidget(self.duration_spin)
        pref_layout.addLayout(dur_row)

        # Maintain checkbox
        self.maintain_check = QCheckBox("Maintain temperature after warmup by default", pref_card)
        self.maintain_check.toggled.connect(self._update_service_preview)
        pref_layout.addWidget(self.maintain_check)

        # Sensor selector
        sensor_row = QHBoxLayout()
        sensor_lbl = QLabel("Thermal Sensor:", pref_card)
        self.sensor_combo = QComboBox(pref_card)
        self.sensor_combo.addItem("Auto-detect Primary CPU Sensor", None)
        for s in self.available_sensors:
            self.sensor_combo.addItem(s, s)
        self.sensor_combo.currentIndexChanged.connect(self._update_service_preview)
        sensor_row.addWidget(sensor_lbl)
        sensor_row.addWidget(self.sensor_combo)
        pref_layout.addLayout(sensor_row)

        main_layout.addWidget(pref_card)

        # Section 2: Systemd Startup Service Card
        sys_card = QFrame(self)
        sys_card.setProperty("class", "CardFrame")
        sys_layout = QVBoxLayout(sys_card)
        sys_layout.setContentsMargins(14, 12, 14, 12)
        sys_layout.setSpacing(10)

        sys_title = QLabel("Systemd Startup Daemon Integration", sys_card)
        sys_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #ff7800;")
        sys_layout.addWidget(sys_title)

        sys_desc = QLabel("Generate a systemd user service to automatically execute the warmup controller headlessly on system startup.", sys_card)
        sys_desc.setProperty("class", "MutedLabel")
        sys_desc.setWordWrap(True)
        sys_layout.addWidget(sys_desc)

        # Service Preview Box
        self.preview_edit = QPlainTextEdit(sys_card)
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setMaximumHeight(130)
        self.preview_edit.setStyleSheet(
            f"background-color: #1a1a1a; color: #a0c0e0; font-family: monospace; font-size: 11px; border: 1px solid #333333; border-radius: 4px;"
        )
        sys_layout.addWidget(self.preview_edit)

        # Service Action Buttons
        sys_btn_layout = QHBoxLayout()
        self.install_btn = QPushButton("Install .service", sys_card)
        self.install_btn.setProperty("class", "SecondaryButton")
        self.install_btn.clicked.connect(self._handle_install_service)
        sys_btn_layout.addWidget(self.install_btn)

        self.enable_btn = QPushButton("Enable on Boot", sys_card)
        self.enable_btn.setProperty("class", "SecondaryButton")
        self.enable_btn.clicked.connect(self._handle_enable_service)
        sys_btn_layout.addWidget(self.enable_btn)

        self.disable_btn = QPushButton("Disable Service", sys_card)
        self.disable_btn.setProperty("class", "SecondaryButton")
        self.disable_btn.clicked.connect(self._handle_disable_service)
        sys_btn_layout.addWidget(self.disable_btn)

        sys_layout.addLayout(sys_btn_layout)

        # Service Status Label
        self.service_status_lbl = QLabel(sys_card)
        self.service_status_lbl.setProperty("class", "MutedLabel")
        self._refresh_service_status()
        sys_layout.addWidget(self.service_status_lbl)

        main_layout.addWidget(sys_card)

        main_layout.addStretch()

        # Dialog Footer Action Buttons
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setProperty("class", "SecondaryButton")
        self.cancel_btn.clicked.connect(self.reject)
        footer_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save Defaults", self)
        self.save_btn.setProperty("class", "PrimaryButton")
        self.save_btn.clicked.connect(self._handle_save)
        footer_layout.addWidget(self.save_btn)

        main_layout.addLayout(footer_layout)

    def _load_values(self) -> None:
        self.target_spin.setValue(self.current_config.target_temp_c)
        self.duration_spin.setValue(self.current_config.duration_seconds)
        self.maintain_check.setChecked(self.current_config.maintain_after_warmup)
        if self.current_config.sensor_name:
            idx = self.sensor_combo.findData(self.current_config.sensor_name)
            if idx >= 0:
                self.sensor_combo.setCurrentIndex(idx)

    def _get_current_input_config(self) -> ThermalConfig:
        sensor_data = self.sensor_combo.currentData()
        return ThermalConfig(
            target_temp_c=self.target_spin.value(),
            duration_seconds=self.duration_spin.value(),
            maintain_after_warmup=self.maintain_check.isChecked(),
            sensor_name=sensor_data
        )

    def _update_service_preview(self) -> None:
        try:
            cfg = self._get_current_input_config()
            content = generate_service_content(cfg)
            self.preview_edit.setPlainText(content)
        except Exception:
            pass

    def _refresh_service_status(self) -> None:
        installed = is_service_installed()
        if installed:
            self.install_btn.setText("Uninstall .service")
            self.install_btn.setStyleSheet(f"background-color: #5a2020; color: #ff9999; border: 1px solid #7a2828;")
        else:
            self.install_btn.setText("Install .service")
            self.install_btn.setStyleSheet("")

        is_active, status_str = get_service_status()
        if is_active:
            self.service_status_lbl.setText(f"● Systemd Status: ACTIVE (running) | Installed: {'Yes' if installed else 'No'}")
            self.service_status_lbl.setStyleSheet(f"color: {PALETTE['accent_green']}; font-size: 11px;")
        else:
            self.service_status_lbl.setText(f"○ Systemd Status: {status_str or 'inactive'} | Installed: {'Yes' if installed else 'No'}")
            self.service_status_lbl.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 11px;")

    def _handle_install_service(self) -> None:
        if is_service_installed():
            # Perform uninstall
            ok, msg = uninstall_user_service()
            if ok:
                QMessageBox.information(self, "Service Uninstalled", "Systemd user service has been stopped, disabled, and removed.")
            else:
                QMessageBox.warning(self, "Uninstall Result", msg)
            self._refresh_service_status()
            return

        # Perform install
        cfg = self._get_current_input_config()
        try:
            path = install_user_service(cfg)
            QMessageBox.information(
                self,
                "Service Installed",
                f"Successfully installed systemd unit file to:\n{path}\n\nYou can now enable it to run on boot."
            )
            self._refresh_service_status()
        except Exception as e:
            QMessageBox.critical(self, "Installation Error", f"Failed to install service: {e}")

    def _handle_enable_service(self) -> None:
        cfg = self._get_current_input_config()
        install_user_service(cfg)
        success, msg = enable_user_service()
        if success:
            QMessageBox.information(self, "Service Enabled", msg)
        else:
            QMessageBox.warning(self, "Enable Service Result", msg)
        self._refresh_service_status()

    def _handle_disable_service(self) -> None:
        success, msg = disable_user_service()
        if success:
            QMessageBox.information(self, "Service Disabled", msg)
        else:
            QMessageBox.warning(self, "Disable Service Result", msg)
        self._refresh_service_status()

    def _handle_save(self) -> None:
        cfg = self._get_current_input_config()
        cfg.save_to_file()
        self.config_saved.emit(cfg)
        self.accept()
