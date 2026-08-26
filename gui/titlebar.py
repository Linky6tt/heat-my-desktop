"""
Custom frameless window title bar with GNOME style and window control buttons.
"""

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)

from .style import get_icon


class CustomTitleBar(QWidget):
    """
    Custom titlebar supporting drag-to-move and dedicated control buttons:
    Close, Minimize, Extend (compact/expanded toggle), and Settings Cogwheel.
    """

    close_requested = pyqtSignal()
    minimize_requested = pyqtSignal()
    extend_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, parent: QWidget, title: str = "CPU Thermal Controller") -> None:
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self._parent = parent
        self._drag_pos: QPoint = QPoint()
        self._is_compact = False

        self._init_ui(title)

    def _init_ui(self, title: str) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(6)

        # Settings cogwheel on left or right (standard GNOME layout puts cogwheel / menu left or right)
        self.settings_btn = QToolButton(self)
        self.settings_btn.setObjectName("SettingsButton")
        self.settings_btn.setProperty("class", "TitleButton")
        self.settings_btn.setIcon(get_icon("settings", 16))
        self.settings_btn.setToolTip("Settings & Startup Daemon (Systemd)")
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self.settings_btn)

        # App Title
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("TitleLabel")
        layout.addWidget(self.title_label)

        layout.addStretch()

        # Extend / Compact button
        self.extend_btn = QToolButton(self)
        self.extend_btn.setObjectName("ExtendButton")
        self.extend_btn.setProperty("class", "TitleButton")
        self.extend_btn.setIcon(get_icon("extend", 14))
        self.extend_btn.setToolTip("Toggle Compact / Expanded View")
        self.extend_btn.clicked.connect(self._toggle_extend)
        layout.addWidget(self.extend_btn)

        # Minimize button
        self.min_btn = QToolButton(self)
        self.min_btn.setObjectName("MinButton")
        self.min_btn.setProperty("class", "TitleButton")
        self.min_btn.setIcon(get_icon("minimize", 14))
        self.min_btn.setToolTip("Minimize")
        self.min_btn.clicked.connect(self.minimize_requested.emit)
        layout.addWidget(self.min_btn)

        # Close button
        self.close_btn = QToolButton(self)
        self.close_btn.setObjectName("CloseButton")
        self.close_btn.setProperty("class", "TitleButton")
        self.close_btn.setIcon(get_icon("close", 14))
        self.close_btn.setToolTip("Close")
        self.close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(self.close_btn)

    def _toggle_extend(self) -> None:
        self._is_compact = not self._is_compact
        icon_name = "collapse" if self._is_compact else "extend"
        self.extend_btn.setIcon(get_icon(icon_name, 14))
        self.extend_requested.emit()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self._parent.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
