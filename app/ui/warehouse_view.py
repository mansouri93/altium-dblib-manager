# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
import re
from typing import Any
from PySide6.QtCore import (
    Qt,
    QAbstractTableModel,
    QModelIndex,
    Signal,
    QSize,
)
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableView,
    QHeaderView,
    QPushButton,
    QLineEdit,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QComboBox,
    QFrame,
    QGroupBox,
    QMessageBox,
    QDialog,
    QMenu,
)
from ..inventree.client import InvenTreeClient, ComponentLinkManager
from .icons import AppIcons
from .smooth_scroll import enable_smooth_scroll

logger = logging.getLogger(__name__)


class CategoryFilterDialog(QDialog):
    """
    Modern popup dialog for selecting InvenTree categories with real-time search,
    hierarchical display, selection counters, and bulk selection controls.
    """

    def __init__(
        self,
        all_categories: list[dict[str, Any]],
        initial_selected_ids: set[int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.all_categories = all_categories
        self.selected_category_ids = set(initial_selected_ids)
        self._init_ui()

    def _init_ui(self) -> None:
        self.setWindowTitle("Filter Warehouse Categories")
        self.setMinimumSize(480, 520)
        self.resize(520, 580)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header Title & Description
        header_layout = QVBoxLayout()
        header_layout.setSpacing(3)
        lbl_title = QLabel("Select Warehouse Categories")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff;")
        lbl_desc = QLabel("Check the InvenTree categories to compare with Altium components.")
        lbl_desc.setStyleSheet("font-size: 12px; color: #8f8fa8;")
        header_layout.addWidget(lbl_title)
        header_layout.addWidget(lbl_desc)
        layout.addLayout(header_layout)

        # Search Bar
        self.search_input = QLineEdit(self)
        self.search_input.setFixedHeight(32)
        self.search_input.setPlaceholderText("Search categories... (e.g. Resistors, Capacitors)")
        self.search_input.addAction(AppIcons.search(), QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter_tree)
        layout.addWidget(self.search_input)

        # Action Toolbar (Select All / Clear / Expand / Collapse)
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(6)

        btn_select_all = QPushButton("Select All")
        btn_select_all.setFixedHeight(26)
        btn_select_all.clicked.connect(self._select_all)
        toolbar_layout.addWidget(btn_select_all)

        btn_clear = QPushButton("Clear")
        btn_clear.setFixedHeight(26)
        btn_clear.clicked.connect(self._clear_all)
        toolbar_layout.addWidget(btn_clear)

        toolbar_layout.addStretch()

        self.btn_expand = QPushButton("Expand All")
        self.btn_expand.setFixedHeight(26)
        toolbar_layout.addWidget(self.btn_expand)

        self.btn_collapse = QPushButton("Collapse All")
        self.btn_collapse.setFixedHeight(26)
        toolbar_layout.addWidget(self.btn_collapse)

        layout.addLayout(toolbar_layout)

        # Tree Widget
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Category Name", "Parts Count"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tree.header().resizeSection(1, 85)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree, stretch=1)

        self.btn_expand.clicked.connect(self.tree.expandAll)
        self.btn_collapse.clicked.connect(self.tree.collapseAll)

        # Footer Status & Dialog Buttons
        footer_layout = QHBoxLayout()
        self.lbl_summary = QLabel()
        self.lbl_summary.setStyleSheet("font-size: 12px; color: #a0a0be; font-weight: 500;")
        footer_layout.addWidget(self.lbl_summary)

        footer_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(30)
        btn_cancel.clicked.connect(self.reject)
        footer_layout.addWidget(btn_cancel)

        btn_apply = QPushButton(" Apply Filter")
        btn_apply.setObjectName("PrimaryButton")
        btn_apply.setFixedHeight(30)
        btn_apply.clicked.connect(self.accept)
        footer_layout.addWidget(btn_apply)

        layout.addLayout(footer_layout)

        self._populate_tree()
        self._update_summary()

    def _populate_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()

        by_parent: dict[int | None, list[dict[str, Any]]] = {}
        for c in self.all_categories:
            pid = c.get("parent")
            by_parent.setdefault(pid, []).append(c)

        def build_node(parent_item: QTreeWidgetItem | None, parent_id: int | None) -> bool:
            children = by_parent.get(parent_id, [])
            has_any_checked = False
            for child in sorted(children, key=lambda x: x.get("name", "")):
                pk = child.get("pk")
                name = child.get("name", "")
                count = child.get("part_count", 0)

                item = QTreeWidgetItem([name, str(count)])
                item.setData(0, Qt.ItemDataRole.UserRole, pk)
                item.setTextAlignment(1, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

                is_checked = pk in self.selected_category_ids
                if is_checked:
                    has_any_checked = True
                item.setCheckState(0, Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)

                if parent_item:
                    parent_item.addChild(item)
                else:
                    self.tree.addTopLevelItem(item)

                child_checked = build_node(item, pk)
                if child_checked:
                    has_any_checked = True
                    item.setExpanded(True)

            return has_any_checked

        build_node(None, None)
        self.tree.blockSignals(False)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        pk = item.data(0, Qt.ItemDataRole.UserRole)
        if pk is not None:
            if item.checkState(0) == Qt.CheckState.Checked:
                self.selected_category_ids.add(pk)
            else:
                self.selected_category_ids.discard(pk)
        self._update_summary()

    def _select_all(self) -> None:
        self.tree.blockSignals(True)
        def check_item(item: QTreeWidgetItem):
            pk = item.data(0, Qt.ItemDataRole.UserRole)
            if pk:
                self.selected_category_ids.add(pk)
            item.setCheckState(0, Qt.CheckState.Checked)
            for i in range(item.childCount()):
                check_item(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            check_item(self.tree.topLevelItem(i))
        self.tree.blockSignals(False)
        self._update_summary()

    def _clear_all(self) -> None:
        self.selected_category_ids.clear()
        self.tree.blockSignals(True)
        def uncheck_item(item: QTreeWidgetItem):
            item.setCheckState(0, Qt.CheckState.Unchecked)
            for i in range(item.childCount()):
                uncheck_item(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            uncheck_item(self.tree.topLevelItem(i))
        self.tree.blockSignals(False)
        self._update_summary()

    def _filter_tree(self, text: str) -> None:
        txt = text.strip().lower()
        def filter_item(item: QTreeWidgetItem) -> bool:
            name = item.text(0).lower()
            match = txt in name
            any_child_match = False
            for i in range(item.childCount()):
                if filter_item(item.child(i)):
                    any_child_match = True
            visible = match or any_child_match or not txt
            item.setHidden(not visible)
            if visible and txt:
                item.setExpanded(True)
            return visible

        for i in range(self.tree.topLevelItemCount()):
            filter_item(self.tree.topLevelItem(i))

    def _update_summary(self) -> None:
        count = len(self.selected_category_ids)
        self.lbl_summary.setText(f"Selected: <b>{count}</b> categories")

    def get_selected_ids(self) -> set[int]:
        return set(self.selected_category_ids)


class WarehouseTableModel(QAbstractTableModel):
    """
    Model presenting warehouse parts aligned with Altium DbLib rows,
    followed by unlinked warehouse parts at the bottom.
    """

    COLUMNS = ["Status", "InvenTree IPN", "Warehouse Name", "Stock", "Location", "Action"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.rows: list[dict[str, Any]] = []

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.rows) and self.rows[section].get("is_separator"):
                return ""
            return str(section + 1)
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if 0 <= index.row() < len(self.rows) and self.rows[index.row()].get("is_separator"):
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self.rows):
            return None

        row = self.rows[index.row()]
        col = index.column()
        is_header_row = row.get("is_separator", False)

        if role == Qt.ItemDataRole.DisplayRole:
            if is_header_row:
                if col == 0:
                    return row.get("title", "")
                return ""

            if col == 0:
                st = row.get("status")
                if st == "LINKED":
                    return "🟢 Linked"
                elif st == "UNLINKED_WAREHOUSE":
                    return "🟠 Unlinked"
                elif st == "UNMATCHED_ALTIUM":
                    return "⚪ Altium Only"
                return ""
            elif col == 1:
                return row.get("ipn") or "—"
            elif col == 2:
                return row.get("name") or "—"
            elif col == 3:
                val = row.get("stock")
                if val is None or val == "":
                    return "—"
                try:
                    num = float(val)
                    return str(int(num)) if num.is_integer() else str(num)
                except (ValueError, TypeError):
                    return str(val)
            elif col == 4:
                return row.get("location") or "—"
            elif col == 5:
                return ""

        elif role == Qt.ItemDataRole.ForegroundRole:
            if is_header_row:
                return QBrush(QColor("#00e5ff"))

            if col == 0:
                st = row.get("status")
                if st == "LINKED":
                    return QBrush(QColor("#40ff80"))
                elif st == "UNLINKED_WAREHOUSE":
                    return QBrush(QColor("#ffaa40"))
                elif st == "UNMATCHED_ALTIUM":
                    return QBrush(QColor("#888899"))
            elif col == 3:
                val = row.get("stock")
                if val is not None and val != "":
                    try:
                        num = float(val)
                        return QBrush(QColor("#40ff80") if num > 0 else QColor("#ff6666"))
                    except (ValueError, TypeError):
                        pass

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if is_header_row:
                return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if col in (0, 3):
                return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        elif role == Qt.ItemDataRole.FontRole:
            if is_header_row or col == 0:
                font = QFont()
                font.setBold(True)
                return font

        elif role == Qt.ItemDataRole.BackgroundRole:
            if is_header_row:
                return QBrush(QColor("#1e2330"))
            elif row.get("status") == "UNMATCHED_ALTIUM":
                return QBrush(QColor("#16161f"))

        return None


class WarehouseLinkWidget(QWidget):
    """
    Split view panel displaying InvenTree warehouse stock aligned
    with Altium DbLib components, with category filtering and
    one-click component creation in Altium.
    """

    create_component_requested = Signal(dict)
    edit_link_requested = Signal(dict, object)
    unlink_component_requested = Signal(dict)
    link_warehouse_to_altium_requested = Signal(dict)
    part_inspected = Signal(dict)
    altium_row_focus_requested = Signal(int)
    rows_rebuilt = Signal(int)

    def __init__(
        self,
        inventree_client: InvenTreeClient,
        link_manager: ComponentLinkManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.it_client = inventree_client
        self.link_manager = link_manager or ComponentLinkManager()

        self.altium_records: list[dict[str, Any]] = []
        self.current_altium_table: str = ""
        self.all_categories: list[dict[str, Any]] = []
        self.selected_category_ids: set[int] = set()
        self.cached_warehouse_parts: list[dict[str, Any]] = []

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # ----------------- Top Control Bar -----------------
        top_bar_container = QWidget()
        top_bar_container.setFixedHeight(32)
        top_bar = QHBoxLayout(top_bar_container)
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(6)

        # Category Filter Dialog Button (Popup)
        self.btn_categories = QPushButton(" Categories (0)")
        self.btn_categories.setFixedHeight(28)
        self.btn_categories.setIcon(AppIcons.table())
        self.btn_categories.setToolTip("Open Categories Filter Dialog (Popup)")
        self.btn_categories.clicked.connect(self._open_category_filter_dialog)
        top_bar.addWidget(self.btn_categories)

        # Filter Warehouse Parts Search Box
        self.search_input = QLineEdit(self)
        self.search_input.setFixedHeight(28)
        self.search_input.setPlaceholderText("Filter unlinked warehouse parts...")
        self.search_input.addAction(AppIcons.search(), QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._build_table_rows)
        top_bar.addWidget(self.search_input)

        # Refresh Button
        self.btn_refresh = QPushButton()
        self.btn_refresh.setFixedSize(28, 28)
        self.btn_refresh.setIcon(AppIcons.refresh())
        self.btn_refresh.setToolTip("Reload Warehouse Inventory")
        self.btn_refresh.clicked.connect(self.reload_warehouse_inventory)
        top_bar.addWidget(self.btn_refresh)

        # Status Summary Badge in Top Bar
        self.lbl_stats = QLabel(self)
        self.lbl_stats.setFixedHeight(28)
        self.lbl_stats.setStyleSheet("font-size: 11.5px; font-weight: bold; padding: 0 4px;")
        top_bar.addWidget(self.lbl_stats)

        main_layout.addWidget(top_bar_container)

        # ----------------- Aligned Dual Table View -----------------
        self.table_model = WarehouseTableModel(self)
        self.table_view = QTableView(self)
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setShowGrid(True)
        enable_smooth_scroll(self.table_view, step_v=45, step_h=60)

        # Fixed row height for pixel-perfect horizontal alignment with Altium table
        self.table_view.verticalHeader().setDefaultSectionSize(30)
        self.table_view.verticalHeader().setMinimumSectionSize(30)
        self.table_view.verticalHeader().setMaximumSectionSize(30)
        self.table_view.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table_view.verticalHeader().setFixedWidth(38)

        # Fixed horizontal header height
        h_header = self.table_view.horizontalHeader()
        h_header.setFixedHeight(30)
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)

        self.table_view.setColumnWidth(0, 125)  # Status ("🟢 Linked", "⚪ Altium Only")
        self.table_view.setColumnWidth(1, 130)  # InvenTree IPN
        self.table_view.setColumnWidth(3, 60)   # Stock
        self.table_view.setColumnWidth(4, 110)  # Location
        self.table_view.setColumnWidth(5, 154)  # Action (+10% width: 140 -> 154)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)

        self.table_view.selectionModel().selectionChanged.connect(self._on_row_selected)
        main_layout.addWidget(self.table_view)

    # ----------------- Popup Category Filter Dialog -----------------
    def _open_category_filter_dialog(self) -> None:
        if not self.all_categories:
            self.all_categories = self.it_client.get_all_categories()

        dialog = CategoryFilterDialog(self.all_categories, self.selected_category_ids, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.selected_category_ids = dialog.get_selected_ids()
            self._update_category_button_label()
            self.reload_warehouse_inventory()

    def _update_category_button_label(self) -> None:
        count = len(self.selected_category_ids)
        self.btn_categories.setText(f" Categories ({count})")

    def _auto_select_matching_category(self, table_name: str) -> None:
        t_clean = table_name.lower().rstrip("s")
        matched_ids = set()

        for c in self.all_categories:
            c_name = str(c.get("name") or "").lower().rstrip("s")
            c_path = str(c.get("pathstring") or "").lower()
            if t_clean == c_name or f"/{t_clean}" in c_path:
                matched_ids.add(c.get("pk"))

        if matched_ids:
            self.selected_category_ids = matched_ids
            self._update_category_button_label()
            self.reload_warehouse_inventory()

    # ----------------- Inventory Data Fetching & Alignment -----------------
    def set_altium_context(self, table_name: str, records: list[dict[str, Any]]) -> None:
        table_changed = self.current_altium_table != table_name
        self.current_altium_table = table_name
        self.altium_records = records

        if table_changed:
            if not self.all_categories:
                self.all_categories = self.it_client.get_all_categories()
            self._auto_select_matching_category(table_name)
        else:
            self._build_table_rows()

    def reload_warehouse_inventory(self) -> None:
        if not self.selected_category_ids:
            self.cached_warehouse_parts = []
            self._build_table_rows()
            self.lbl_stats.setText("No categories")
            return

        cat_list = list(self.selected_category_ids)
        logger.info(f"Reloading warehouse parts for categories: {cat_list}")
        self.lbl_stats.setText("Querying InvenTree...")

        try:
            self.cached_warehouse_parts = self.it_client.get_parts_by_categories(cat_list)
            logger.info(f"Loaded {len(self.cached_warehouse_parts)} parts from InvenTree.")
            self._build_table_rows()
        except Exception as exc:
            logger.error(f"Failed to fetch parts from InvenTree: {exc}", exc_info=True)
            self.lbl_stats.setText("Error fetching parts")

    def _normalize_pn(self, val: Any) -> str:
        if not val:
            return ""
        s = str(val).strip()
        s = s.replace("Ω", "").replace("ω", "").replace("Ω", "").replace("ohm", "").replace("OHM", "").replace(" ", "")
        s = s.lower()
        # Shorthand notation replacements:
        # e.g. 1r5k -> 1.5k, 15r4k -> 15.4k
        s = re.sub(r"(\d+)r(\d+)([km])", r"\1.\2\3", s)
        # e.g. 1k5 -> 1.5k, 4k7 -> 4.7k
        s = re.sub(r"(\d+)([km])(\d+)", r"\1.\3\2", s)
        # e.g. 0r1 -> 0.1, 1r5 -> 1.5
        s = re.sub(r"(\d+)r(\d+)", r"\1.\2", s)
        # e.g. 100r -> 100
        s = re.sub(r"(\d+)r(?=$|[-_])", r"\1", s)
        return s

    def _build_table_rows(self) -> None:
        filter_text = self.search_input.text().strip().lower()

        it_by_pk: dict[int, dict[str, Any]] = {
            int(p["pk"]): p for p in self.cached_warehouse_parts if p.get("pk")
        }
        it_by_ipn: dict[str, dict[str, Any]] = {}
        for p in self.cached_warehouse_parts:
            ipn = p.get("IPN")
            if ipn:
                it_by_ipn[str(ipn).strip().lower()] = p

        matched_it_pks: set[int] = set()
        aligned_rows: list[dict[str, Any]] = []

        # Section 1: Aligned Altium Rows (Strict 1-to-1 index matching with Altium view)
        linked_count = 0
        unmatched_altium_count = 0

        for altium_idx, rec in enumerate(self.altium_records):
            row_id = rec.get("ID")
            override = self.link_manager.get_link(self.current_altium_table, row_id) if row_id else None

            matched_it = None
            if override:
                if override.get("unlinked"):
                    matched_it = None
                elif override.get("inventree_pk"):
                    target_pk = override["inventree_pk"]
                    matched_it = it_by_pk.get(target_pk)
                    if not matched_it and target_pk:
                        matched_it = self.it_client.get_part_by_pk(target_pk)
            else:
                # Strictly match by explicit warehouse IPN field if present; NEVER guess by Part Number
                db_ipn = str(rec.get("IPN") or "").strip().lower()
                if db_ipn and db_ipn in it_by_ipn:
                    matched_it = it_by_ipn[db_ipn]
                    if row_id:
                        self.link_manager.set_link(self.current_altium_table, row_id, matched_it)

            if matched_it:
                matched_it_pks.add(matched_it["pk"])
                linked_count += 1
                row_data = {
                    "status": "LINKED",
                    "altium_index": altium_idx,
                    "altium_record": rec,
                    "inventree_part": matched_it,
                    "ipn": matched_it.get("IPN"),
                    "name": matched_it.get("name"),
                    "stock": matched_it.get("total_in_stock"),
                    "location": matched_it.get("location_name"),
                    "can_add": False,
                }
            else:
                unmatched_altium_count += 1
                row_data = {
                    "status": "UNMATCHED_ALTIUM",
                    "altium_index": altium_idx,
                    "altium_record": rec,
                    "inventree_part": None,
                    "ipn": "—",
                    "name": "(No warehouse match)",
                    "stock": "",
                    "location": "",
                    "can_add": False,
                }

            aligned_rows.append(row_data)

        # Section 2: Unlinked Warehouse Parts
        unlinked_it_parts = [p for p in self.cached_warehouse_parts if p["pk"] not in matched_it_pks]
        unlinked_count = len(unlinked_it_parts)
        sep_row_idx = None

        if unlinked_it_parts:
            sep_row_idx = len(aligned_rows)
            sep_row = {
                "is_separator": True,
                "title": f"═══ Unlinked Warehouse Parts ({unlinked_count} parts not in Altium '{self.current_altium_table}') ═══",
                "status": "",
                "ipn": "",
                "name": "",
                "stock": "",
                "location": "",
                "can_add": False,
            }
            aligned_rows.append(sep_row)

            for it_p in sorted(unlinked_it_parts, key=lambda x: str(x.get("IPN") or x.get("name") or "")):
                # Filter unlinked parts if filter text is typed
                ipn_s = str(it_p.get("IPN") or "")
                name_s = str(it_p.get("name") or "")
                loc_s = str(it_p.get("location_name") or "")
                if filter_text and filter_text not in f"{ipn_s} {name_s} {loc_s}".lower():
                    continue

                row_data = {
                    "status": "UNLINKED_WAREHOUSE",
                    "altium_index": None,
                    "altium_record": None,
                    "inventree_part": it_p,
                    "ipn": it_p.get("IPN") or "—",
                    "name": it_p.get("name") or "—",
                    "stock": it_p.get("total_in_stock"),
                    "location": it_p.get("location_name") or "",
                    "can_add": True,
                }
                aligned_rows.append(row_data)

        self.table_view.clearSpans()
        self.table_model.set_rows(aligned_rows)

        if sep_row_idx is not None and sep_row_idx < len(aligned_rows):
            self.table_view.setSpan(sep_row_idx, 0, 1, len(WarehouseTableModel.COLUMNS))

        self._attach_action_buttons()
        self.rows_rebuilt.emit(len(aligned_rows))

        total_wh = len(self.cached_warehouse_parts)
        self.lbl_stats.setText(
            f"<span style='color: #40ff80;'>🟢 {linked_count}</span> | "
            f"<span style='color: #ffaa40;'>🟠 {unlinked_count}</span>"
        )
        self.lbl_stats.setToolTip(
            f"Warehouse Total: {total_wh} parts\n"
            f"Linked to Altium: {linked_count}\n"
            f"Unlinked in Warehouse: {unlinked_count}\n"
            f"Altium Unmatched: {unmatched_altium_count}"
        )

    def _attach_action_buttons(self) -> None:
        for row_idx, r in enumerate(self.table_model.rows):
            status = r.get("status")
            col_idx = 5
            index = self.table_model.index(row_idx, col_idx)

            if status == "LINKED":
                container = QWidget()
                h_layout = QHBoxLayout(container)
                h_layout.setContentsMargins(2, 2, 2, 2)
                h_layout.setSpacing(4)
                h_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                btn_edit = QPushButton(" Edit")
                btn_edit.setIcon(AppIcons.edit("#58a6ff"))
                btn_edit.setIconSize(QSize(12, 12))
                btn_edit.setFixedSize(58, 24)
                btn_edit.setToolTip("Edit Link (Select a different warehouse part)")
                btn_edit.setStyleSheet("""
                    QPushButton {
                        background-color: #242938;
                        border: 1px solid #384260;
                        border-radius: 4px;
                        color: #d0d8f0;
                        font-size: 11px;
                        font-weight: 500;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background-color: #2e364c;
                        border-color: #58a6ff;
                        color: #ffffff;
                    }
                """)
                alt_rec = r.get("altium_record")
                it_part = r.get("inventree_part")
                btn_edit.clicked.connect(lambda ch=False, a=alt_rec, it=it_part: self.edit_link_requested.emit(a, it))
                h_layout.addWidget(btn_edit)

                btn_unlink = QPushButton(" Unlink")
                btn_unlink.setIcon(AppIcons.cancel("#ff7b72"))
                btn_unlink.setIconSize(QSize(11, 11))
                btn_unlink.setFixedSize(66, 24)
                btn_unlink.setToolTip("Remove Link (Unlink from warehouse)")
                btn_unlink.setStyleSheet("""
                    QPushButton {
                        background-color: #381e24;
                        border: 1px solid #632a32;
                        border-radius: 4px;
                        color: #f0c0c0;
                        font-size: 11px;
                        font-weight: 500;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background-color: #4a232b;
                        border-color: #ff7b72;
                        color: #ffffff;
                    }
                """)
                btn_unlink.clicked.connect(lambda ch=False, a=alt_rec: self.unlink_component_requested.emit(a))
                h_layout.addWidget(btn_unlink)

                self.table_view.setIndexWidget(index, container)

            elif status == "UNMATCHED_ALTIUM":
                container = QWidget()
                h_layout = QHBoxLayout(container)
                h_layout.setContentsMargins(2, 2, 2, 2)
                h_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                btn_link = QPushButton(" Link")
                btn_link.setIcon(AppIcons.link("#58a6ff"))
                btn_link.setIconSize(QSize(12, 12))
                btn_link.setFixedSize(72, 24)
                btn_link.setToolTip("Link this Altium component to an InvenTree warehouse part")
                btn_link.setStyleSheet("""
                    QPushButton {
                        background-color: #1a2736;
                        border: 1px solid #294466;
                        border-radius: 4px;
                        color: #79c0ff;
                        font-size: 11px;
                        font-weight: bold;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background-color: #22374e;
                        border-color: #58a6ff;
                        color: #ffffff;
                    }
                """)
                alt_rec = r.get("altium_record")
                btn_link.clicked.connect(lambda ch=False, a=alt_rec: self.edit_link_requested.emit(a, None))
                h_layout.addWidget(btn_link)

                self.table_view.setIndexWidget(index, container)

            elif status == "UNLINKED_WAREHOUSE":
                container = QWidget()
                h_layout = QHBoxLayout(container)
                h_layout.setContentsMargins(2, 2, 2, 2)
                h_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                btn = QPushButton(" Add")
                btn.setIcon(AppIcons.add("#ffffff"))
                btn.setIconSize(QSize(11, 11))
                btn.setFixedSize(72, 24)
                btn.setToolTip("Add this part to Altium and link with warehouse")
                btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1f6feb, stop:1 #1158c7);
                        border: 1px solid #388bfd;
                        border-radius: 4px;
                        color: #ffffff;
                        font-size: 11px;
                        font-weight: bold;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #388bfd, stop:1 #1f6feb);
                        border-color: #58a6ff;
                    }
                """)
                part_data = r.get("inventree_part")
                btn.clicked.connect(lambda ch=False, p=part_data: self._on_add_part_clicked(p))
                h_layout.addWidget(btn)

                self.table_view.setIndexWidget(index, container)
            else:
                self.table_view.setIndexWidget(index, None)

    def _show_context_menu(self, pos) -> None:
        idx = self.table_view.indexAt(pos)
        if not idx.isValid() or idx.row() >= len(self.table_model.rows):
            return
        row_data = self.table_model.rows[idx.row()]
        status = row_data.get("status")
        alt_rec = row_data.get("altium_record")
        it_part = row_data.get("inventree_part")

        menu = QMenu(self)
        if status == "LINKED":
            pn = alt_rec.get("Part Number") or "Component" if alt_rec else "Component"
            act_edit = menu.addAction(AppIcons.link(), f"Edit Link for '{pn}'...")
            act_edit.triggered.connect(lambda: self.edit_link_requested.emit(alt_rec, it_part))

            act_unlink = menu.addAction(AppIcons.delete(), f"Remove Link for '{pn}' (Unlink)")
            act_unlink.triggered.connect(lambda: self.unlink_component_requested.emit(alt_rec))

        elif status == "UNMATCHED_ALTIUM":
            pn = alt_rec.get("Part Number") or "Component" if alt_rec else "Component"
            act_link = menu.addAction(AppIcons.link(), f"Link '{pn}' with Warehouse Part...")
            act_link.triggered.connect(lambda: self.edit_link_requested.emit(alt_rec, None))

        elif status == "UNLINKED_WAREHOUSE":
            ipn = it_part.get("IPN") or "Part" if it_part else "Part"
            act_add = menu.addAction(AppIcons.add(), f"➕ Add '{ipn}' to Altium")
            act_add.triggered.connect(lambda: self._on_add_part_clicked(it_part))

            act_link_existing = menu.addAction(AppIcons.link(), f"Link '{ipn}' to Selected Altium Component")
            act_link_existing.triggered.connect(lambda: self.link_warehouse_to_altium_requested.emit(it_part))

        menu.exec(self.table_view.viewport().mapToGlobal(pos))

    def _on_add_part_clicked(self, part_data: dict[str, Any] | None) -> None:
        if part_data:
            logger.info(f"User requested to add InvenTree part to Altium: {part_data.get('IPN')}")
            self.create_component_requested.emit(part_data)

    def _on_row_selected(self) -> None:
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes:
            return
        row_idx = indexes[0].row()
        if 0 <= row_idx < len(self.table_model.rows):
            row_data = self.table_model.rows[row_idx]
            it_part = row_data.get("inventree_part")
            if it_part:
                self.part_inspected.emit(it_part)

            altium_idx = row_data.get("altium_index")
            if altium_idx is not None:
                self.altium_row_focus_requested.emit(altium_idx)
