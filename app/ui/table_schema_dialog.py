# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from typing import Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QMessageBox,
    QHeaderView,
    QFrame,
    QGroupBox,
    QGridLayout,
    QWidget,
)
from ..db.access_manager import AccessDBManager
from .icons import AppIcons
from .smooth_scroll import enable_smooth_scroll

logger = logging.getLogger(__name__)


class FieldEditDialog(QDialog):
    """Dialog to add or edit a field, with support for Calculated formula and type detection."""

    def __init__(
        self,
        existing_names: list[str],
        field_data: dict[str, Any] | None = None,
        is_part_number: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.raw_existing_names = [str(n) for n in existing_names]
        self.existing_names = [n.lower() for n in existing_names]
        self.is_edit = field_data is not None
        self.is_part_number = is_part_number

        title = "Edit Field" if self.is_edit else "Add New Field"
        self.setWindowTitle(title)
        self.resize(520, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Field Name
        layout.addWidget(QLabel("Field Name:"))
        self.txt_name = QLineEdit(self)
        self.txt_name.setPlaceholderText("e.g. Resistance, Operating Voltage, Package...")
        if self.is_edit and field_data:
            self.txt_name.setText(field_data.get("name", ""))
            if self.is_part_number or field_data.get("name", "").upper() == "ID":
                self.txt_name.setReadOnly(True)
                self.txt_name.setStyleSheet("background-color: #212130; color: #8f8fa8;")
        layout.addWidget(self.txt_name)

        # Data Type
        layout.addWidget(QLabel("Data Type:"))
        self.cb_type = QComboBox(self)
        self.cb_type.addItem("Short Text (VARCHAR 255)", "short_text")
        self.cb_type.addItem("Long Text (MEMO - For file paths & long notes)", "long_text")
        self.cb_type.addItem("Calculated Field (Formula / Expression)", "calculated")

        if self.is_edit and field_data:
            t = field_data.get("type", "short_text")
            idx = self.cb_type.findData(t)
            if idx >= 0:
                self.cb_type.setCurrentIndex(idx)
        layout.addWidget(self.cb_type)

        # Auto-detect long text for path fields when typing name
        if not self.is_edit:
            self.txt_name.textChanged.connect(self._on_name_text_changed)

        # Formula / Expression Group (visible when Calculated is chosen)
        self.grp_calc = QGroupBox("Calculated Field Expression (Access Formula)", self)
        calc_layout = QVBoxLayout(self.grp_calc)
        calc_layout.setSpacing(8)

        lbl_formula_hint = QLabel(
            "Enter formula combining other fields, e.g.:<br>"
            "<code>'R-' &amp; [Package] &amp; '-' &amp; [Value] &amp; '-' &amp; [Tolerance]</code>"
        )
        lbl_formula_hint.setStyleSheet("font-size: 11px; color: #79c0ff; line-height: 1.3;")
        calc_layout.addWidget(lbl_formula_hint)

        self.txt_expr = QLineEdit(self)
        self.txt_expr.setPlaceholderText('[Prefix] & "-" & [Value]')
        if self.is_edit and field_data:
            self.txt_expr.setText(field_data.get("expression", ""))
        calc_layout.addWidget(self.txt_expr)

        # Dropdown to insert any field in the table
        insert_row = QHBoxLayout()
        insert_row.setSpacing(6)
        insert_row.addWidget(QLabel("Insert Field:"))
        self.cb_insert_field = QComboBox(self)
        for fn in self.raw_existing_names:
            if fn.upper() != "ID" and (not field_data or fn.lower() != field_data.get("name", "").lower()):
                self.cb_insert_field.addItem(fn)
        insert_row.addWidget(self.cb_insert_field, stretch=1)

        self.btn_insert_selected = QPushButton("+ Insert Field")
        self.btn_insert_selected.setFixedHeight(26)
        self.btn_insert_selected.clicked.connect(self._on_insert_selected_field)
        insert_row.addWidget(self.btn_insert_selected)
        calc_layout.addLayout(insert_row)

        # Quick clickable chips for all available fields
        tags_lbl = QLabel("Quick field chips (click to insert):")
        tags_lbl.setStyleSheet("font-size: 11px; color: #9a9ab5;")
        calc_layout.addWidget(tags_lbl)

        chips_widget = QWidget(self)
        chips_layout = QGridLayout(chips_widget)
        chips_layout.setContentsMargins(0, 0, 0, 0)
        chips_layout.setSpacing(4)

        col_idx = 0
        row_idx = 0
        MAX_COLS = 4
        for fn in self.raw_existing_names:
            if fn.upper() != "ID" and (not field_data or fn.lower() != field_data.get("name", "").lower()):
                btn_tag = QPushButton(f"[{fn}]")
                btn_tag.setFixedHeight(24)
                btn_tag.setStyleSheet("font-size: 11px; padding: 2px 6px; background-color: #26263a;")
                btn_tag.clicked.connect(lambda _, t=fn: self._insert_tag(t))
                chips_layout.addWidget(btn_tag, row_idx, col_idx)
                col_idx += 1
                if col_idx >= MAX_COLS:
                    col_idx = 0
                    row_idx += 1

        calc_layout.addWidget(chips_widget)
        layout.addWidget(self.grp_calc)

        self.cb_type.currentIndexChanged.connect(self._on_type_changed)
        self._on_type_changed()

        layout.addStretch()

        # Dialog Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Save Field")
        btn_save.setObjectName("PrimaryButton")
        btn_save.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def _on_name_text_changed(self, text: str) -> None:
        """Automatically suggest Long Text for file path fields."""
        if "path" in text.lower():
            idx = self.cb_type.findData("long_text")
            if idx >= 0:
                self.cb_type.setCurrentIndex(idx)

    def _on_type_changed(self) -> None:
        is_calc = self.cb_type.currentData() == "calculated"
        self.grp_calc.setVisible(is_calc)

    def _on_insert_selected_field(self) -> None:
        field_name = self.cb_insert_field.currentText().strip()
        if field_name:
            self._insert_tag(field_name)

    def _insert_tag(self, field_name: str) -> None:
        curr = self.txt_expr.text()
        tag = f"[{field_name}]"
        if curr and not curr.rstrip().endswith("&"):
            tag = f" & {tag}"
        self.txt_expr.setText(curr + tag)
        self.txt_expr.setFocus()

    def _validate_and_accept(self) -> None:
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a field name.")
            return

        # Check for duplicates on add or rename
        if not self.is_edit or (self.is_edit and self.txt_name.isModified()):
            if name.lower() in self.existing_names:
                QMessageBox.warning(self, "Duplicate Field", f"A field named '{name}' already exists.")
                return

        ftype = self.cb_type.currentData()
        if ftype == "calculated":
            raw_expr = self.txt_expr.text().strip()
            if not raw_expr:
                QMessageBox.warning(self, "Formula Required", "Please enter a formula expression for the calculated field.")
                return

            import re
            import difflib

            # Find all bracketed references [ColumnName]
            bracketed = re.findall(r"\[(.*?)\]", raw_expr)
            avail_map = {n.lower(): n for n in self.raw_existing_names if n.upper() != "ID"}

            invalid_refs = []
            for ref in bracketed:
                ref_clean = ref.strip()
                if ref_clean.lower() not in avail_map:
                    matches = difflib.get_close_matches(ref_clean.lower(), list(avail_map.keys()), n=1, cutoff=0.5)
                    if matches:
                        sugg = avail_map[matches[0]]
                        invalid_refs.append(f"• '[{ref_clean}]' -> Did you mean '[{sugg}]'?")
                    else:
                        invalid_refs.append(f"• '[{ref_clean}]' (column not found in table)")

            if invalid_refs:
                available_str = ", ".join(f"[{avail_map[k]}]" for k in avail_map)
                msg = (
                    "The formula references invalid or misspelled field names:\n\n"
                    + "\n".join(invalid_refs)
                    + "\n\nAvailable table fields:\n"
                    + available_str
                )
                QMessageBox.warning(self, "Invalid Formula Field", msg)
                return

            # Auto-correct casing of referenced fields to match exact database column name
            fixed_expr = raw_expr
            for ref in bracketed:
                ref_clean = ref.strip()
                if ref_clean.lower() in avail_map:
                    exact = avail_map[ref_clean.lower()]
                    if ref != exact:
                        fixed_expr = re.sub(rf"\[\s*{re.escape(ref)}\s*\]", f"[{exact}]", fixed_expr)
            self.txt_expr.setText(fixed_expr)

        self.accept()

    def get_data(self) -> dict[str, Any]:
        return {
            "name": self.txt_name.text().strip(),
            "type": self.cb_type.currentData(),
            "expression": self.txt_expr.text().strip() if self.cb_type.currentData() == "calculated" else "",
        }


class TableSchemaDialog(QDialog):
    """
    Comprehensive dialog to inspect, add, edit, and delete fields of an Access table.
    Enforces mandatory ID and Part Number, supports Short/Long Text and Calculated fields.
    """

    schema_changed = Signal(str)  # table_name

    def __init__(self, db_manager: AccessDBManager, table_name: str, parent=None) -> None:
        super().__init__(parent)
        self.db_manager = db_manager
        self.table_name = table_name

        self.setWindowTitle(f"Manage Table Fields — [{self.table_name}]")
        self.resize(780, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header info
        header_layout = QHBoxLayout()
        header_lbl = QLabel(f"Table Schema: <b>{self.table_name}</b>")
        header_lbl.setStyleSheet("font-size: 14px; color: #ffffff;")
        header_layout.addWidget(header_lbl)
        header_layout.addStretch()

        self.lbl_field_count = QLabel("")
        self.lbl_field_count.setStyleSheet("color: #8f8fa8; font-size: 12px;")
        header_layout.addWidget(self.lbl_field_count)
        layout.addLayout(header_layout)

        # Fields Table Widget
        self.tbl_fields = QTableWidget(self)
        self.tbl_fields.setColumnCount(4)
        self.tbl_fields.setHorizontalHeaderLabels(["Field Name", "Data Type", "Formula / Expression", "Status / Role"])
        self.tbl_fields.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tbl_fields.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.tbl_fields.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_fields.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.tbl_fields.setColumnWidth(0, 190)
        self.tbl_fields.setColumnWidth(1, 140)
        self.tbl_fields.setColumnWidth(3, 150)
        self.tbl_fields.verticalHeader().setVisible(False)
        self.tbl_fields.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_fields.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        enable_smooth_scroll(self.tbl_fields, step_v=30, step_h=50)
        layout.addWidget(self.tbl_fields, stretch=1)

        # Buttons Toolbar
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_add = QPushButton(" + Add Field")
        self.btn_add.setObjectName("PrimaryButton")
        self.btn_add.setIcon(AppIcons.add())
        self.btn_add.clicked.connect(self._on_add_field)
        btn_layout.addWidget(self.btn_add)

        self.btn_edit = QPushButton(" Edit Field...")
        self.btn_edit.setIcon(AppIcons.edit())
        self.btn_edit.clicked.connect(self._on_edit_field)
        btn_layout.addWidget(self.btn_edit)

        self.btn_delete = QPushButton(" Delete Field")
        self.btn_delete.setIcon(AppIcons.delete())
        self.btn_delete.clicked.connect(self._on_delete_field)
        btn_layout.addWidget(self.btn_delete)

        btn_layout.addStretch()

        self.btn_refresh = QPushButton(" Refresh")
        self.btn_refresh.setIcon(AppIcons.refresh())
        self.btn_refresh.clicked.connect(self._load_schema)
        btn_layout.addWidget(self.btn_refresh)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

        self.tbl_fields.selectionModel().selectionChanged.connect(self._update_action_button_states)
        self.tbl_fields.doubleClicked.connect(self._on_edit_field)

        self._load_schema()

    def _load_schema(self) -> None:
        self.schema = self.db_manager.get_table_schema(self.table_name)
        self.tbl_fields.setRowCount(len(self.schema))
        self.lbl_field_count.setText(f"{len(self.schema)} fields")

        for row, f in enumerate(self.schema):
            fname = f.get("name", "")
            ftype = f.get("type", "short_text")
            expr = f.get("expression", "")
            is_pk = f.get("is_primary_key", False)
            is_mandatory = f.get("is_mandatory", False)

            # 1. Field Name
            it_name = QTableWidgetItem(fname)
            if is_pk or is_mandatory:
                it_name.setForeground(Qt.GlobalColor.white)
            self.tbl_fields.setItem(row, 0, it_name)

            # 2. Data Type Display
            type_label = "Short Text"
            if ftype == "autonumber":
                type_label = "AutoNumber"
            elif ftype == "long_text":
                type_label = "Long Text (Memo)"
            elif ftype == "calculated":
                type_label = "Calculated (Formula)"
            it_type = QTableWidgetItem(type_label)
            if ftype == "calculated":
                it_type.setForeground(Qt.GlobalColor.cyan)
            self.tbl_fields.setItem(row, 1, it_type)

            # 3. Formula
            it_expr = QTableWidgetItem(expr or "—")
            if expr:
                it_expr.setForeground(Qt.GlobalColor.yellow)
            self.tbl_fields.setItem(row, 2, it_expr)

            # 4. Status / Role
            status_str = "Optional"
            if is_pk:
                status_str = "Primary Key (Auto)"
            elif fname.upper() == "PART NUMBER":
                status_str = "Mandatory (Core)"
            elif "Path" in fname:
                status_str = "File Path (System)"
            it_status = QTableWidgetItem(status_str)
            if is_pk or fname.upper() == "PART NUMBER":
                it_status.setForeground(Qt.GlobalColor.green)
            self.tbl_fields.setItem(row, 3, it_status)

        self._update_action_button_states()

    def _get_selected_field(self) -> dict[str, Any] | None:
        rows = self.tbl_fields.selectionModel().selectedRows()
        if not rows:
            return None
        r = rows[0].row()
        if 0 <= r < len(self.schema):
            return self.schema[r]
        return None

    def _update_action_button_states(self) -> None:
        f = self._get_selected_field()
        if not f:
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)
            return

        fname = f.get("name", "").upper()
        if fname == "ID":
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)
        elif fname == "PART NUMBER":
            self.btn_edit.setEnabled(True)   # Can edit formula or switch to text
            self.btn_delete.setEnabled(False) # Mandatory! Cannot delete
        else:
            self.btn_edit.setEnabled(True)
            self.btn_delete.setEnabled(True)

    def _on_add_field(self) -> None:
        existing_names = [f["name"] for f in self.schema]
        dialog = FieldEditDialog(existing_names=existing_names, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            fname = data["name"]
            ftype = data["type"]
            fexpr = data["expression"]

            try:
                self.db_manager.add_column(self.table_name, fname, ftype, fexpr)
                self._load_schema()
                self.schema_changed.emit(self.table_name)
                QMessageBox.information(self, "Field Added", f"Field '{fname}' was added successfully.")
            except Exception as exc:
                logger.error(f"Failed to add field: {exc}", exc_info=True)
                QMessageBox.critical(self, "Error Adding Field", f"Failed to add field:\n{exc}")

    def _on_edit_field(self) -> None:
        f = self._get_selected_field()
        if not f:
            return

        fname = f.get("name", "")
        if fname.upper() == "ID":
            QMessageBox.warning(self, "Protected Field", "The 'ID' AutoNumber primary key cannot be modified.")
            return

        is_pn = fname.upper() == "PART NUMBER"
        other_names = [x["name"] for x in self.schema if x["name"] != fname]
        dialog = FieldEditDialog(existing_names=other_names, field_data=f, is_part_number=is_pn, parent=self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            new_name = data["name"]
            new_type = data["type"]
            new_expr = data["expression"]

            try:
                self.db_manager.edit_column(self.table_name, fname, new_name, new_type, new_expr)
                self._load_schema()
                self.schema_changed.emit(self.table_name)
                QMessageBox.information(self, "Field Updated", f"Field '{new_name}' was updated successfully.")
            except Exception as exc:
                logger.error(f"Failed to edit field: {exc}", exc_info=True)
                QMessageBox.critical(self, "Error Updating Field", f"Failed to update field:\n{exc}")

    def _on_delete_field(self) -> None:
        f = self._get_selected_field()
        if not f:
            return

        fname = f.get("name", "")
        if fname.upper() in ("ID", "PART NUMBER"):
            QMessageBox.warning(self, "Mandatory Field", f"The '{fname}' field is mandatory and cannot be deleted.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Field Deletion",
            f"Are you sure you want to permanently delete column '{fname}' from table '{self.table_name}'?\n\n"
            f"All data stored in this column across all records will be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self.db_manager.delete_column(self.table_name, fname)
            self._load_schema()
            self.schema_changed.emit(self.table_name)
            QMessageBox.information(self, "Field Deleted", f"Column '{fname}' has been removed.")
        except Exception as exc:
            logger.error(f"Failed to delete field: {exc}", exc_info=True)
            QMessageBox.critical(self, "Error Deleting Field", f"Failed to delete column:\n{exc}")
