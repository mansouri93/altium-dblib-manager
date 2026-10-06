# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
import re
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
    QGroupBox,
)
from ..db.access_manager import AccessDBManager, SYMBOL_FOOTPRINT_COLUMNS
from ..db.dblib_sync import DbLibSync
from .icons import AppIcons
from .smooth_scroll import enable_smooth_scroll
from .table_schema_dialog import FieldEditDialog

logger = logging.getLogger(__name__)


class TableCreateDialog(QDialog):
    """
    Dialog to create a new category table in Access database and sync to .DbLib.
    Features:
    - Template presets (Passives with Calculated Part Number, ICs / Standard, Custom).
    - Mandatory ID (AutoNumber) and Part Number (Short Text or Calculated).
    - Add, edit, remove fields prior to creation.
    - Path fields auto-configured as Long Text.
    """

    table_created = Signal(str)  # table_name

    def __init__(self, db_manager: AccessDBManager, parent=None) -> None:
        super().__init__(parent)
        self.db_manager = db_manager
        self.dblib_sync = DbLibSync()
        self.existing_tables = [t.lower() for t in self.db_manager.list_tables()]

        self.setWindowTitle("Create New Category Table")
        self.resize(760, 540)

        self.fields: list[dict[str, Any]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Table Name
        top_group = QGroupBox("Table Configuration", self)
        top_layout = QVBoxLayout(top_group)
        top_layout.setSpacing(10)

        # Name row
        row_name = QHBoxLayout()
        row_name.addWidget(QLabel("Table / Category Name:"))
        self.txt_table_name = QLineEdit(self)
        self.txt_table_name.setPlaceholderText("e.g. Inductors, Connectors, Diodes...")
        row_name.addWidget(self.txt_table_name, stretch=1)
        top_layout.addLayout(row_name)

        layout.addWidget(top_group)

        # Fields Table
        fields_group = QGroupBox("Fields & Schema Definition", self)
        fields_layout = QVBoxLayout(fields_group)
        fields_layout.setSpacing(8)

        self.tbl_fields = QTableWidget(self)
        self.tbl_fields.setColumnCount(4)
        self.tbl_fields.setHorizontalHeaderLabels(["Field Name", "Data Type", "Formula / Expression", "Status / Role"])
        self.tbl_fields.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tbl_fields.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.tbl_fields.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_fields.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.tbl_fields.setColumnWidth(0, 180)
        self.tbl_fields.setColumnWidth(1, 140)
        self.tbl_fields.setColumnWidth(3, 140)
        self.tbl_fields.verticalHeader().setVisible(False)
        self.tbl_fields.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_fields.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        enable_smooth_scroll(self.tbl_fields, step_v=30, step_h=50)
        fields_layout.addWidget(self.tbl_fields, stretch=1)

        # Buttons below table
        btn_table_row = QHBoxLayout()
        btn_table_row.setSpacing(8)

        self.btn_add_fld = QPushButton(" + Add Field")
        self.btn_add_fld.setIcon(AppIcons.add())
        self.btn_add_fld.clicked.connect(self._on_add_field)
        btn_table_row.addWidget(self.btn_add_fld)

        self.btn_edit_fld = QPushButton(" Edit Field...")
        self.btn_edit_fld.setIcon(AppIcons.edit())
        self.btn_edit_fld.clicked.connect(self._on_edit_field)
        btn_table_row.addWidget(self.btn_edit_fld)

        self.btn_del_fld = QPushButton(" Delete Field")
        self.btn_del_fld.setIcon(AppIcons.delete())
        self.btn_del_fld.clicked.connect(self._on_delete_field)
        btn_table_row.addWidget(self.btn_del_fld)

        self.btn_reset_fld = QPushButton(" Reset Defaults")
        self.btn_reset_fld.setIcon(AppIcons.refresh())
        self.btn_reset_fld.clicked.connect(self._load_default_fields)
        btn_table_row.addWidget(self.btn_reset_fld)

        btn_table_row.addStretch()
        fields_layout.addLayout(btn_table_row)

        layout.addWidget(fields_group, stretch=1)

        # Dialog Action Buttons
        dlg_btn_row = QHBoxLayout()
        dlg_btn_row.setSpacing(10)
        dlg_btn_row.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        dlg_btn_row.addWidget(btn_cancel)

        self.btn_create = QPushButton("Create Table")
        self.btn_create.setObjectName("PrimaryButton")
        self.btn_create.clicked.connect(self._on_create_table)
        dlg_btn_row.addWidget(self.btn_create)

        layout.addLayout(dlg_btn_row)

        self.tbl_fields.selectionModel().selectionChanged.connect(self._update_btn_states)
        self.tbl_fields.doubleClicked.connect(self._on_edit_field)

        # Load default fields
        self._load_default_fields()

    def _load_default_fields(self) -> None:
        """Load the default fields: ID (AutoNumber), Part Number, Location, Stock, IPN (all Short Text)."""
        self.fields = [
            {"name": "ID", "type": "autonumber", "expression": "", "is_pk": True, "is_mandatory": True},
            {"name": "Part Number", "type": "short_text", "expression": "", "is_pk": False, "is_mandatory": True},
            {"name": "Location", "type": "short_text", "expression": "", "is_pk": False, "is_mandatory": False},
            {"name": "Stock", "type": "short_text", "expression": "", "is_pk": False, "is_mandatory": False},
            {"name": "IPN", "type": "short_text", "expression": "", "is_pk": False, "is_mandatory": False},
        ]
        self._render_table()

    def _render_table(self) -> None:
        self.tbl_fields.setRowCount(len(self.fields))
        for row, f in enumerate(self.fields):
            fname = f["name"]
            ftype = f["type"]
            expr = f.get("expression", "")
            is_pk = f.get("is_pk", False)
            is_mand = f.get("is_mandatory", False)

            it_name = QTableWidgetItem(fname)
            if is_pk or is_mand:
                it_name.setForeground(Qt.GlobalColor.white)
            self.tbl_fields.setItem(row, 0, it_name)

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

            it_expr = QTableWidgetItem(expr or "—")
            if expr:
                it_expr.setForeground(Qt.GlobalColor.yellow)
            self.tbl_fields.setItem(row, 2, it_expr)

            status_str = "Optional"
            if is_pk:
                status_str = "Primary Key (Auto)"
            elif fname.upper() == "PART NUMBER":
                status_str = "Mandatory (Core)"
            elif "Path" in fname:
                status_str = "File Path (System)"
            it_status = QTableWidgetItem(status_str)
            if is_pk or is_mand:
                it_status.setForeground(Qt.GlobalColor.green)
            self.tbl_fields.setItem(row, 3, it_status)

        self._update_btn_states()

    def _on_template_changed(self) -> None:
        tmpl_key = self.cb_template.currentData()
        self._load_template(tmpl_key)

    def _get_selected_index(self) -> int:
        rows = self.tbl_fields.selectionModel().selectedRows()
        if not rows:
            return -1
        return rows[0].row()

    def _update_btn_states(self) -> None:
        idx = self._get_selected_index()
        if idx < 0 or idx >= len(self.fields):
            self.btn_edit_fld.setEnabled(False)
            self.btn_del_fld.setEnabled(False)
            return

        f = self.fields[idx]
        fname = f["name"].upper()
        if fname == "ID":
            self.btn_edit_fld.setEnabled(False)
            self.btn_del_fld.setEnabled(False)
        elif fname == "PART NUMBER":
            self.btn_edit_fld.setEnabled(True)    # can switch between Short Text and Calculated
            self.btn_del_fld.setEnabled(False)   # mandatory
        else:
            self.btn_edit_fld.setEnabled(True)
            self.btn_del_fld.setEnabled(True)

    def _on_add_field(self) -> None:
        existing = [f["name"] for f in self.fields]
        dlg = FieldEditDialog(existing_names=existing, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.fields.append({
                "name": data["name"],
                "type": data["type"],
                "expression": data["expression"],
                "is_pk": False,
                "is_mandatory": False,
            })
            self._render_table()

    def _on_edit_field(self) -> None:
        idx = self._get_selected_index()
        if idx < 0 or idx >= len(self.fields):
            return
        f = self.fields[idx]
        fname = f["name"]
        if fname.upper() == "ID":
            return

        is_pn = fname.upper() == "PART NUMBER"
        other_names = [x["name"] for x in self.fields if x["name"] != fname]
        dlg = FieldEditDialog(existing_names=other_names, field_data=f, is_part_number=is_pn, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            f["name"] = data["name"]
            f["type"] = data["type"]
            f["expression"] = data["expression"]
            self._render_table()

    def _on_delete_field(self) -> None:
        idx = self._get_selected_index()
        if idx < 0 or idx >= len(self.fields):
            return
        f = self.fields[idx]
        fname = f["name"]
        if fname.upper() in ("ID", "PART NUMBER"):
            QMessageBox.warning(self, "Protected Field", f"Field '{fname}' is mandatory and cannot be deleted.")
            return

        self.fields.pop(idx)
        self._render_table()

    def _on_create_table(self) -> None:
        tname = self.txt_table_name.text().strip()
        if not tname:
            QMessageBox.warning(self, "Invalid Name", "Please enter a table name.")
            self.txt_table_name.setFocus()
            return

        # Validate table name according to MS Access standard
        is_valid, err_msg = self.db_manager.validate_table_name(tname)
        if not is_valid:
            QMessageBox.warning(self, "Invalid Table Name", err_msg)
            self.txt_table_name.setFocus()
            return

        if tname.lower() in self.existing_tables:
            QMessageBox.warning(self, "Duplicate Table", f"A table named '{tname}' already exists in the database.")
            return

        # Verify Part Number is present
        has_pn = any(f["name"].upper() == "PART NUMBER" for f in self.fields)
        if not has_pn:
            QMessageBox.warning(self, "Mandatory Field Missing", "The 'Part Number' field is mandatory and must be included.")
            return

        try:
            # 1. Create table in MS Access database
            self.db_manager.create_category_table(tname, self.fields)

            # 2. Sync into Altium .DbLib
            col_names = self.db_manager.get_columns(tname)
            self.dblib_sync.sync_table_to_dblib(tname, col_names)

            self.table_created.emit(tname)
            QMessageBox.information(self, "Table Created", f"Category table '{tname}' has been created and synced with Altium .DbLib successfully!")
            self.accept()
        except Exception as exc:
            logger.error(f"Failed to create table '{tname}': {exc}", exc_info=True)
            QMessageBox.critical(self, "Error Creating Table", f"Failed to create table:\n{exc}")
