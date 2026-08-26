"""
GNOME Adwaita Dark inspired styling and vector icons for CPU Thermal Controller widget.
"""

from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import QByteArray, QSize

# GNOME Adwaita Dark Palette
PALETTE = {
    "window_bg": "#1e1e1e",          # 90% main body dark grey
    "header_bg": "#2e2e2e",          # Lighter shade grey top bar
    "card_bg": "#282828",            # Elevated card containers
    "card_border": "#383838",        # Subtle card border
    "text_primary": "#ffffff",       # Bright white text
    "text_secondary": "#9a9996",     # Muted grey text
    "accent_blue": "#3584e4",        # Adwaita Blue
    "accent_orange": "#ff7800",      # Thermal Orange
    "accent_red": "#e01b24",         # Warning / Failsafe Red
    "accent_green": "#2ec27e",       # Success / Active Green
    "button_bg": "#3c3c3c",          # Standard button
    "button_hover": "#4a4a4a",       # Button hover
    "button_pressed": "#2c2c2c",     # Button pressed
    "close_hover": "#c01c28",        # Close button hover red
}

# SVG Icon definitions
SVG_ICONS = {
    "close": """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#d0d0d0" stroke-width="2" stroke-linecap="round"><line x1="4" y1="4" x2="12" y2="12"/><line x1="12" y1="4" x2="4" y2="12"/></svg>""",
    "minimize": """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#d0d0d0" stroke-width="2" stroke-linecap="round"><line x1="3" y1="8" x2="13" y2="8"/></svg>""",
    "extend": """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#d0d0d0" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2h4v4M6 14H2v-4M14 2l-5 5M2 14l5-5"/></svg>""",
    "collapse": """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#d0d0d0" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10h4v4M12 6H8V2M8 8l-5 5M8 8l5-5"/></svg>""",
    "settings": """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#d0d0d0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>""",
    "flame": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#ff7800" stroke="#e01b24" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 17c1.38 0 2.5-1.12 2.5-2.5 0-.74-.32-1.4-.84-1.85-.38-.33-.66-.78-.66-1.3 0-.67.4-1.25.96-1.55C14.7 9.17 16 11.23 16 13.5a5.5 5.5 0 0 1-11 0c0-2.27 1.3-4.33 3.04-5.2.56.3.96.88.96 1.55 0 .52-.28.97-.66 1.3-.52.45-.84 1.11-.84 1.85z"/></svg>""",
    "flame_hot": """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#e01b24" stroke="#ff7800" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 17c1.38 0 2.5-1.12 2.5-2.5 0-.74-.32-1.4-.84-1.85-.38-.33-.66-.78-.66-1.3 0-.67.4-1.25.96-1.55C14.7 9.17 16 11.23 16 13.5a5.5 5.5 0 0 1-11 0c0-2.27 1.3-4.33 3.04-5.2.56.3.96.88.96 1.55 0 .52-.28.97-.66 1.3-.52.45-.84 1.11-.84 1.85z"/></svg>""",
    "cpu": """<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3584e4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>""",
}


def get_icon(name: str, size: int = 16) -> QIcon:
    """Renders an SVG string into a QIcon with the specified pixel size."""
    svg_str = SVG_ICONS.get(name, "")
    if not svg_str:
        return QIcon()

    renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)


MAIN_STYLESHEET = f"""
QWidget#RootContainer {{
    background-color: {PALETTE['window_bg']};
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.1);
}}

/* Top Title Bar (Lighter shade of grey, top 10%) */
QWidget#TitleBar {{
    background-color: {PALETTE['header_bg']};
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    border-bottom: 1px solid rgba(0, 0, 0, 0.3);
    min-height: 40px;
    max-height: 40px;
}}

QLabel#TitleLabel {{
    color: {PALETTE['text_primary']};
    font-size: 13px;
    font-weight: bold;
}}

/* Titlebar Action Buttons */
QToolButton.TitleButton {{
    background-color: transparent;
    border: none;
    border-radius: 14px;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
}}

QToolButton.TitleButton:hover {{
    background-color: {PALETTE['button_hover']};
}}

QToolButton#CloseButton:hover {{
    background-color: {PALETTE['close_hover']};
}}

/* Main Body (Dark grey, 90% of UI) */
QWidget#MainBody {{
    background-color: {PALETTE['window_bg']};
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
}}

/* Elevated Cards */
QFrame.CardFrame {{
    background-color: {PALETTE['card_bg']};
    border: 1px solid {PALETTE['card_border']};
    border-radius: 10px;
}}

/* Text & Labels */
QLabel {{
    color: {PALETTE['text_primary']};
    font-family: 'Cantarell', 'Ubuntu', 'DejaVu Sans', sans-serif;
}}

QLabel.MutedLabel {{
    color: {PALETTE['text_secondary']};
    font-size: 11px;
}}

QLabel.ValueDisplay {{
    font-size: 28px;
    font-weight: bold;
    color: {PALETTE['text_primary']};
}}

/* Form Inputs */
QSpinBox, QDoubleSpinBox {{
    background-color: {PALETTE['card_bg']};
    color: {PALETTE['text_primary']};
    border: 1px solid {PALETTE['card_border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    font-weight: bold;
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {PALETTE['accent_blue']};
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 18px;
    background-color: {PALETTE['button_bg']};
    border: none;
    border-radius: 3px;
    margin: 1px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {PALETTE['button_hover']};
}}

/* Sliders */
QSlider::groove:horizontal {{
    height: 6px;
    background: #333333;
    border-radius: 3px;
}}

QSlider::sub-page:horizontal {{
    background: {PALETTE['accent_blue']};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: #ffffff;
    border: 1px solid #777777;
    width: 16px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background: #e0e0e0;
}}

/* Checkbox / Toggle */
QCheckBox {{
    color: {PALETTE['text_primary']};
    font-size: 12px;
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid {PALETTE['card_border']};
    background-color: {PALETTE['card_bg']};
}}

QCheckBox::indicator:checked {{
    background-color: {PALETTE['accent_blue']};
    border: 1px solid {PALETTE['accent_blue']};
}}

/* Progress Bar */
QProgressBar {{
    background-color: #1a1a1a;
    border: 1px solid #333333;
    border-radius: 6px;
    height: 10px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {PALETTE['accent_blue']}, stop:1 {PALETTE['accent_orange']});
    border-radius: 5px;
}}

/* Action Buttons */
QPushButton.PrimaryButton {{
    background-color: {PALETTE['accent_blue']};
    color: #ffffff;
    font-size: 13px;
    font-weight: bold;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
}}

QPushButton.PrimaryButton:hover {{
    background-color: #4a90e8;
}}

QPushButton.PrimaryButton:pressed {{
    background-color: #2a6ec2;
}}

QPushButton.StopButton {{
    background-color: {PALETTE['accent_red']};
    color: #ffffff;
    font-size: 13px;
    font-weight: bold;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
}}

QPushButton.StopButton:hover {{
    background-color: #eb3b44;
}}

QPushButton.SecondaryButton {{
    background-color: {PALETTE['button_bg']};
    color: {PALETTE['text_primary']};
    font-size: 12px;
    border: 1px solid {PALETTE['card_border']};
    border-radius: 6px;
    padding: 6px 12px;
}}

QPushButton.SecondaryButton:hover {{
    background-color: {PALETTE['button_hover']};
}}

/* Tooltips */
QToolTip {{
    background-color: #2b2b2b;
    color: #ffffff;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 4px 8px;
}}
"""
