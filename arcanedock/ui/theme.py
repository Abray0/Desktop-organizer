"""Palette and stylesheet, derived from one accent colour.

Everything - glass wash, aurora blooms, text, borders - is generated from a
single hue so the fences take on the Windows accent colour without anything
being hand-tuned per theme.
"""
from __future__ import annotations

from PySide6.QtGui import QColor

# Used when the system accent is switched off: the original arcane violet.
FALLBACK_ACCENT = (169, 139, 255)

# Filled in by set_accent(), which is called once at startup.
INK = "#EEEAFF"
DIM = "#A79FD0"
FAINT = "#7C749E"
ACCENT = "#A98BFF"
ACCENT_RGB = FALLBACK_ACCENT
GLASS: list[QColor] = []
AURORA: list[tuple[float, float, float, QColor]] = []
ACRYLIC_TINT = 0x30140A20


def _hsv(hue: float, sat: float, val: float, alpha: int = 255) -> QColor:
    color = QColor.fromHsvF(hue % 1.0, min(max(sat, 0.0), 1.0),
                            min(max(val, 0.0), 1.0), 1.0)
    color.setAlpha(alpha)
    return color


def set_accent(rgb: tuple[int, int, int] | None = None) -> None:
    """Rebuild the palette around rgb (or the fallback violet when None)."""
    global INK, DIM, FAINT, ACCENT, ACCENT_RGB, GLASS, AURORA, ACRYLIC_TINT

    ACCENT_RGB = rgb or FALLBACK_ACCENT
    base = QColor(*ACCENT_RGB)
    hue = max(base.hueF(), 0.0)          # -1 for greys; clamp to red
    # A nearly grey accent would wash out to flat charcoal, so keep some colour.
    sat = max(base.saturationF(), 0.22)

    # The pane itself: dark, faintly tinted, and see-through enough for the
    # wallpaper to read behind the blur.
    GLASS = [
        _hsv(hue, sat * 0.70, 0.21, 148),
        _hsv(hue, sat * 0.66, 0.14, 156),
        _hsv(hue, sat * 0.60, 0.09, 166),
    ]

    # Soft blooms: the accent, a cool counterpoint, and a warm highlight.
    AURORA = [
        (0.16, 0.02, 0.62, _hsv(hue, sat * 0.85, 0.80, 58)),
        (0.92, 0.86, 0.58, _hsv(hue + 0.42, sat * 0.60, 0.72, 34)),
        (0.62, 0.10, 0.34, _hsv(hue + 0.08, sat * 0.55, 0.95, 20)),
    ]

    ACCENT = _hsv(hue, sat * 0.80, 0.94).name()
    INK = _hsv(hue, 0.05, 0.97).name()
    DIM = _hsv(hue, 0.13, 0.74).name()
    FAINT = _hsv(hue, 0.16, 0.54).name()

    tint = _hsv(hue, sat * 0.6, 0.13)
    ACRYLIC_TINT = ((0x2A << 24) | (tint.blue() << 16)
                    | (tint.green() << 8) | tint.red())


def accent_qcolor(alpha: int = 255) -> QColor:
    color = QColor(ACCENT)
    color.setAlpha(alpha)
    return color


def qss() -> str:
    accent = QColor(ACCENT)
    a = f"{accent.red()},{accent.green()},{accent.blue()}"
    return f"""
QWidget {{
    color: {INK};
    font-family: "Segoe UI Variable Display", "Segoe UI", sans-serif;
    font-size: 13px;
}}
QWidget#Root {{ background: transparent; }}

QLineEdit#Search {{
    background: rgba(255,255,255,0.055);
    border: 1px solid rgba(255,255,255,0.13);
    border-radius: 15px;
    padding: 6px 14px;
    selection-background-color: rgba({a},0.45);
}}
QLineEdit#Search:focus {{
    border: 1px solid rgba({a},0.65);
    background: rgba(255,255,255,0.085);
}}

QLabel#Title {{
    font-family: "Georgia", "Segoe UI", serif;
    font-size: 17px;
    letter-spacing: 1.5px;
    color: {INK};
}}
QLabel#GroupTitle {{
    font-family: "Georgia", serif;
    font-size: 20px;
    letter-spacing: 0.6px;
}}
QLabel#Subtle {{ color: {FAINT}; font-size: 12px; }}
QLabel#Empty {{ color: {FAINT}; font-size: 13px; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,0.16); border-radius: 4px; min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba({a},0.55); }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    height: 0; width: 0; background: none; border: none;
}}

QMenu {{
    background: rgba(26,22,20,0.97);
    border: 1px solid rgba(255,255,255,0.13);
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: rgba({a},0.28); }}
QMenu::separator {{ height: 1px; background: rgba(255,255,255,0.10); margin: 5px 8px; }}
QMenu::indicator {{ width: 14px; height: 14px; margin-left: 8px; }}

QToolTip {{
    background: rgba(26,22,20,0.97);
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 6px; padding: 4px 8px; color: {INK};
}}

QPushButton {{
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 8px; padding: 6px 14px;
}}
QPushButton:hover {{ background: rgba({a},0.22); border-color: rgba({a},0.5); }}
"""


set_accent(None)
