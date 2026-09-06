# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from typing import Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QComboBox,
    QToolTip,
)
from ..altium.unit_engine import (
    EngineeringValueParser,
    STANDARD_UNITS,
    PREFIX_MAP,
    ALL_PREFIX_SYMBOLS,
)

logger = logging.getLogger(__name__)


class EngineeringValueEditor(QWidget):
    """
    Interactive in-cell editor for electronic component values with
    metric prefix scale selector, unit dropdown, and live validation.
    """

    editing_finished = Signal()

    def __init__(
        self,
        table_name: str = "",
        col_name: str = "Value",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.table_name = table_name
        self.col_name = col_name

        self.config = EngineeringValueParser.get_column_config(table_name, col_name) or {
            "default_unit": "Ω",
            "allowed_units": ["Ω"],
            "allowed_prefixes": ALL_PREFIX_SYMBOLS,
            "allow_fraction": False,
        }

        self.default_unit = self.config.get("default_unit", "")
        self.allowed_units = self.config.get("allowed_units") or list(STANDARD_UNITS.keys())
        self.allowed_prefixes = self.config.get("allowed_prefixes") or ALL_PREFIX_SYMBOLS

        self._updating_internally = False
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(2)

        # 1. Magnitude Input Field
        self.txt_magnitude = QLineEdit(self)
        self.txt_magnitude.setFixedHeight(26)
        self.txt_magnitude.setPlaceholderText("Value (e.g. 10 or 4k7)")
        self.txt_magnitude.setStyleSheet("""
            QLineEdit {
                background-color: #171724;
                border: 1.5px solid #0099ff;
                border-radius: 3px;
                padding: 1px 4px;
                color: #ffffff;
                font-size: 12px;
                font-weight: 500;
            }
            QLineEdit:focus {
                border-color: #38b0ff;
                background-color: #1c1c2e;
            }
        """)
        self.txt_magnitude.textChanged.connect(self._on_magnitude_text_changed)
        layout.addWidget(self.txt_magnitude, stretch=2)

        # 2. Metric Prefix Scale Combo
        self.cmb_prefix = QComboBox(self)
        self.cmb_prefix.setFixedHeight(26)
        self.cmb_prefix.setFixedWidth(52)
        self.cmb_prefix.setStyleSheet("""
            QComboBox {
                background-color: #222233;
                border: 1px solid #3d3d57;
                border-radius: 3px;
                color: #58a6ff;
                font-weight: bold;
                font-size: 11px;
                padding: 1px 2px;
            }
            QComboBox:hover {
                border-color: #58a6ff;
            }
            QComboBox::drop-down {
                width: 12px;
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a26;
                color: #e0e0f0;
                selection-background-color: #007acc;
                border: 1px solid #3d3d57;
            }
        """)

        # Populate allowed prefixes
        for p in self.allowed_prefixes:
            lbl = p if p else "— (1)"
            self.cmb_prefix.addItem(lbl, userData=p)

        self.cmb_prefix.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self.cmb_prefix)

        # 3. Physical Unit Combo
        self.cmb_unit = QComboBox(self)
        self.cmb_unit.setFixedHeight(26)
        self.cmb_unit.setFixedWidth(44)
        self.cmb_unit.setStyleSheet("""
            QComboBox {
                background-color: #222233;
                border: 1px solid #3d3d57;
                border-radius: 3px;
                color: #40ff80;
                font-weight: bold;
                font-size: 11.5px;
                padding: 1px 2px;
            }
            QComboBox:hover {
                border-color: #40ff80;
            }
            QComboBox::drop-down {
                width: 12px;
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a26;
                color: #e0e0f0;
                selection-background-color: #007acc;
                border: 1px solid #3d3d57;
            }
        """)

        for u in self.allowed_units:
            self.cmb_unit.addItem(u, userData=u)

        self.cmb_unit.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self.cmb_unit)

        self.setFocusProxy(self.txt_magnitude)

    def set_value(self, raw_text: str) -> None:
        """Initialize editor with current cell value string."""
        self._updating_internally = True
        try:
            parsed = EngineeringValueParser.parse(raw_text, default_unit=self.default_unit)
            if parsed["valid"]:
                mag = parsed["magnitude"]
                mag_str = str(int(mag)) if isinstance(mag, float) and mag.is_integer() else str(mag)
                self.txt_magnitude.setText(mag_str)

                # Set prefix combo
                target_pref = parsed["prefix"]
                pref_idx = -1
                for i in range(self.cmb_prefix.count()):
                    if self.cmb_prefix.itemData(i) == target_pref:
                        pref_idx = i
                        break
                if pref_idx >= 0:
                    self.cmb_prefix.setCurrentIndex(pref_idx)

                # Set unit combo
                target_unit = parsed["unit"] or self.default_unit
                unit_idx = -1
                for i in range(self.cmb_unit.count()):
                    if self.cmb_unit.itemData(i) == target_unit:
                        unit_idx = i
                        break
                if unit_idx >= 0:
                    self.cmb_unit.setCurrentIndex(unit_idx)
            else:
                self.txt_magnitude.setText(raw_text)
                # Select default unit
                for i in range(self.cmb_unit.count()):
                    if self.cmb_unit.itemData(i) == self.default_unit:
                        self.cmb_unit.setCurrentIndex(i)
                        break

            self.txt_magnitude.selectAll()
        finally:
            self._updating_internally = False

    def get_value(self) -> str:
        """Construct the canonical formatted value string."""
        mag = self.txt_magnitude.text().strip()
        if not mag:
            return ""

        pref = self.cmb_prefix.currentData() or ""
        unit = self.cmb_unit.currentData() or self.default_unit

        return EngineeringValueParser.format(mag, pref, unit)

    def is_valid(self) -> tuple[bool, str]:
        """Validate current state against engineering rules."""
        if getattr(self, "_unsupported_unit", ""):
            return False, f"Unit '{self._unsupported_unit}' is not allowed for this column. Allowed: {', '.join(self.allowed_units)}"

        raw_val = self.get_value()
        if not raw_val:
            return True, ""  # Empty is acceptable (NULL in DB)

        ok, fmt, err = EngineeringValueParser.validate(
            raw_val,
            table_name=self.table_name,
            col_name=self.col_name,
        )
        return ok, err

    def _on_magnitude_text_changed(self, text: str) -> None:
        """Smart inline typing parser: detects prefix/unit if user typed shorthand."""
        if self._updating_internally:
            return

        raw = text.strip()
        if not raw:
            self._unsupported_unit = ""
            self._set_valid_style(True)
            return

        # Check if user typed shorthand like '4k7', '10k', '4.7u', '100n'
        parsed = EngineeringValueParser.parse(raw, default_unit=self.default_unit)
        if parsed["valid"]:
            # If the user explicitly typed a unit that is NOT allowed in this column:
            raw_unit = parsed.get("unit")
            if raw_unit and raw_unit not in self.allowed_units:
                self._unsupported_unit = raw_unit
                self._set_valid_style(False, f"Unit '{raw_unit}' is not allowed for this column. Allowed: {', '.join(self.allowed_units)}")
                return
            else:
                self._unsupported_unit = ""

            if parsed["prefix"] or (raw_unit and raw_unit != self.default_unit):
                self._updating_internally = True
                try:
                    mag = parsed["magnitude"]
                    mag_str = str(int(mag)) if isinstance(mag, float) and mag.is_integer() else str(mag)
                    self.txt_magnitude.setText(mag_str)

                    target_pref = parsed["prefix"]
                    for i in range(self.cmb_prefix.count()):
                        if self.cmb_prefix.itemData(i) == target_pref:
                            self.cmb_prefix.setCurrentIndex(i)
                            break

                    target_unit = parsed["unit"]
                    for i in range(self.cmb_unit.count()):
                        if self.cmb_unit.itemData(i) == target_unit:
                            self.cmb_unit.setCurrentIndex(i)
                            break
                finally:
                    self._updating_internally = False

        # Live validation feedback
        valid, err = self.is_valid()
        self._set_valid_style(valid, err)

    def _on_combo_changed(self) -> None:
        if self._updating_internally:
            return
        self._unsupported_unit = ""
        valid, err = self.is_valid()
        self._set_valid_style(valid, err)

    def _set_valid_style(self, valid: bool, err_msg: str = "") -> None:
        if valid:
            self.txt_magnitude.setStyleSheet("""
                QLineEdit {
                    background-color: #171724;
                    border: 1.5px solid #0099ff;
                    border-radius: 3px;
                    padding: 1px 4px;
                    color: #ffffff;
                    font-size: 12px;
                    font-weight: 500;
                }
                QLineEdit:focus {
                    border-color: #38b0ff;
                    background-color: #1c1c2e;
                }
            """)
            self.txt_magnitude.setToolTip("")
        else:
            self.txt_magnitude.setStyleSheet("""
                QLineEdit {
                    background-color: #2b1717;
                    border: 1.5px solid #ff4444;
                    border-radius: 3px;
                    padding: 1px 4px;
                    color: #ffffff;
                    font-size: 12px;
                    font-weight: 500;
                }
            """)
            self.txt_magnitude.setToolTip(f"Validation Error: {err_msg}")
            # Display tooltip immediately
            QToolTip.showText(self.mapToGlobal(self.pos()), err_msg, self)
