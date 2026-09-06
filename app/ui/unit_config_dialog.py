# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QWidget,
    QMessageBox,
    QFrame,
)
from ..altium.unit_engine import (
    EngineeringValueParser,
    ColumnUnitConfigManager,
    STANDARD_UNITS,
    ALL_PREFIX_SYMBOLS,
    PREFIX_MAP,
    DEFAULT_TABLE_CONFIG,
)
from .icons import AppIcons

logger = logging.getLogger(__name__)

# Standard prefix presets by unit type for quick selection
STANDARD_UNIT_PREFIX_PRESETS: dict[str, list[str]] = {
    "Ω": ["G", "M", "k", "", "m"],
    "F": ["m", "µ", "n", "p", "f"],
    "H": ["", "m", "µ", "n", "p"],
    "V": ["k", "", "m"],
    "A": ["", "m", "µ", "n"],
    "W": ["k", "", "m"],
    "Hz": ["G", "M", "k", ""],
    "%": [""],
    "dB": [""],
    "s": ["", "m", "µ", "n"],
    "°C": [""],
}


class ColumnUnitConfigDialog(QDialog):
    """
    Dialog allowing the user to configure engineering physical unit,
    allowed scale prefixes, and validation rules for any selected column.
    All UI elements are in English.
    """

    def __init__(
        self,
        table_name: str,
        col_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.table_name = table_name
        self.col_name = col_name
        self.manager = ColumnUnitConfigManager.get_instance()

        self.setWindowTitle(f"Configure Unit & Scale — {col_name} ({table_name})")
        self.setMinimumWidth(480)
        self.setStyleSheet("""
            QDialog {
                background-color: #171724;
                color: #e0e0f0;
            }
            QLabel {
                color: #d0d0e6;
                font-size: 12px;
            }
            QGroupBox {
                border: 1px solid #32324d;
                border-radius: 6px;
                margin-top: 14px;
                padding-top: 14px;
                font-size: 12px;
                font-weight: bold;
                color: #58a6ff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                background-color: #171724;
            }
            QComboBox {
                background-color: #212133;
                border: 1px solid #3d3d5c;
                border-radius: 4px;
                padding: 5px 8px;
                color: #ffffff;
                font-size: 12px;
                font-weight: 500;
            }
            QComboBox:hover {
                border-color: #58a6ff;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e2e;
                color: #ffffff;
                selection-background-color: #007acc;
                border: 1px solid #3d3d5c;
            }
            QCheckBox {
                color: #e0e0f0;
                font-size: 12px;
                spacing: 6px;
            }
            QCheckBox:disabled {
                color: #666680;
            }
            QPushButton {
                background-color: #26263b;
                color: #e0e0f0;
                border: 1px solid #3d3d5c;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #31314d;
                border-color: #58a6ff;
                color: #ffffff;
            }
            QPushButton#PrimaryButton {
                background-color: #1a56db;
                border: 1px solid #2563eb;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton#PrimaryButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton#DangerButton {
                background-color: #3b1818;
                border: 1px solid #772b2b;
                color: #ff8888;
            }
            QPushButton#DangerButton:hover {
                background-color: #521f1f;
                border-color: #ff5555;
                color: #ffffff;
            }
        """)

        self.prefix_checkboxes: dict[str, QCheckBox] = {}
        self._init_ui()
        self._load_current_state()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header banner
        header_layout = QHBoxLayout()
        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(AppIcons.unit_settings().pixmap(28, 28))
        header_layout.addWidget(icon_lbl)

        title_layout = QVBoxLayout()
        lbl_title = QLabel("Column Unit & Scale Configuration")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #58a6ff;")
        lbl_sub = QLabel(f"Table: <b>{self.table_name}</b> &nbsp;|&nbsp; Column: <b>{self.col_name}</b>")
        lbl_sub.setStyleSheet("font-size: 11.5px; color: #a0a0c0;")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_sub)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2b2b40;")
        main_layout.addWidget(sep)

        # Master Checkbox: Enable/Disable unit for this column
        self.chk_enable = QCheckBox("Enable physical unit & metric scale for this column")
        self.chk_enable.setStyleSheet("font-size: 13px; font-weight: bold; color: #40ff80;")
        self.chk_enable.toggled.connect(self._on_enable_toggled)
        main_layout.addWidget(self.chk_enable)

        # Settings Container Widget
        self.container_widget = QWidget(self)
        container_layout = QVBoxLayout(self.container_widget)
        container_layout.setContentsMargins(0, 4, 0, 0)
        container_layout.setSpacing(12)

        # 1. Physical Unit Selection
        unit_layout = QHBoxLayout()
        lbl_unit = QLabel("Physical Unit:")
        lbl_unit.setFixedWidth(110)
        lbl_unit.setStyleSheet("font-weight: 500;")
        unit_layout.addWidget(lbl_unit)

        self.cmb_unit = QComboBox(self.container_widget)
        for sym, u_obj in STANDARD_UNITS.items():
            display_text = f"{sym:<3} — {u_obj.name} ({u_obj.description})"
            self.cmb_unit.addItem(display_text, userData=sym)

        self.cmb_unit.currentIndexChanged.connect(self._on_unit_selection_changed)
        unit_layout.addWidget(self.cmb_unit, stretch=1)
        container_layout.addLayout(unit_layout)

        # 2. Metric Prefix Scale Selector Group
        grp_prefix = QGroupBox("Allowed Metric Scale Prefixes", self.container_widget)
        grp_layout = QVBoxLayout(grp_prefix)
        grp_layout.setSpacing(8)

        # Quick select buttons
        quick_layout = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_all.setFixedHeight(24)
        btn_all.clicked.connect(self._select_all_prefixes)
        quick_layout.addWidget(btn_all)

        btn_preset = QPushButton("Standard Electronic")
        btn_preset.setFixedHeight(24)
        btn_preset.clicked.connect(self._select_preset_prefixes)
        quick_layout.addWidget(btn_preset)

        btn_base = QPushButton("Base Only")
        btn_base.setFixedHeight(24)
        btn_base.clicked.connect(self._select_base_only_prefix)
        quick_layout.addWidget(btn_base)
        quick_layout.addStretch()
        grp_layout.addLayout(quick_layout)

        # Checkboxes Grid (3 columns)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        for idx, sym in enumerate(ALL_PREFIX_SYMBOLS):
            row = idx // 3
            col = idx % 3
            p_obj = PREFIX_MAP.get(sym)
            label_text = p_obj.display_label if p_obj else (sym or "(Base)")
            cb = QCheckBox(label_text, grp_prefix)
            self.prefix_checkboxes[sym] = cb
            grid.addWidget(cb, row, col)

        grp_layout.addLayout(grid)
        container_layout.addWidget(grp_prefix)

        # 3. Fraction option
        self.chk_fractions = QCheckBox("Allow fraction values (e.g. 1/4 W, 1/8 W)", self.container_widget)
        container_layout.addWidget(self.chk_fractions)

        main_layout.addWidget(self.container_widget)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_disable = QPushButton("Disable Unit")
        self.btn_disable.setObjectName("DangerButton")
        self.btn_disable.clicked.connect(self._on_disable_clicked)
        btn_layout.addWidget(self.btn_disable)

        self.btn_reset = QPushButton("Reset to Default")
        self.btn_reset.setToolTip("Reset this column configuration to built-in system defaults")
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        btn_layout.addWidget(self.btn_reset)

        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save & Apply")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.clicked.connect(self._on_save_clicked)
        btn_layout.addWidget(self.btn_save)

        main_layout.addLayout(btn_layout)

    def _on_enable_toggled(self, checked: bool) -> None:
        self.container_widget.setEnabled(checked)

    def _load_current_state(self) -> None:
        cfg = self.manager.get_config(self.table_name, self.col_name)
        has_custom = self.manager.is_customized(self.table_name, self.col_name)
        self.btn_reset.setVisible(has_custom)

        if cfg:
            self.chk_enable.setChecked(True)
            self.container_widget.setEnabled(True)

            # Set unit
            unit = cfg.get("default_unit", "Ω")
            idx = -1
            for i in range(self.cmb_unit.count()):
                if self.cmb_unit.itemData(i) == unit:
                    idx = i
                    break
            if idx >= 0:
                self.cmb_unit.setCurrentIndex(idx)

            # Set prefixes
            allowed_p = cfg.get("allowed_prefixes", ALL_PREFIX_SYMBOLS)
            for p, cb in self.prefix_checkboxes.items():
                cb.setChecked(p in allowed_p)

            # Set fractions
            self.chk_fractions.setChecked(cfg.get("allow_fraction", False))
        else:
            self.chk_enable.setChecked(False)
            self.container_widget.setEnabled(False)

            # Guess default unit from column name
            guessed_unit = self._guess_unit_for_column()
            idx = -1
            for i in range(self.cmb_unit.count()):
                if self.cmb_unit.itemData(i) == guessed_unit:
                    idx = i
                    break
            if idx >= 0:
                self.cmb_unit.setCurrentIndex(idx)

            self._select_preset_prefixes()
            self.chk_fractions.setChecked("power" in self.col_name.lower())

    def _guess_unit_for_column(self) -> str:
        col_low = self.col_name.lower()
        if "volt" in col_low or "v_" in col_low or col_low.endswith("_v"):
            return "V"
        elif "curr" in col_low or "amp" in col_low or "i_" in col_low:
            return "A"
        elif "power" in col_low or "watt" in col_low:
            return "W"
        elif "freq" in col_low or "hz" in col_low:
            return "Hz"
        elif "induct" in col_low:
            return "H"
        elif "capacit" in col_low:
            return "F"
        elif "temp" in col_low or "celsius" in col_low or "deg" in col_low:
            return "°C"
        elif "tol" in col_low or "pct" in col_low:
            return "%"
        elif "time" in col_low or "delay" in col_low:
            return "s"
        elif "gain" in col_low or "db" in col_low or "atten" in col_low:
            return "dB"

        # Table level guess
        t_low = self.table_name.lower()
        if "cap" in t_low:
            return "F"
        elif "ind" in t_low:
            return "H"
        elif "dio" in t_low:
            return "V"
        elif "cryst" in t_low or "osc" in t_low:
            return "Hz"

        return "Ω"

    def _on_unit_selection_changed(self) -> None:
        pass

    def _select_all_prefixes(self) -> None:
        for cb in self.prefix_checkboxes.values():
            cb.setChecked(True)

    def _select_base_only_prefix(self) -> None:
        for p, cb in self.prefix_checkboxes.items():
            cb.setChecked(p == "")

    def _select_preset_prefixes(self) -> None:
        current_unit = self.cmb_unit.currentData() or "Ω"
        preset = STANDARD_UNIT_PREFIX_PRESETS.get(current_unit, [""])
        for p, cb in self.prefix_checkboxes.items():
            cb.setChecked(p in preset)

    def _on_save_clicked(self) -> None:
        if not self.chk_enable.isChecked():
            # User wants unit disabled for this column
            self.manager.disable_config(self.table_name, self.col_name)
            logger.info(f"Disabled unit for [{self.table_name}] '{self.col_name}'")
            self.accept()
            return

        unit = self.cmb_unit.currentData()
        if not unit:
            QMessageBox.warning(self, "Invalid Selection", "Please select a valid unit.")
            return

        selected_prefixes = [p for p in ALL_PREFIX_SYMBOLS if self.prefix_checkboxes[p].isChecked()]
        if not selected_prefixes:
            # At least allow base prefix
            selected_prefixes = [""]

        allow_fraction = self.chk_fractions.isChecked()

        config = {
            "default_unit": unit,
            "allowed_units": [unit],
            "allowed_prefixes": selected_prefixes,
            "allow_fraction": allow_fraction,
        }

        self.manager.set_config(self.table_name, self.col_name, config)
        logger.info(f"Saved unit config for [{self.table_name}] '{self.col_name}': {config}")
        self.accept()

    def _on_disable_clicked(self) -> None:
        self.manager.disable_config(self.table_name, self.col_name)
        logger.info(f"Explicitly disabled unit for [{self.table_name}] '{self.col_name}'")
        self.accept()

    def _on_reset_clicked(self) -> None:
        self.manager.clear_override(self.table_name, self.col_name)
        logger.info(f"Cleared custom override for [{self.table_name}] '{self.col_name}'")
        self.accept()
