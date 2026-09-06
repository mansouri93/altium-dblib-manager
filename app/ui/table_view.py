# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
import re
from typing import Any
from PySide6.QtCore import (
    Qt,
    QAbstractTableModel,
    QAbstractItemModel,
    QModelIndex,
    Signal,
    QSortFilterProxyModel,
)
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QWidget, QLineEdit, QMessageBox
from ..config import SYMBOL_FOOTPRINT_COLUMNS
from ..db.access_manager import AccessDBManager
from ..altium.unit_engine import EngineeringValueParser
from .value_editor import EngineeringValueEditor

logger = logging.getLogger(__name__)

class AltiumFilterProxyModel(QSortFilterProxyModel):
    """
    Sort/filter proxy model for Altium components table that ensures
    spacer and separator rows are always preserved at the bottom when filtering.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFilterKeyColumn(-1)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        src_model = self.sourceModel()
        if hasattr(src_model, "is_spacer_row") and src_model.is_spacer_row(source_row):
            return True
        return super().filterAcceptsRow(source_row, source_parent)


class ComponentsTableModel(QAbstractTableModel):
    """Table model representing records of an Altium DbLib table with spacer row support for split-view alignment."""

    data_saved = Signal(str, int, str, object)  # table_name, row_id, column, value

    def __init__(self, db_manager: AccessDBManager, parent=None) -> None:
        super().__init__(parent)
        self.db_manager = db_manager
        self.current_table: str = ""
        self.columns: list[str] = []
        self.records: list[dict[str, Any]] = []
        self.spacer_count: int = 0
        self.separator_title: str = ""

    def set_spacer_count(self, count: int, separator_title: str = "") -> None:
        count = max(0, count)
        if self.spacer_count == count and self.separator_title == separator_title:
            return
        self.beginResetModel()
        self.spacer_count = count
        self.separator_title = separator_title
        self.endResetModel()

    def load_table(self, table_name: str) -> None:
        self.beginResetModel()
        self.current_table = table_name
        self.spacer_count = 0
        self.separator_title = ""
        if table_name:
            self.columns = self.db_manager.get_columns(table_name)
            self.records = self.db_manager.fetch_records(table_name)
        else:
            self.columns = []
            self.records = []
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.records) + self.spacer_count

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.columns)

    def is_spacer_row(self, row: int) -> bool:
        return row >= len(self.records)

    def is_separator_row(self, row: int) -> bool:
        return self.spacer_count > 0 and row == len(self.records)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= self.rowCount():
            return None

        row = index.row()
        col = index.column()

        # Separator row (matches the warehouse view separator line)
        if self.is_separator_row(row):
            if role == Qt.ItemDataRole.DisplayRole:
                if col == 0:
                    return self.separator_title or "═══ End of Altium Components (Warehouse parts below are unlinked) ═══"
                return ""
            elif role == Qt.ItemDataRole.ForegroundRole:
                return QBrush(QColor("#79c0ff"))
            elif role == Qt.ItemDataRole.BackgroundRole:
                return QBrush(QColor("#1e2330"))
            elif role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            elif role == Qt.ItemDataRole.FontRole:
                font = QFont()
                font.setBold(True)
                font.setPointSize(9)
                return font
            return None

        # Spacer rows (empty placeholder slots for unlinked warehouse parts below)
        if self.is_spacer_row(row):
            if role == Qt.ItemDataRole.BackgroundRole:
                return QBrush(QColor("#14141d"))
            elif role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
                return ""
            return None

        row_data = self.records[row]
        col_name = self.columns[col]
        val = row_data.get(col_name)

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if val is None:
                return ""
            if col_name == "Stock":
                if isinstance(val, float) and val.is_integer():
                    return str(int(val))
                return str(val)
            return str(val)

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col_name == "Stock":
                if val is not None and str(val).strip() != "":
                    m = re.match(r"^\s*([+-]?\d+(?:\.\d+)?)", str(val))
                    if m:
                        try:
                            num = float(m.group(1))
                            if num > 0:
                                return QBrush(QColor("#40ff80"))  # Green for in-stock
                            else:
                                return QBrush(QColor("#ff7070"))  # Red for out-of-stock
                        except (ValueError, TypeError):
                            pass
            elif col_name == "ID":
                return QBrush(QColor("#777799"))
            elif col_name in SYMBOL_FOOTPRINT_COLUMNS:
                return QBrush(QColor("#7e809b"))

        elif role == Qt.ItemDataRole.ToolTipRole:
            if col_name in SYMBOL_FOOTPRINT_COLUMNS:
                return f"{col_name} (System-managed reference - Read-only)"

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section < len(self.columns):
                return self.columns[section]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            if section < len(self.records):
                return str(section + 1)
            return ""
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        if self.is_spacer_row(index.row()):
            return Qt.ItemFlag.NoItemFlags

        col_name = self.columns[index.column()]
        default_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

        # ID, Part Number, and Symbol/Footprint columns are read-only
        if col_name in ("ID", "Part Number") or col_name in SYMBOL_FOOTPRINT_COLUMNS:
            return default_flags

        return default_flags | Qt.ItemFlag.ItemIsEditable

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False

        if self.is_spacer_row(index.row()):
            return False

        col_name = self.columns[index.column()]
        if col_name in ("ID", "Part Number") or col_name in SYMBOL_FOOTPRINT_COLUMNS:
            return False

        row_data = self.records[index.row()]
        row_id = row_data.get("ID")
        if row_id is None:
            return False

        str_val = str(value).strip() if value is not None else ""
        db_val = str_val if str_val != "" else None

        # Update in database
        try:
            ok = self.db_manager.update_cell(self.current_table, row_id, col_name, db_val)
            if ok:
                if col_name in ("Package", "Value", "Tolerance"):
                    refreshed = self.db_manager.fetch_single_record(self.current_table, row_id)
                    if refreshed:
                        row_data.update(refreshed)
                        first_idx = self.index(index.row(), 0)
                        last_idx = self.index(index.row(), len(self.columns) - 1)
                        self.dataChanged.emit(first_idx, last_idx, [Qt.ItemDataRole.DisplayRole])
                        self.data_saved.emit(self.current_table, row_id, col_name, db_val)
                        return True

                row_data[col_name] = db_val
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
                self.data_saved.emit(self.current_table, row_id, col_name, db_val)
                return True
        except Exception as exc:
            logger.error(f"Error saving cell data for {col_name} on row {row_id}: {exc}", exc_info=True)

        return False

    def get_record(self, row: int) -> dict[str, Any] | None:
        if 0 <= row < len(self.records):
            return self.records[row]
        return None

    def update_record_in_model(self, row: int, field_updates: dict[str, Any]) -> None:
        """Update multiple fields of a row in-memory and in DB."""
        if 0 <= row < len(self.records):
            rec = self.records[row]
            row_id = rec.get("ID")
            if row_id is not None:
                clean_updates = {}
                for k, v in field_updates.items():
                    if v is None or str(v).strip() == "":
                        clean_updates[k] = None
                    else:
                        clean_updates[k] = str(v).strip() if isinstance(v, str) else v

                self.db_manager.update_record(self.current_table, row_id, clean_updates)
                rec.update(clean_updates)
                first_idx = self.index(row, 0)
                last_idx = self.index(row, len(self.columns) - 1)
                self.dataChanged.emit(first_idx, last_idx, [Qt.ItemDataRole.DisplayRole])


class TableItemDelegate(QStyledItemDelegate):
    """Custom item delegate supporting specialized EngineeringValueEditor for unit-managed fields."""

    def _get_table_and_column(self, index: QModelIndex) -> tuple[str, str]:
        model = index.model()
        src_idx = model.mapToSource(index) if hasattr(model, "mapToSource") else index
        src_model = src_idx.model()
        table_name = getattr(src_model, "current_table", "")
        col_idx = src_idx.column()
        col_name = src_model.columns[col_idx] if hasattr(src_model, "columns") and col_idx < len(src_model.columns) else ""
        return table_name, col_name

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        table_name, col_name = self._get_table_and_column(index)
        cfg = EngineeringValueParser.get_column_config(table_name, col_name)
        if cfg:
            editor = EngineeringValueEditor(table_name=table_name, col_name=col_name, parent=parent)
            editor.txt_magnitude.returnPressed.connect(lambda: self.commitAndCloseEditor(editor))
            return editor

        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.setStyleSheet(
                "background-color: #1a1a28; color: #ffffff; border: 1.5px solid #0099ff; "
                "border-radius: 3px; padding: 1px 6px; font-size: 12.5px; selection-background-color: #007acc;"
            )
        return editor

    def commitAndCloseEditor(self, editor: QWidget) -> None:
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QStyledItemDelegate.EndEditHint.NoHint)

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        if isinstance(editor, EngineeringValueEditor):
            val = index.data(Qt.ItemDataRole.EditRole)
            if val is None or val == "":
                val = index.data(Qt.ItemDataRole.DisplayRole) or ""
            editor.set_value(str(val))
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex) -> None:
        if isinstance(editor, EngineeringValueEditor):
            ok, err = editor.is_valid()
            if not ok:
                QMessageBox.warning(
                    editor,
                    "Invalid Engineering Value",
                    f"The entered value does not conform to the engineering rules for this column:\n\n{err}",
                )
                return

            val = editor.get_value()
            model.setData(index, val, Qt.ItemDataRole.EditRole)
        else:
            super().setModelData(editor, model, index)

    def updateEditorGeometry(self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        if isinstance(editor, EngineeringValueEditor):
            rect = option.rect
            w = max(rect.width(), 160)
            editor.setGeometry(rect.x(), rect.y(), w, rect.height())
        else:
            editor.setGeometry(option.rect)
