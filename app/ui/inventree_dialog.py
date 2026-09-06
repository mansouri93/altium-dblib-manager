# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
    QWidget,
    QMessageBox,
)
from ..inventree.client import InvenTreeClient
from .icons import AppIcons

class InvenTreeSearchDialog(QDialog):
    """Dialog to search InvenTree catalog and select a part to link."""

    def __init__(self, client: InvenTreeClient, initial_query: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.selected_part_data: dict[str, Any] | None = None

        self.setWindowTitle("Search & Link InvenTree Part")
        self.resize(800, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Search Bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Enter IPN, part name, or keyword...")
        self.search_input.addAction(AppIcons.search(), QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setText(initial_query)
        self.search_input.returnPressed.connect(self._do_search)
        search_layout.addWidget(self.search_input)

        self.btn_search = QPushButton(" Search")
        self.btn_search.setIcon(AppIcons.search())
        self.btn_search.setObjectName("PrimaryButton")
        self.btn_search.clicked.connect(self._do_search)
        search_layout.addWidget(self.btn_search)

        layout.addLayout(search_layout)

        # Results Table
        self.results_table = QTableWidget(self)
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(["ID", "IPN", "Name", "Stock", "Location"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.results_table.itemDoubleClicked.connect(lambda: self._confirm_selection())
        layout.addWidget(self.results_table)

        self.lbl_status = QLabel("Ready to search")
        self.lbl_status.setStyleSheet("color: #8888aa; font-size: 11px;")
        layout.addWidget(self.lbl_status)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton(" Cancel")
        self.btn_cancel.setIcon(AppIcons.cancel())
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_link = QPushButton(" Link Part")
        self.btn_link.setIcon(AppIcons.link())
        self.btn_link.setObjectName("SuccessButton")
        self.btn_link.setEnabled(False)
        self.btn_link.clicked.connect(self._confirm_selection)
        btn_layout.addWidget(self.btn_link)

        layout.addLayout(btn_layout)

        self._current_results: list[dict[str, Any]] = []

        if initial_query:
            self._do_search()

    def _do_search(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            return

        self.lbl_status.setText("Searching InvenTree...")
        self.btn_search.setEnabled(False)
        try:
            results = self.client.search_parts(query, limit=50)
            self._current_results = results
            self.results_table.setRowCount(len(results))

            for row_idx, part in enumerate(results):
                pk = str(part.get("pk", ""))
                ipn = str(part.get("IPN", "") or "")
                name = str(part.get("name", "") or "")
                stock = str(part.get("total_in_stock", 0.0))
                def_loc_id = part.get("default_location")
                loc_str = self.client.get_location_string(def_loc_id) if def_loc_id else ""

                self.results_table.setItem(row_idx, 0, QTableWidgetItem(pk))
                self.results_table.setItem(row_idx, 1, QTableWidgetItem(ipn))
                self.results_table.setItem(row_idx, 2, QTableWidgetItem(name))
                self.results_table.setItem(row_idx, 3, QTableWidgetItem(stock))
                self.results_table.setItem(row_idx, 4, QTableWidgetItem(loc_str))

            self.lbl_status.setText(f"Found {len(results)} parts matching '{query}'")
        except Exception as exc:
            self.lbl_status.setText(f"Search error: {exc}")
        finally:
            self.btn_search.setEnabled(True)

    def _on_selection_changed(self) -> None:
        selected_rows = self.results_table.selectionModel().selectedRows()
        self.btn_link.setEnabled(len(selected_rows) > 0)

    def _confirm_selection(self) -> None:
        selected_rows = self.results_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row_idx = selected_rows[0].row()
        if 0 <= row_idx < len(self._current_results):
            part = self._current_results[row_idx]
            pk = int(part["pk"])
            stock, loc = self.client.get_stock_and_location(pk)
            ipn_val = str(part.get("IPN") or "").strip()
            name_val = str(part.get("name") or "").strip()
            self.selected_part_data = {
                "pk": pk,
                "ipn": ipn_val or name_val,
                "IPN": ipn_val,
                "name": name_val,
                "stock": str(stock),
                "location": loc,
            }
            self.accept()

    def get_selected_part(self) -> dict[str, Any] | None:
        return self.selected_part_data
