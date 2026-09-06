# -*- coding: utf-8 -*-
"""
Multi-theme styles engine for the Altium DbLib Manager.
Supports Dark Modern, Midnight Navy, Graphite/Obsidian, Nord Dark, and Clean Light.
"""
from __future__ import annotations
from typing import Any
from PySide6.QtWidgets import QApplication, QWidget

# Active runtime theme ID
_ACTIVE_THEME: str = "dark_modern"

THEME_PALETTES: dict[str, dict[str, Any]] = {
    "dark_modern": {
        "id": "dark_modern",
        "name": "Dark Modern (Charcoal & Electric Blue)",
        "desc": "Sleek dark theme with deep charcoal background and electric blue accents.",
        "is_dark": True,
        "bg_window": "#17171e",
        "bg_card": "#1a1a29",
        "bg_surface": "#13131a",
        "bg_input": "#1a1a28",
        "bg_alt_row": "#181822",
        "text_primary": "#ffffff",
        "text_secondary": "#8f8fa8",
        "border_color": "#2b2b3c",
        "accent_color": "#007acc",
        "accent_light": "#58a6ff",
        "accent_hover": "#0099ff",
        "selection_bg": "#124d77",
        "selection_text": "#ffffff",
        "table_grid": "#222230",
        "header_bg_start": "#272737",
        "header_bg_end": "#20202d",
        "toolbar_bg_start": "#232330",
        "toolbar_bg_end": "#1d1d27",
        "statusbar_bg": "#131319",
        "scroll_handle": "#38384d",
        "scroll_hover": "#4f4f6e",
        "btn_bg": "#282839",
        "btn_hover": "#35354b",
        "tab_pill_bg": "#1e1e2d",
        "tab_pill_border": "#383852",
        "swatch": ["#17171e", "#13131a", "#007acc", "#58a6ff"],
    },
    "midnight_navy": {
        "id": "midnight_navy",
        "name": "Midnight Navy (Ocean Deep & Cyan)",
        "desc": "Rich ocean deep blue-gray palette with vibrant cyan and sky accents.",
        "is_dark": True,
        "bg_window": "#0b1329",
        "bg_card": "#111c38",
        "bg_surface": "#080e1e",
        "bg_input": "#122040",
        "bg_alt_row": "#0f1a33",
        "text_primary": "#f0f6fc",
        "text_secondary": "#7dd3fc",
        "border_color": "#1e293b",
        "accent_color": "#0284c7",
        "accent_light": "#38bdf8",
        "accent_hover": "#0ea5e9",
        "selection_bg": "#0369a1",
        "selection_text": "#ffffff",
        "table_grid": "#172554",
        "header_bg_start": "#1e293b",
        "header_bg_end": "#0f172a",
        "toolbar_bg_start": "#111c38",
        "toolbar_bg_end": "#0d172e",
        "statusbar_bg": "#080e1e",
        "scroll_handle": "#1e3a8a",
        "scroll_hover": "#2563eb",
        "btn_bg": "#1e293b",
        "btn_hover": "#334155",
        "tab_pill_bg": "#111c38",
        "tab_pill_border": "#1e3a8a",
        "swatch": ["#0b1329", "#080e1e", "#0284c7", "#38bdf8"],
    },
    "graphite": {
        "id": "graphite",
        "name": "Graphite / Obsidian (Emerald Accent)",
        "desc": "Minimalist obsidian dark mode with vivid emerald green highlights.",
        "is_dark": True,
        "bg_window": "#121214",
        "bg_card": "#18181b",
        "bg_surface": "#0f0f11",
        "bg_input": "#18181b",
        "bg_alt_row": "#141416",
        "text_primary": "#f4f4f5",
        "text_secondary": "#a1a1aa",
        "border_color": "#27272a",
        "accent_color": "#059669",
        "accent_light": "#10b981",
        "accent_hover": "#34d399",
        "selection_bg": "#065f46",
        "selection_text": "#ffffff",
        "table_grid": "#1f1f23",
        "header_bg_start": "#27272a",
        "header_bg_end": "#1c1c1f",
        "toolbar_bg_start": "#1c1c20",
        "toolbar_bg_end": "#141416",
        "statusbar_bg": "#0f0f11",
        "scroll_handle": "#3f3f46",
        "scroll_hover": "#52525b",
        "btn_bg": "#27272a",
        "btn_hover": "#3f3f46",
        "tab_pill_bg": "#1c1c1f",
        "tab_pill_border": "#27272a",
        "swatch": ["#121214", "#0f0f11", "#059669", "#10b981"],
    },
    "nord_dark": {
        "id": "nord_dark",
        "name": "Nord Dark (Arctic Frost & Slate)",
        "desc": "Iconic Arctic Scandinavian color palette with muted slate and frost tones.",
        "is_dark": True,
        "bg_window": "#242933",
        "bg_card": "#2e3440",
        "bg_surface": "#1e222a",
        "bg_input": "#2e3440",
        "bg_alt_row": "#262c37",
        "text_primary": "#eceff4",
        "text_secondary": "#d8dee9",
        "border_color": "#3b4252",
        "accent_color": "#5e81ac",
        "accent_light": "#88c0d0",
        "accent_hover": "#81a1c1",
        "selection_bg": "#434c5e",
        "selection_text": "#ffffff",
        "table_grid": "#2f3542",
        "header_bg_start": "#3b4252",
        "header_bg_end": "#2e3440",
        "toolbar_bg_start": "#2e3440",
        "toolbar_bg_end": "#272c36",
        "statusbar_bg": "#1e222a",
        "scroll_handle": "#4c566a",
        "scroll_hover": "#5e81ac",
        "btn_bg": "#3b4252",
        "btn_hover": "#434c5e",
        "tab_pill_bg": "#2e3440",
        "tab_pill_border": "#434c5e",
        "swatch": ["#242933", "#1e222a", "#5e81ac", "#88c0d0"],
    },
    "light_clean": {
        "id": "light_clean",
        "name": "Clean Light (Slate & Cobalt Day Mode)",
        "desc": "Crisp slate and cobalt light theme engineered for daytime clarity.",
        "is_dark": False,
        "bg_window": "#f1f5f9",
        "bg_card": "#ffffff",
        "bg_surface": "#ffffff",
        "bg_input": "#f8fafc",
        "bg_alt_row": "#f8fafc",
        "text_primary": "#0f172a",
        "text_secondary": "#64748b",
        "border_color": "#cbd5e1",
        "accent_color": "#2563eb",
        "accent_light": "#1d4ed8",
        "accent_hover": "#3b82f6",
        "selection_bg": "#2563eb",
        "selection_text": "#ffffff",
        "table_grid": "#e2e8f0",
        "header_bg_start": "#f8fafc",
        "header_bg_end": "#e2e8f0",
        "toolbar_bg_start": "#ffffff",
        "toolbar_bg_end": "#f1f5f9",
        "statusbar_bg": "#f8fafc",
        "scroll_handle": "#94a3b8",
        "scroll_hover": "#64748b",
        "btn_bg": "#f1f5f9",
        "btn_hover": "#e2e8f0",
        "tab_pill_bg": "#ffffff",
        "tab_pill_border": "#cbd5e1",
        "swatch": ["#f1f5f9", "#ffffff", "#2563eb", "#64748b"],
    },
}

QSS_TEMPLATE = """
/* ================= Base Windows & Dialogs ================= */
QMainWindow, QDialog {{
    background-color: {bg_window};
    color: {text_primary};
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Tahoma', sans-serif;
    font-size: 13px;
}}

QWidget {{
    color: {text_primary};
    background-color: transparent;
}}

/* ================= Splitters ================= */
QSplitter::handle:horizontal {{
    background-color: {border_color};
    width: 4px;
    border-radius: 2px;
    margin: 2px 0px;
}}

QSplitter::handle:horizontal:hover {{
    background-color: {accent_color};
}}

QSplitter::handle:vertical {{
    background-color: {border_color};
    height: 4px;
    border-radius: 2px;
    margin: 0px 2px;
}}

QSplitter::handle:vertical:hover {{
    background-color: {accent_color};
}}

/* ================= ToolBar ================= */
QToolBar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {toolbar_bg_start}, stop:1 {toolbar_bg_end});
    border-bottom: 1px solid {border_color};
    padding: 6px 10px;
    spacing: 8px;
}}

QToolButton {{
    background-color: {btn_bg};
    border: 1px solid {border_color};
    border-radius: 5px;
    padding: 5px 12px;
    color: {text_primary};
    font-weight: 500;
}}

QToolButton:hover {{
    background-color: {btn_hover};
    border-color: {accent_light};
    color: {text_primary};
}}

QToolButton:pressed {{
    background-color: {accent_color};
    border-color: {accent_hover};
    color: #ffffff;
}}

/* ================= Category Sidebar / List ================= */
QListWidget {{
    background-color: {bg_surface};
    border: 1px solid {border_color};
    border-radius: 8px;
    padding: 6px;
    outline: none;
}}

QListWidget::item {{
    padding: 9px 14px;
    border-radius: 6px;
    margin-bottom: 3px;
    color: {text_secondary};
    font-weight: 500;
    font-size: 13px;
    border: 1px solid transparent;
}}

QListWidget::item:hover {{
    background-color: {bg_card};
    color: {text_primary};
    border-color: {border_color};
}}

QListWidget::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent_color}, stop:1 {accent_hover});
    color: #ffffff;
    font-weight: 600;
    border-color: {accent_light};
}}

/* ================= Table View ================= */
QTableView {{
    background-color: {bg_surface};
    border: 1px solid {border_color};
    border-radius: 8px;
    gridline-color: {table_grid};
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
    alternate-background-color: {bg_alt_row};
    outline: none;
}}

QTableView::item {{
    padding: 0px 8px;
    border: none;
    font-size: 12.5px;
}}

QTableView::item:hover {{
    background-color: {bg_card};
}}

QTableView::item:selected {{
    background-color: {selection_bg};
    color: {selection_text};
}}

QTableView QLineEdit {{
    background-color: {bg_input};
    border: 1.5px solid {accent_light};
    border-radius: 3px;
    padding: 1px 6px;
    margin: 0px;
    color: {text_primary};
    font-size: 12.5px;
    selection-background-color: {accent_color};
}}

QHeaderView {{
    background-color: transparent;
    border: none;
}}

QHeaderView::section:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {header_bg_start}, stop:1 {header_bg_end});
    color: {text_secondary};
    padding: 7px 10px;
    border: none;
    border-right: 1px solid {border_color};
    border-bottom: 2px solid {border_color};
    font-weight: 600;
    font-size: 12px;
}}

QHeaderView::section:horizontal:hover {{
    background: {btn_hover};
    color: {text_primary};
}}

QHeaderView::section:horizontal:pressed {{
    background-color: {accent_color};
    color: #ffffff;
}}

QHeaderView::section:vertical {{
    background-color: {bg_window};
    color: {text_secondary};
    padding: 0 4px;
    border: none;
    border-bottom: 1px solid {table_grid};
    font-size: 11px;
}}

/* ================= Buttons ================= */
QPushButton {{
    background-color: {btn_bg};
    border: 1px solid {border_color};
    border-radius: 5px;
    padding: 6px 14px;
    color: {text_primary};
    font-weight: 500;
    font-size: 12.5px;
}}

QPushButton:hover {{
    background-color: {btn_hover};
    border-color: {accent_light};
    color: {text_primary};
}}

QPushButton:pressed {{
    background-color: {accent_color};
    border-color: {accent_color};
    color: #ffffff;
}}

QPushButton#PrimaryButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {accent_hover}, stop:1 {accent_color});
    border: 1px solid {accent_light};
    color: #ffffff;
    font-weight: 600;
}}

QPushButton#PrimaryButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {accent_light}, stop:1 {accent_hover});
    border-color: {accent_light};
}}

QPushButton#PrimaryButton:pressed {{
    background-color: {accent_color};
}}

QPushButton#SuccessButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #228a47, stop:1 #196936);
    border: 1px solid #28a745;
    color: #ffffff;
    font-weight: 600;
}}

QPushButton#SuccessButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #28a053, stop:1 #1e7e41);
    border-color: #34c759;
}}

QPushButton#DangerButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8f2626, stop:1 #721e1e);
    border: 1px solid #a82e2e;
    color: #ffffff;
    font-weight: 600;
}}

QPushButton#DangerButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #a62d2d, stop:1 #842323);
    border-color: #c93b3b;
}}

/* ================= Input Fields ================= */
QLineEdit {{
    background-color: {bg_surface};
    border: 1px solid {border_color};
    border-radius: 6px;
    padding: 7px 12px;
    color: {text_primary};
    font-size: 12.5px;
    selection-background-color: {accent_color};
}}

QLineEdit:hover {{
    border-color: {accent_light};
}}

QLineEdit:focus {{
    border-color: {accent_color};
    background-color: {bg_input};
}}

/* ================= GroupBox & Panels ================= */
QGroupBox {{
    background-color: {bg_window};
    border: 1px solid {border_color};
    border-radius: 8px;
    margin-top: 16px;
    font-weight: 600;
    color: {text_secondary};
    padding-top: 14px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    left: 12px;
    background-color: {bg_card};
    border: 1px solid {border_color};
    border-radius: 4px;
    color: {text_primary};
    font-size: 12px;
}}

QFrame#CardFrame {{
    background-color: {bg_card};
    border: 1px solid {border_color};
    border-radius: 8px;
}}

/* ================= Graphics View ================= */
QGraphicsView {{
    background-color: {bg_surface};
    border: 1px solid {border_color};
    border-radius: 6px;
}}

/* ================= Modern Floating Pill ScrollBars ================= */
QScrollBar:vertical {{
    background-color: {bg_surface};
    width: 12px;
    margin: 0px;
    border-radius: 6px;
}}

QScrollBar::handle:vertical {{
    background-color: {scroll_handle};
    min-height: 32px;
    border-radius: 4px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {scroll_hover};
}}

QScrollBar::handle:vertical:pressed {{
    background-color: {accent_color};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    background: none;
    border: none;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background-color: {bg_surface};
    height: 12px;
    margin: 0px;
    border-radius: 6px;
}}

QScrollBar::handle:horizontal {{
    background-color: {scroll_handle};
    min-width: 32px;
    border-radius: 4px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {scroll_hover};
}}

QScrollBar::handle:horizontal:pressed {{
    background-color: {accent_color};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
    background: none;
    border: none;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

QScrollBar::corner {{
    background-color: {bg_surface};
}}

/* ================= Context Menu ================= */
QMenu {{
    background-color: {bg_card};
    border: 1px solid {border_color};
    border-radius: 7px;
    padding: 6px;
    color: {text_primary};
}}

QMenu::item {{
    padding: 7px 26px 7px 12px;
    border-radius: 5px;
    margin: 1px 0px;
    font-size: 12.5px;
}}

QMenu::item:selected {{
    background-color: {accent_color};
    color: #ffffff;
}}

QMenu::separator {{
    height: 1px;
    background-color: {border_color};
    margin: 4px 6px;
}}

/* ================= TabWidget & TabBar ================= */
QTabWidget::pane {{
    border: 1px solid {border_color};
    background-color: {bg_card};
    border-radius: 6px;
    top: -1px;
}}

QTabBar::tab {{
    background-color: {bg_window};
    color: {text_secondary};
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid {border_color};
    border-bottom: none;
    font-size: 12px;
    font-weight: 500;
}}

QTabBar::tab:selected {{
    background-color: {bg_card};
    color: {accent_light};
    border-bottom: 2px solid {accent_color};
    font-weight: bold;
}}

QTabBar::tab:hover:!selected {{
    background-color: {btn_hover};
    color: {text_primary};
}}

/* ================= ComboBox & SpinBox ================= */
QComboBox {{
    background-color: {bg_surface};
    border: 1px solid {border_color};
    border-radius: 5px;
    padding: 5px 10px;
    color: {text_primary};
    font-size: 12px;
}}

QComboBox:hover {{
    border-color: {accent_light};
}}

QComboBox:focus {{
    border-color: {accent_color};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid {border_color};
}}

QComboBox QAbstractItemView {{
    background-color: {bg_card};
    border: 1px solid {border_color};
    color: {text_primary};
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
}}

/* ================= CheckBox & RadioButton ================= */
QCheckBox, QRadioButton {{
    color: {text_primary};
    spacing: 8px;
    font-size: 12px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {border_color};
    border-radius: 3px;
    background-color: {bg_surface};
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {accent_light};
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {accent_color};
    border-color: {accent_hover};
}}

/* ================= StatusBar ================= */
QStatusBar {{
    background-color: {statusbar_bg};
    border-top: 1px solid {border_color};
    color: {text_secondary};
    font-size: 11.5px;
    padding: 2px 4px;
}}

/* ================= Progress Bar ================= */
QProgressBar {{
    background-color: {bg_window};
    border: 1px solid {border_color};
    border-radius: 6px;
    text-align: center;
    color: {text_primary};
    font-weight: 600;
}}

QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent_color}, stop:1 {accent_light});
    border-radius: 5px;
}}
"""

def get_available_themes() -> list[dict[str, Any]]:
    """Returns metadata for all registered themes."""
    return list(THEME_PALETTES.values())

def get_theme_palette(theme_id: str | None = None) -> dict[str, Any]:
    """Returns color dictionary for a given theme ID, defaulting to active theme."""
    global _ACTIVE_THEME
    tid = theme_id or _ACTIVE_THEME or "dark_modern"
    return dict(THEME_PALETTES.get(tid, THEME_PALETTES["dark_modern"]))

def get_theme_qss(theme_id: str | None = None) -> str:
    """Generates complete Qt stylesheet string for the specified theme ID."""
    palette = get_theme_palette(theme_id)
    return QSS_TEMPLATE.format(**palette)

def get_current_theme_id() -> str:
    """Returns the ID of the currently active theme."""
    global _ACTIVE_THEME
    return _ACTIVE_THEME

def apply_theme(theme_id: str, app_or_target: QApplication | QWidget | None = None) -> None:
    """
    Applies the specified theme to the application or target widget.
    Updates the global _ACTIVE_THEME state.
    """
    global _ACTIVE_THEME
    if theme_id not in THEME_PALETTES:
        theme_id = "dark_modern"
    _ACTIVE_THEME = theme_id
    qss = get_theme_qss(theme_id)

    target = app_or_target or QApplication.instance()
    if target is not None:
        target.setStyleSheet(qss)

# Backwards compatibility
DARK_THEME_QSS = get_theme_qss("dark_modern")
