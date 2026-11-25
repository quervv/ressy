from __future__ import annotations

from PySide6 import QtSvg
from PySide6.QtGui import QColor, QFont, QFontDatabase

from ..paths import resource_path

PLATE = "#17181C"
MODS = "#2A2C33"
LEGEND = "#E9E6DF"
ACCENT = "#9D6BFF"
LILAC = "#C9B6FF"
BACKLIGHT = "#4DF0B5"

PLATE_EDGE = "#2E3038"
FIELD = "#202228"
FIELD_EDGE = "#3A3D46"
MODS_SKIRT = "#1E1F24"
ACCENT_SKIRT = "#6E45D6"
LEGEND_DIM = "#A9A69F"
REST = "#3A3D46"
INK = "#17181C"

STATE_LABELS = {
    "asleep": "Dorme",
    "listening": "Ascolta",
    "hearing": "Ascolta",
    "thinking": "Pensa",
    "speaking": "Parla",
}
OFFLINE_LABEL = "Offline"

_family: str | None = None


def family() -> str:
    global _family
    if _family is None:
        path = resource_path("assets/fonts/Archivo-VF.ttf")
        font_id = QFontDatabase.addApplicationFont(str(path)) if path.exists() else -1
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        _family = families[0] if families else "Segoe UI"
    return _family


def font(px: float, weight: int = 400, width: float = 100.0) -> QFont:
    weight = max(100, min(int(weight), 900))
    f = QFont(family())
    f.setPixelSize(max(1, round(px)))
    f.setWeight(QFont.Weight(round(weight / 100) * 100))
    if hasattr(f, "setVariableAxis"):
        if width != 100:
            f.setVariableAxis(QFont.Tag("wdth"), float(width))
        if weight % 100:
            f.setVariableAxis(QFont.Tag("wght"), float(weight))
    return f


def color(value: str, alpha: float = 1.0) -> QColor:
    c = QColor(value)
    c.setAlphaF(max(0.0, min(alpha, 1.0)))
    return c


def _asset_url(name: str) -> str:
    return resource_path(f"assets/ui/{name}").as_posix()


def stylesheet() -> str:
    fam = family()
    chevron = _asset_url("chevron-down.svg")
    check = _asset_url("check.svg")
    return f"""
    QWidget {{
        color: {LEGEND};
        font-family: "{fam}";
        font-size: 14px;
    }}
    QDialog, QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget {{
        background: {PLATE};
    }}
    QLabel#title {{
        font-size: 22px;
        font-weight: 700;
    }}
    QLabel#section {{
        font-size: 12px;
        font-weight: 700;
        color: {LEGEND_DIM};
        padding-top: 14px;
    }}
    QLabel#hint, QCheckBox#hint {{
        color: {LEGEND_DIM};
        font-size: 13px;
    }}
    QLabel#error {{
        color: #FF8C73;
        font-size: 13px;
    }}
    QLabel#ok {{
        color: {BACKLIGHT};
        font-size: 13px;
    }}
    QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{
        background: {FIELD};
        border: 1px solid {FIELD_EDGE};
        border-radius: 6px;
        padding: 7px 10px;
        selection-background-color: {ACCENT};
        selection-color: {INK};
        min-height: 20px;
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
        border: 1px solid {ACCENT};
    }}
    QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
        color: #6E6C68;
        border-color: {PLATE_EDGE};
    }}
    QComboBox::drop-down {{ border: none; width: 30px; }}
    QComboBox::down-arrow {{ image: url("{chevron}"); width: 12px; height: 8px; }}
    QComboBox QAbstractItemView {{
        background: {FIELD};
        border: 1px solid {FIELD_EDGE};
        selection-background-color: {MODS};
        selection-color: {LEGEND};
        outline: none;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
    QPushButton {{
        background: {MODS};
        color: {LEGEND};
        border: 1px solid #383A42;
        border-bottom: 4px solid {MODS_SKIRT};
        border-radius: 7px;
        padding: 7px 16px 6px 16px;
        font-weight: 600;
        min-height: 20px;
    }}
    QPushButton:hover {{ background: #33363E; }}
    QPushButton:pressed {{
        border-bottom-width: 1px;
        margin-top: 3px;
        padding-bottom: 6px;
    }}
    QPushButton:focus {{ border: 1px solid {ACCENT}; border-bottom: 4px solid {MODS_SKIRT}; }}
    QPushButton:disabled {{ color: #6E6C68; background: #24262C; }}
    QPushButton#primary {{
        background: {ACCENT};
        color: {INK};
        border: 1px solid #B08CFF;
        border-bottom: 4px solid {ACCENT_SKIRT};
    }}
    QPushButton#primary:hover {{ background: #AE85FF; }}
    QPushButton#primary:focus {{ border: 1px solid {LEGEND}; border-bottom: 4px solid {ACCENT_SKIRT}; }}
    QPushButton#primary:disabled {{
        background: #2B2638;
        color: #7D7591;
        border: 1px solid #3A3450;
        border-bottom: 4px solid #221E2C;
    }}
    QPushButton#link {{
        background: transparent;
        border: none;
        color: {LEGEND};
        text-decoration: underline;
        padding: 0;
        font-weight: 400;
    }}
    QCheckBox {{ spacing: 10px; }}
    QCheckBox::indicator {{
        width: 18px; height: 18px;
        border-radius: 4px;
        border: 1px solid {FIELD_EDGE};
        background: {FIELD};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border: 1px solid {ACCENT};
        image: url("{check}");
    }}
    QCheckBox::indicator:focus {{ border: 1px solid {LEGEND}; }}
    QRadioButton {{ spacing: 10px; font-weight: 600; }}
    QRadioButton::indicator {{
        width: 16px; height: 16px;
        border-radius: 9px;
        border: 1px solid {FIELD_EDGE};
        background: {FIELD};
    }}
    QRadioButton::indicator:checked {{
        border: 5px solid {ACCENT};
        background: {INK};
        width: 8px; height: 8px;
    }}
    QRadioButton::indicator:focus {{ border-color: {LEGEND}; }}
    QSlider::groove:horizontal {{
        height: 4px; background: {FIELD_EDGE}; border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        width: 16px; height: 16px; margin: -7px 0;
        border-radius: 4px; background: {LEGEND};
    }}
    QListWidget#nav {{
        background: {PLATE};
        border: none;
        outline: none;
        padding: 4px;
    }}
    QListWidget#nav::item {{
        background: {MODS};
        border: 1px solid #383A42;
        border-bottom: 4px solid {MODS_SKIRT};
        border-radius: 7px;
        margin: 0 0 8px 0;
        padding: 9px 12px;
        font-weight: 600;
    }}
    QListWidget#nav::item:selected {{
        background: {ACCENT};
        color: {INK};
        border: 1px solid #B08CFF;
        border-bottom: 1px solid {ACCENT_SKIRT};
        margin-top: 3px;
        margin-bottom: 5px;
    }}
    QListWidget#links {{
        background: {FIELD};
        border: 1px solid {FIELD_EDGE};
        border-radius: 6px;
        padding: 4px;
    }}
    QProgressBar {{
        background: {FIELD};
        border: 1px solid {PLATE_EDGE};
        border-radius: 4px;
    }}
    QProgressBar::chunk {{
        border-radius: 3px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_SKIRT}, stop:1 {LILAC});
    }}
    QScrollBar:vertical {{ background: {PLATE}; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {FIELD_EDGE}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QToolTip {{
        background: {MODS}; color: {LEGEND}; border: 1px solid {FIELD_EDGE}; padding: 6px;
    }}
    QMenu {{
        background: {PLATE};
        border: 1px solid {PLATE_EDGE};
        padding: 6px;
    }}
    QMenu::item {{ padding: 7px 22px 7px 14px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {MODS}; }}
    QMenu::item:disabled {{ color: {LEGEND_DIM}; }}
    QMenu::separator {{ height: 1px; background: {PLATE_EDGE}; margin: 6px 4px; }}
    QMessageBox {{ background: {PLATE}; }}
    """
