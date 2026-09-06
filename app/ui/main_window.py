# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import logging
from pathlib import Path
import re
from typing import Any
from PySide6.QtCore import Qt, QSortFilterProxyModel, QSize, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QFont, QColor, QIcon, QPen, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QTableView,
    QLineEdit,
    QPushButton,
    QLabel,
    QToolBar,
    QStatusBar,
    QMessageBox,
    QInputDialog,
    QHeaderView,
    QGroupBox,
    QProgressDialog,
    QMenu,
    QButtonGroup,
    QDialog,
)
from ..config import (
    DB_PATH,
    DBLIB_PATH,
    CACHE_DIR,
    to_absolute_path,
    get_db_path,
    get_symbols_dir,
    get_footprints_dir,
    AppSettingsManager,
    format_stock_value,
)
from ..db.access_manager import AccessDBManager, check_access_driver_installed
from ..db.dblib_sync import DbLibSync
from ..altium.preview_cache import PreviewCache
from ..altium.unit_engine import EngineeringValueParser, ColumnUnitConfigManager
from ..inventree.client import InvenTreeClient, ComponentLinkManager
from .table_view import ComponentsTableModel, TableItemDelegate, AltiumFilterProxyModel
from .svg_viewer import SvgViewer
from .footprint_preview_widget import FootprintPreviewWidget
from .library_browser import LibraryBrowserDialog
from .inventree_dialog import InvenTreeSearchDialog
from .warehouse_view import WarehouseLinkWidget
from .unit_config_dialog import ColumnUnitConfigDialog
from .inventree_settings_dialog import InvenTreeSettingsDialog
from .settings_dialog import SettingsDialog
from .driver_warning_dialog import AccessDriverWarningDialog
from .table_schema_dialog import TableSchemaDialog
from .table_create_dialog import TableCreateDialog
from .icons import AppIcons
from .styles import get_theme_palette, apply_theme
from .smooth_scroll import enable_smooth_scroll, install_global_wheel_scroll_filter

logger = logging.getLogger(__name__)


class VerticalBorderTab(QWidget):
    """
    Sleek vertical tab docked on panel boundary lines for one-click expand/collapse.
    Displays an icon, rotated vertical label, and directional arrow.
    """
    clicked = Signal()

    def __init__(
        self,
        text: str,
        icon: QIcon,
        arrow_text: str,
        orientation: str = "left",
        tooltip: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._icon = icon
        self._arrow = arrow_text
        self._orientation = orientation
        self._hovered = False

        self.setFixedWidth(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        if tooltip:
            self.setToolTip(tooltip)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()

        pal = get_theme_palette()

        # Boundary bar background and line
        bg_color = QColor(pal.get("btn_hover", "#252538")) if self._hovered else QColor(pal.get("bg_window", "#161622"))
        border_color = QColor(pal.get("accent_light", "#58a6ff")) if self._hovered else QColor(pal.get("border_color", "#2d2d42"))

        p.fillRect(0, 0, w, h, bg_color)
        p.setPen(border_color)
        line_x = w - 1 if self._orientation == "left" else 0
        p.drawLine(line_x, 0, line_x, h)

        # Tab pill indicator
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        fm = QFontMetrics(font)
        text_len = fm.horizontalAdvance(self._text)

        pill_pad = 10
        icon_h = 13
        arrow_h = 13
        gap = 8
        pill_h = pill_pad + icon_h + gap + text_len + gap + arrow_h + pill_pad
        pill_y = (h - pill_h) // 2

        pill_bg = QColor(pal.get("btn_hover", "#2d2d44")) if self._hovered else QColor(pal.get("tab_pill_bg", "#1e1e2d"))
        pill_border = QColor(pal.get("accent_light", "#58a6ff")) if self._hovered else QColor(pal.get("tab_pill_border", "#383852"))

        p.setPen(pill_border)
        p.setBrush(pill_bg)
        p.drawRoundedRect(2, pill_y, w - 5, pill_h, 4, 4)

        # Draw icon
        curr_y = pill_y + pill_pad
        if self._icon and not self._icon.isNull():
            pm = self._icon.pixmap(QSize(13, 13))
            p.drawPixmap((w - pm.width()) // 2, curr_y, pm)
        curr_y += icon_h + gap

        # Draw rotated vertical text centered horizontally & vertically in the key
        p.save()
        p.setFont(font)
        p.setPen(QColor(pal.get("text_primary", "#ffffff") if self._hovered else pal.get("text_secondary", "#b0b0cc")))
        text_center_y = curr_y + text_len / 2
        p.translate(w / 2, text_center_y)
        p.rotate(90)
        p.drawText(-text_len // 2, fm.capHeight() // 2, self._text)
        p.restore()
        curr_y += text_len + gap

        # Draw directional indicator arrow
        p.setFont(font)
        p.setPen(QColor(pal.get("accent_light", "#58a6ff") if self._hovered else pal.get("text_secondary", "#8080a0")))
        p.drawText(0, curr_y, w, arrow_h, Qt.AlignmentFlag.AlignCenter, self._arrow)
        p.end()


class MainWindow(QMainWindow):
    """Main window for the Altium Database Library (DbLib) Manager."""

    def __init__(self) -> None:
        super().__init__()
        # Ensure mouse wheel value changes are disabled application-wide
        install_global_wheel_scroll_filter()

        self.setWindowTitle("Altium Database Library (DbLib) Manager")
        self.resize(1400, 850)

        logger.info("Initializing MainWindow...")

        # Core Backend Services
        self.db_manager = AccessDBManager(get_db_path())
        self.dblib_sync = DbLibSync(DBLIB_PATH)
        self.preview_cache = PreviewCache()
        self.inventree_client = InvenTreeClient()
        self.link_manager = ComponentLinkManager()

        # Splitter panel memory
        self._last_cat_width = 180
        self._last_inspect_width = 440

        # Build UI
        self._init_toolbar()
        self._init_central_ui()
        self._init_statusbar()

        # Load initial data
        self._load_categories()

        # Check MS Access ODBC driver installation
        driver_installed, _, _ = check_access_driver_installed()
        if not driver_installed:
            logger.warning("Microsoft Access ODBC driver not detected on system.")
            QTimer.singleShot(300, self._show_driver_warning)

        logger.info("MainWindow initialized successfully.")

    def _show_driver_warning(self) -> None:
        dlg = AccessDriverWarningDialog(self)
        dlg.exec()

    def _init_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(toolbar)

        # Shortcut: Toggle Categories Sidebar (Ctrl+1)
        self.shortcut_cat = QShortcut(QKeySequence("Ctrl+1"), self)
        self.shortcut_cat.activated.connect(self._on_shortcut_toggle_cat)

        # Action: Add Component
        btn_add = QPushButton(" Add Component")
        btn_add.setIcon(AppIcons.add())
        btn_add.setObjectName("PrimaryButton")
        btn_add.clicked.connect(self._on_add_component)
        toolbar.addWidget(btn_add)

        # Action: Delete Component
        btn_del = QPushButton(" Delete Component")
        btn_del.setIcon(AppIcons.delete())
        btn_del.setObjectName("DangerButton")
        btn_del.clicked.connect(self._on_delete_component)
        toolbar.addWidget(btn_del)

        toolbar.addSeparator()

        # Action: InvenTree Sync Selected
        btn_sync_one = QPushButton(" Sync Selected")
        btn_sync_one.setIcon(AppIcons.sync_inventree())
        btn_sync_one.clicked.connect(self._on_sync_selected_inventree)
        toolbar.addWidget(btn_sync_one)

        # Action: InvenTree Sync All
        btn_sync_all = QPushButton(" Bulk Sync InvenTree")
        btn_sync_all.setIcon(AppIcons.sync_bulk())
        btn_sync_all.setObjectName("SuccessButton")
        btn_sync_all.clicked.connect(self._on_bulk_sync_inventree)
        toolbar.addWidget(btn_sync_all)

        toolbar.addSeparator()

        # Action: Refresh
        btn_refresh = QPushButton(" Refresh")
        btn_refresh.setIcon(AppIcons.refresh())
        btn_refresh.clicked.connect(self._on_refresh_current_table)
        toolbar.addWidget(btn_refresh)

        toolbar.addSeparator()

        # Action: Warehouse Split View
        self.btn_warehouse_toggle = QPushButton(" Warehouse Split View")
        self.btn_warehouse_toggle.setIcon(AppIcons.inventory_box())
        self.btn_warehouse_toggle.setCheckable(True)
        self.btn_warehouse_toggle.setChecked(False)
        self.btn_warehouse_toggle.toggled.connect(self._on_toggle_warehouse_view)
        toolbar.addWidget(self.btn_warehouse_toggle)

        # Action: Toggle Inspector Panel
        self.btn_toggle_inspector = QPushButton(" Inspector")
        self.btn_toggle_inspector.setIcon(AppIcons.sidebar_right())
        self.btn_toggle_inspector.setCheckable(True)
        self.btn_toggle_inspector.setChecked(True)
        self.btn_toggle_inspector.setShortcut("Ctrl+3")
        self.btn_toggle_inspector.setToolTip("Toggle Component Inspector (Symbols, Footprints & Sync) (Ctrl+3)")
        self.btn_toggle_inspector.toggled.connect(self._toggle_inspector_panel)
        toolbar.addWidget(self.btn_toggle_inspector)

        toolbar.addSeparator()

        # Action: Application Settings
        btn_settings = QPushButton(" Settings")
        btn_settings.setIcon(AppIcons.settings())
        btn_settings.setToolTip("Application Settings (Database, Library Paths, InvenTree Connection)")
        btn_settings.clicked.connect(self._on_open_settings)
        toolbar.addWidget(btn_settings)

    def _init_central_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # Master Splitter: [Categories Sidebar] | [Components Table] | [Inspect & Preview Panel]
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # ----------------- Pane 1: Categories Sidebar -----------------
        self.cat_widget = QWidget()
        cat_layout = QVBoxLayout(self.cat_widget)
        cat_layout.setContentsMargins(0, 0, 0, 0)
        cat_layout.setSpacing(6)

        cat_header_layout = QHBoxLayout()
        lbl_cat = QLabel("Categories (Tables):")
        lbl_cat.setStyleSheet("font-weight: bold; color: #a0a0c0; padding: 4px 0;")
        cat_header_layout.addWidget(lbl_cat)
        cat_header_layout.addStretch()

        btn_new_cat = QPushButton(" + New")
        btn_new_cat.setToolTip("Create a new category table")
        btn_new_cat.setFixedHeight(24)
        btn_new_cat.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        btn_new_cat.clicked.connect(self._on_create_category_table)
        cat_header_layout.addWidget(btn_new_cat)

        btn_close_cat = QPushButton()
        btn_close_cat.setIcon(AppIcons.chevron_left("#a0a0c0"))
        btn_close_cat.setToolTip("Collapse Categories Panel")
        btn_close_cat.setFixedSize(24, 24)
        btn_close_cat.setStyleSheet(
            "QPushButton { border: 1px solid #33334d; background: #212130; border-radius: 4px; padding: 0; }"
            "QPushButton:hover { background-color: #2e2e42; border-color: #58a6ff; }"
        )
        btn_close_cat.clicked.connect(lambda: self._toggle_categories_panel(False))
        cat_header_layout.addWidget(btn_close_cat)

        cat_layout.addLayout(cat_header_layout)

        self.categories_list = QListWidget(self)
        self.categories_list.itemClicked.connect(self._on_category_selected)
        self.categories_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.categories_list.customContextMenuRequested.connect(self._show_category_context_menu)
        enable_smooth_scroll(self.categories_list, step_v=30, step_h=40)
        cat_layout.addWidget(self.categories_list)
        self.main_splitter.addWidget(self.cat_widget)

        # ----------------- Pane 2: Components Table -----------------
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(6)

        # Table Filter & Counter Header
        top_filter_container = QWidget()
        top_filter_container.setFixedHeight(32)
        top_filter_layout = QHBoxLayout(top_filter_container)
        top_filter_layout.setContentsMargins(0, 0, 0, 0)
        top_filter_layout.setSpacing(6)

        self.filter_input = QLineEdit(self)
        self.filter_input.setFixedHeight(28)
        self.filter_input.setPlaceholderText("Filter components across all columns (Value, Part Number, Package, Stock...)...")
        self.filter_input.addAction(AppIcons.search(), QLineEdit.ActionPosition.LeadingPosition)
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.textChanged.connect(self._on_filter_changed)
        top_filter_layout.addWidget(self.filter_input)

        self.lbl_record_count = QLabel("0 components")
        self.lbl_record_count.setFixedHeight(28)
        self.lbl_record_count.setStyleSheet("color: #8f8fa8; font-weight: bold; padding: 0 8px;")
        top_filter_layout.addWidget(self.lbl_record_count)

        table_layout.addWidget(top_filter_container)

        # Data Model and Proxy
        self.table_model = ComponentsTableModel(self.db_manager, self)
        self.proxy_model = AltiumFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        self.table_view = QTableView(self)
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setShowGrid(True)
        enable_smooth_scroll(self.table_view, step_v=45, step_h=60)

        self.table_view.setItemDelegate(TableItemDelegate(self.table_view))
        self.table_view.verticalHeader().setDefaultSectionSize(30)
        self.table_view.verticalHeader().setMinimumSectionSize(30)
        self.table_view.verticalHeader().setMaximumSectionSize(30)
        self.table_view.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table_view.verticalHeader().setFixedWidth(38)

        header = self.table_view.horizontalHeader()
        header.setFixedHeight(30)
        header.setSectionsMovable(True)
        header.setFirstSectionMovable(True)
        header.setSectionsClickable(True)
        header.setHighlightSections(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.sectionMoved.connect(self._on_section_moved)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_context_menu)

        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_altium_table_context_menu)

        self.table_view.selectionModel().selectionChanged.connect(self._on_table_row_selected)
        self.table_model.dataChanged.connect(self._on_altium_data_changed)
        table_layout.addWidget(self.table_view)

        # Center Container with boundary border tabs on left and right edges
        self.center_container = QWidget(self)
        center_container_layout = QHBoxLayout(self.center_container)
        center_container_layout.setContentsMargins(0, 0, 0, 0)
        center_container_layout.setSpacing(0)

        # Vertical Border Tab for Categories (left boundary line)
        self.tab_border_cat = VerticalBorderTab(
            "Categories",
            AppIcons.sidebar_left("#58a6ff"),
            "▶",
            orientation="left",
            tooltip="Expand Categories Panel (Ctrl+1)",
            parent=self.center_container,
        )
        self.tab_border_cat.setVisible(False)
        self.tab_border_cat.clicked.connect(lambda: self._toggle_categories_panel(True))
        center_container_layout.addWidget(self.tab_border_cat)

        # Center Section Splitter (Altium Table + Warehouse Split View)
        self.center_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.center_splitter.addWidget(table_container)

        self.warehouse_view = WarehouseLinkWidget(self.inventree_client, self.link_manager, self)
        self.warehouse_view.setVisible(False)
        self.warehouse_view.create_component_requested.connect(self._on_create_component_from_warehouse)
        self.warehouse_view.edit_link_requested.connect(self._on_edit_warehouse_link)
        self.warehouse_view.unlink_component_requested.connect(self._on_unlink_component)
        self.warehouse_view.link_warehouse_to_altium_requested.connect(self._on_link_warehouse_part_to_selected_altium)
        self.warehouse_view.part_inspected.connect(self._on_warehouse_part_inspected)
        self.warehouse_view.altium_row_focus_requested.connect(self._on_focus_altium_row)
        self.warehouse_view.rows_rebuilt.connect(self._sync_table_spacers)

        # Synchronize vertical scrollbars for side-by-side alignment
        self.table_view.verticalScrollBar().valueChanged.connect(self.warehouse_view.table_view.verticalScrollBar().setValue)
        self.warehouse_view.table_view.verticalScrollBar().valueChanged.connect(self.table_view.verticalScrollBar().setValue)

        self.center_splitter.addWidget(self.warehouse_view)
        center_container_layout.addWidget(self.center_splitter, 1)

        # Vertical Border Tab for Inspector (right boundary line)
        self.tab_border_inspector = VerticalBorderTab(
            "Inspector",
            AppIcons.sidebar_right("#58a6ff"),
            "◀",
            orientation="right",
            tooltip="Expand Component Details & Preview Panel (Ctrl+3)",
            parent=self.center_container,
        )
        self.tab_border_inspector.setVisible(False)
        self.tab_border_inspector.clicked.connect(lambda: self.btn_toggle_inspector.setChecked(True))
        center_container_layout.addWidget(self.tab_border_inspector)

        self.main_splitter.addWidget(self.center_container)

        # ----------------- Pane 3: Inspect & Preview Panel -----------------
        self.inspect_container = QWidget()
        inspect_layout = QVBoxLayout(self.inspect_container)
        inspect_layout.setContentsMargins(0, 0, 0, 0)
        inspect_layout.setSpacing(8)

        # Top Header Bar with Title and Collapse Button
        inspect_header_layout = QHBoxLayout()
        lbl_inspect_title = QLabel("Component Details & Preview")
        lbl_inspect_title.setStyleSheet("font-weight: bold; color: #a0a0c0; font-size: 12px; padding: 3px 0;")
        inspect_header_layout.addWidget(lbl_inspect_title)
        inspect_header_layout.addStretch()

        btn_close_inspect = QPushButton()
        btn_close_inspect.setIcon(AppIcons.chevron_right("#a0a0c0"))
        btn_close_inspect.setToolTip("Collapse Inspector Panel")
        btn_close_inspect.setFixedSize(24, 24)
        btn_close_inspect.setStyleSheet(
            "QPushButton { border: 1px solid #33334d; background: #212130; border-radius: 4px; padding: 0; }"
            "QPushButton:hover { background-color: #2e2e42; border-color: #58a6ff; }"
        )
        btn_close_inspect.clicked.connect(lambda: self.btn_toggle_inspector.setChecked(False))
        inspect_header_layout.addWidget(btn_close_inspect)
        inspect_layout.addLayout(inspect_header_layout)

        # 1. Symbol Preview Card
        sym_box = QGroupBox("Schematic Symbol Preview", self)
        sym_box_layout = QVBoxLayout(sym_box)
        self.symbol_viewer = SvgViewer("Symbol", self)
        sym_box_layout.addWidget(self.symbol_viewer)

        sym_info_layout = QHBoxLayout()
        self.lbl_sym_path = QLabel("Ref: None")
        self.lbl_sym_path.setStyleSheet("color: #8888aa; font-size: 11px;")
        self.lbl_sym_path.setWordWrap(True)
        sym_info_layout.addWidget(self.lbl_sym_path)

        sym_btn = QPushButton(" Change...")
        sym_btn.setIcon(AppIcons.edit())
        sym_btn.setIconSize(QSize(13, 13))
        sym_btn.clicked.connect(self._on_browse_symbol)
        sym_info_layout.addWidget(sym_btn)
        sym_box_layout.addLayout(sym_info_layout)
        inspect_layout.addWidget(sym_box, 1)

        # 2. Footprint Preview Card (Supports up to 3 Footprints)
        fp_box = QGroupBox("PCB Footprint Preview", self)
        fp_box_layout = QVBoxLayout(fp_box)

        # Slot selector buttons (FP 1, FP 2, FP 3)
        slot_layout = QHBoxLayout()
        slot_layout.setSpacing(4)
        slot_layout.setContentsMargins(0, 0, 0, 2)

        self.btn_fp_slot1 = QPushButton("FP 1 (Primary) ○")
        self.btn_fp_slot2 = QPushButton("FP 2 ○")
        self.btn_fp_slot3 = QPushButton("FP 3 ○")

        self.fp_slot_group = QButtonGroup(self)
        self.fp_slot_group.setExclusive(True)

        slot_btn_style = """
            QPushButton {
                background-color: #212130;
                color: #a0a0c0;
                border: 1px solid #33334d;
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #2a2a3e;
                color: #ffffff;
                border-color: #4a4a6e;
            }
            QPushButton:checked {
                background-color: #007acc;
                color: #ffffff;
                border-color: #0099ff;
                font-weight: bold;
            }
        """

        for slot_id, btn in [(1, self.btn_fp_slot1), (2, self.btn_fp_slot2), (3, self.btn_fp_slot3)]:
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(slot_btn_style)
            self.fp_slot_group.addButton(btn, slot_id)
            slot_layout.addWidget(btn)

        self.btn_fp_slot1.setChecked(True)
        self.active_fp_slot = 1
        self.fp_slot_group.idClicked.connect(self._on_fp_slot_changed)
        fp_box_layout.addLayout(slot_layout)

        self.footprint_viewer = FootprintPreviewWidget("Footprint", self)
        fp_box_layout.addWidget(self.footprint_viewer)

        fp_info_layout = QHBoxLayout()
        self.lbl_fp_path = QLabel("Ref: None")
        self.lbl_fp_path.setStyleSheet("color: #8888aa; font-size: 11px;")
        self.lbl_fp_path.setWordWrap(True)
        fp_info_layout.addWidget(self.lbl_fp_path, 1)

        self.fp_btn = QPushButton(" Change...")
        self.fp_btn.setIcon(AppIcons.edit())
        self.fp_btn.setIconSize(QSize(13, 13))
        self.fp_btn.clicked.connect(lambda: self._on_browse_footprint())
        fp_info_layout.addWidget(self.fp_btn)

        self.fp_clear_btn = QPushButton(" Clear")
        self.fp_clear_btn.setIcon(AppIcons.delete())
        self.fp_clear_btn.setIconSize(QSize(13, 13))
        self.fp_clear_btn.setEnabled(False)
        self.fp_clear_btn.clicked.connect(lambda: self._on_clear_footprint())
        fp_info_layout.addWidget(self.fp_clear_btn)

        fp_box_layout.addLayout(fp_info_layout)
        inspect_layout.addWidget(fp_box, 2)

        # 3. InvenTree Live Card
        it_box = QGroupBox("InvenTree Inventory Status", self)
        it_box_layout = QVBoxLayout(it_box)

        self.lbl_it_details = QLabel("Select a component to inspect InvenTree status.")
        self.lbl_it_details.setStyleSheet("color: #cccccc; font-size: 12px; line-height: 1.4;")
        self.lbl_it_details.setWordWrap(True)
        it_box_layout.addWidget(self.lbl_it_details)

        it_actions = QHBoxLayout()
        self.btn_it_sync_this = QPushButton(" Sync Now")
        self.btn_it_sync_this.setIcon(AppIcons.sync_inventree())
        self.btn_it_sync_this.setIconSize(QSize(14, 14))
        self.btn_it_sync_this.clicked.connect(self._on_sync_selected_inventree)
        it_actions.addWidget(self.btn_it_sync_this)

        self.btn_it_search_link = QPushButton(" Edit Link...")
        self.btn_it_search_link.setIcon(AppIcons.link())
        self.btn_it_search_link.setIconSize(QSize(14, 14))
        self.btn_it_search_link.clicked.connect(self._on_search_link_inventree)
        it_actions.addWidget(self.btn_it_search_link)

        self.btn_it_unlink = QPushButton(" Unlink")
        self.btn_it_unlink.setIcon(AppIcons.delete())
        self.btn_it_unlink.setIconSize(QSize(14, 14))
        self.btn_it_unlink.clicked.connect(self._on_unlink_selected_inventree)
        it_actions.addWidget(self.btn_it_unlink)

        it_box_layout.addLayout(it_actions)

        inspect_layout.addWidget(it_box)
        self.main_splitter.addWidget(self.inspect_container)

        # Set initial splitter layout sizes
        self.main_splitter.setSizes([180, 740, 440])
        main_layout.addWidget(self.main_splitter)

    def _on_shortcut_toggle_cat(self) -> None:
        self._toggle_categories_panel(not self.cat_widget.isVisible())

    @property
    def btn_toggle_cat(self):
        class _DummyToggle:
            def __init__(self, parent):
                self._p = parent
            def setChecked(self, val: bool) -> None:
                self._p._toggle_categories_panel(val)
            def isChecked(self) -> bool:
                return self._p.cat_widget.isVisible()
        return _DummyToggle(self)

    def _toggle_categories_panel(self, checked: bool) -> None:
        sizes = self.main_splitter.sizes()
        if checked:
            self.cat_widget.setVisible(True)
            self.tab_border_cat.setVisible(False)
            left_w = getattr(self, "_last_cat_width", 180) or 180
            center_w = sizes[1] if len(sizes) > 1 and sizes[1] > 0 else 740
            right_w = sizes[2] if len(sizes) > 2 else (440 if self.inspect_container.isVisible() else 0)
            self.main_splitter.setSizes([left_w, center_w, right_w])
        else:
            if len(sizes) > 0 and sizes[0] > 50:
                self._last_cat_width = sizes[0]
            self.cat_widget.setVisible(False)
            self.tab_border_cat.setVisible(True)

    def _toggle_inspector_panel(self, checked: bool) -> None:
        if self.btn_toggle_inspector.isChecked() != checked:
            self.btn_toggle_inspector.blockSignals(True)
            self.btn_toggle_inspector.setChecked(checked)
            self.btn_toggle_inspector.blockSignals(False)

        sizes = self.main_splitter.sizes()
        if checked:
            self.inspect_container.setVisible(True)
            self.tab_border_inspector.setVisible(False)
            left_w = sizes[0] if len(sizes) > 0 else (180 if self.cat_widget.isVisible() else 0)
            center_w = sizes[1] if len(sizes) > 1 and sizes[1] > 0 else 740
            right_w = getattr(self, "_last_inspect_width", 440) or 440
            self.main_splitter.setSizes([left_w, center_w, right_w])
        else:
            if len(sizes) > 2 and sizes[2] > 50:
                self._last_inspect_width = sizes[2]
            self.inspect_container.setVisible(False)
            self.tab_border_inspector.setVisible(True)

    def _init_statusbar(self) -> None:
        statusbar = QStatusBar(self)
        self.setStatusBar(statusbar)

        self.lbl_status_db = QLabel(f"DB: {self.db_manager.db_path.name}")
        self.lbl_status_db.setStyleSheet("padding: 0 8px; color: #88aa88;")
        statusbar.addPermanentWidget(self.lbl_status_db)

        it_ok, it_msg = self.inventree_client.test_connection()
        self.lbl_status_it = QLabel(f"InvenTree: {'Connected' if it_ok else 'Offline'}")
        self.lbl_status_it.setStyleSheet(f"padding: 0 8px; color: {'#40ff80' if it_ok else '#ff5555'};")
        statusbar.addPermanentWidget(self.lbl_status_it)

        statusbar.showMessage("Ready")

    # ---------------- Category Management ----------------
    def _load_categories(self) -> None:
        logger.info("Loading categories from database...")
        self.categories_list.clear()
        tables = self.db_manager.list_tables()
        for tname in tables:
            item = QListWidgetItem(tname)
            self.categories_list.addItem(item)

        if tables:
            first_item = self.categories_list.item(0)
            self.categories_list.setCurrentItem(first_item)
            self._on_category_selected(first_item)

    def _on_category_selected(self, item: QListWidgetItem) -> None:
        table_name = item.text()
        logger.info(f"Category selected: {table_name}")
        self.table_model.load_table(table_name)
        count = len(self.table_model.records)
        self.lbl_record_count.setText(f"{count} component{'s' if count != 1 else ''}")
        restored = self._restore_current_table_column_layout()
        if not restored:
            self._auto_fit_columns()
        if hasattr(self, "warehouse_view") and not self.warehouse_view.isHidden():
            self.warehouse_view.set_altium_context(table_name, self._get_displayed_altium_records())
        self.statusBar().showMessage(f"Loaded category: {table_name} ({count} items)")
        self._clear_previews()

    def _show_category_context_menu(self, pos) -> None:
        item = self.categories_list.itemAt(pos)
        menu = QMenu(self)

        if item:
            table_name = item.text()
            act_schema = menu.addAction(AppIcons.table(), f"Manage Columns / Schema for '{table_name}'...")
            act_schema.triggered.connect(lambda: self._on_manage_table_schema(table_name))

            act_rename = menu.addAction(AppIcons.edit(), f"Rename Category '{table_name}'...")
            act_rename.triggered.connect(lambda: self._on_rename_category(table_name))

            act_delete = menu.addAction(AppIcons.delete(), f"Delete Category '{table_name}'")
            act_delete.triggered.connect(lambda: self._on_delete_category(table_name))

            menu.addSeparator()

        act_new = menu.addAction(AppIcons.add(), " + New Category (Table)...")
        act_new.triggered.connect(self._on_create_category_table)

        act_refresh = menu.addAction(AppIcons.refresh(), " Refresh Categories")
        act_refresh.triggered.connect(self._load_categories)

        menu.exec(self.categories_list.mapToGlobal(pos))

    def _on_create_category_table(self) -> None:
        dlg = TableCreateDialog(self.db_manager, self)
        dlg.table_created.connect(lambda _: self._load_categories())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load_categories()

    def _on_manage_table_schema(self, table_name: str) -> None:
        dlg = TableSchemaDialog(self.db_manager, table_name, self)
        dlg.schema_changed.connect(self._on_schema_changed)
        dlg.exec()

    def _on_schema_changed(self, table_name: str) -> None:
        if self.table_model.current_table == table_name:
            self.table_model.load_table(table_name)
            restored = self._restore_current_table_column_layout()
            if not restored:
                self._auto_fit_columns()
            self.lbl_record_count.setText(f"{len(self.table_model.records)} components")

    def _on_rename_category(self, old_name: str) -> None:
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Category Table",
            f"Enter new name for category table '{old_name}':",
            text=old_name,
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return

        new_name = new_name.strip()
        if not re.match(r"^[A-Za-z0-9_ ]+$", new_name):
            QMessageBox.warning(self, "Invalid Name", "Table name can only contain letters, numbers, spaces, and underscores.")
            return

        try:
            self.db_manager.rename_table(old_name, new_name)
            self.dblib_sync.rename_table_in_dblib(old_name, new_name)
            self._load_categories()
            # Select the renamed item
            for i in range(self.categories_list.count()):
                it = self.categories_list.item(i)
                if it.text() == new_name:
                    self.categories_list.setCurrentItem(it)
                    self._on_category_selected(it)
                    break
            QMessageBox.information(self, "Category Renamed", f"Category '{old_name}' renamed to '{new_name}'.")
        except Exception as exc:
            logger.error(f"Failed to rename table '{old_name}' to '{new_name}': {exc}", exc_info=True)
            QMessageBox.critical(self, "Error Renaming Category", f"Failed to rename category:\n{exc}")

    def _on_delete_category(self, table_name: str) -> None:
        confirm = QMessageBox.question(
            self,
            "Confirm Category Deletion",
            f"Are you sure you want to permanently delete category table '{table_name}'?\n\n"
            f"All components, records, and schema in this table will be permanently removed from the database and Altium library.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self.db_manager.drop_table(table_name)
            self.dblib_sync.remove_table_from_dblib(table_name)
            self._load_categories()
            QMessageBox.information(self, "Category Deleted", f"Category table '{table_name}' was successfully deleted.")
        except Exception as exc:
            logger.error(f"Failed to delete table '{table_name}': {exc}", exc_info=True)
            QMessageBox.critical(self, "Error Deleting Category", f"Failed to delete category:\n{exc}")

    # ---------------- Component Row Selection & Previews ----------------
    def _get_current_source_row(self) -> int | None:
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes:
            indexes = self.table_view.selectionModel().selectedIndexes()
        if not indexes:
            return None
        proxy_idx = indexes[0]
        source_idx = self.proxy_model.mapToSource(proxy_idx)
        if not source_idx.isValid():
            return None
        return source_idx.row()

    def _on_table_row_selected(self) -> None:
        try:
            row = self._get_current_source_row()
            if row is None:
                self._clear_previews()
                return

            rec = self.table_model.get_record(row)
            if not rec:
                self._clear_previews()
                return

            pn = rec.get("Part Number") or ""
            row_id = rec.get("ID")
            logger.debug(f"Row selected: index={row}, ID={row_id}, Part Number={pn}")

            # 1. Update Symbol Preview
            sym_path = rec.get("Library Path") or ""
            sym_ref = rec.get("Library Ref") or ""
            if sym_path and sym_ref:
                self.lbl_sym_path.setText(f"Ref: {sym_ref}\nFile: {Path(sym_path).name}")
                logger.debug(f"Loading symbol preview for {sym_ref} from {sym_path}")
                svg_str = self.preview_cache.get_svg(sym_path, sym_ref)
                self.symbol_viewer.load_svg(svg_str, sym_ref)
            else:
                self.lbl_sym_path.setText("Ref: Not assigned")
                self.symbol_viewer.show_placeholder("No symbol assigned")

            # 2. Update Footprint Slot Indicators and Active Preview
            fp1_ref = rec.get("Footprint Ref")
            fp2_ref = rec.get("Footprint Ref 2")
            fp3_ref = rec.get("Footprint Ref 3")

            if hasattr(self, "btn_fp_slot1"):
                self.btn_fp_slot1.setText(f"FP 1 (Primary) {'●' if fp1_ref else '○'}")
                self.btn_fp_slot1.setToolTip(f"Footprint 1 (Primary): {fp1_ref or 'None'}")
            if hasattr(self, "btn_fp_slot2"):
                self.btn_fp_slot2.setText(f"FP 2 {'●' if fp2_ref else '○'}")
                self.btn_fp_slot2.setToolTip(f"Footprint 2: {fp2_ref or 'None'}")
            if hasattr(self, "btn_fp_slot3"):
                self.btn_fp_slot3.setText(f"FP 3 {'●' if fp3_ref else '○'}")
                self.btn_fp_slot3.setToolTip(f"Footprint 3: {fp3_ref or 'None'}")

            self._update_active_footprint_preview()

            # 3. Update InvenTree Status Details
            table_name = self.table_model.current_table
            raw_stock = rec.get("Stock")
            stock_str = str(raw_stock) if raw_stock is not None else "0"
            loc = rec.get("Location") or "Unknown"

            status_str = ""
            it_ipn_display = "—"
            if table_name and row_id:
                link = self.link_manager.get_link(table_name, row_id)
                if link and link.get("unlinked"):
                    status_str = "<span style='color: #8888aa;'>⚪ Manually Unlinked</span>"
                    self.btn_it_unlink.setEnabled(False)
                elif link and link.get("inventree_pk"):
                    it_ipn_display = str(link.get("inventree_ipn") or f"PK {link.get('inventree_pk')}")
                    status_str = f"<span style='color: #40ff80;'>🟢 Linked ({it_ipn_display})</span>"
                    self.btn_it_unlink.setEnabled(True)
                elif rec.get("IPN"):
                    it_ipn_display = str(rec.get("IPN"))
                    status_str = f"<span style='color: #40ff80;'>🟢 Linked ({it_ipn_display})</span>"
                    self.btn_it_unlink.setEnabled(True)
                else:
                    status_str = "<span style='color: #8888aa;'>⚪ Not Linked</span>"
                    self.btn_it_unlink.setEnabled(False)
            else:
                self.btn_it_unlink.setEnabled(False)

            self.lbl_it_details.setText(
                f"<b>Status:</b> {status_str}<br>"
                f"<b>Warehouse IPN:</b> {it_ipn_display}<br>"
                f"<b>Current Stock:</b> <span style='color: #40ff80; font-weight: bold;'>{stock_str}</span><br>"
                f"<b>Current Location:</b> <span style='color: #4da6ff; font-weight: bold;'>{loc}</span>"
            )
            # 4. Synchronize selection to Warehouse split view
            if hasattr(self, "warehouse_view") and not self.warehouse_view.isHidden():
                proxy_idx = self.table_view.currentIndex()
                if proxy_idx.isValid():
                    p_row = proxy_idx.row()
                    if p_row < self.warehouse_view.table_model.rowCount():
                        self.warehouse_view.table_view.blockSignals(True)
                        self.warehouse_view.table_view.selectRow(p_row)
                        self.warehouse_view.table_view.blockSignals(False)
        except Exception as exc:
            logger.error(f"Error in _on_table_row_selected: {exc}", exc_info=True)

    def _get_fp_column_names(self, slot: int = 1) -> tuple[str, str]:
        """Return (ref_col, path_col) for given footprint slot (1, 2, or 3)."""
        if slot == 2:
            return "Footprint Ref 2", "Footprint Path 2"
        elif slot == 3:
            return "Footprint Ref 3", "Footprint Path 3"
        return "Footprint Ref", "Footprint Path"

    def _on_fp_slot_changed(self, slot_id: int) -> None:
        self.active_fp_slot = slot_id
        self._update_active_footprint_preview()

    def _update_active_footprint_preview(self) -> None:
        """Update footprint SVG viewer and path label according to current active slot."""
        row = self._get_current_source_row()
        slot = getattr(self, "active_fp_slot", 1)
        slot_label = "Primary" if slot == 1 else f"Slot {slot}"

        if row is None:
            self.lbl_fp_path.setText(f"FP {slot} ({slot_label}): None")
            self.footprint_viewer.show_placeholder("Select a component")
            if hasattr(self, "fp_clear_btn"):
                self.fp_clear_btn.setEnabled(False)
            return

        rec = self.table_model.get_record(row)
        if not rec:
            self.lbl_fp_path.setText(f"FP {slot} ({slot_label}): None")
            self.footprint_viewer.show_placeholder("Select a component")
            if hasattr(self, "fp_clear_btn"):
                self.fp_clear_btn.setEnabled(False)
            return

        ref_col, path_col = self._get_fp_column_names(slot)
        fp_path = rec.get(path_col) or ""
        fp_ref = rec.get(ref_col) or ""

        if fp_path and fp_ref:
            self.lbl_fp_path.setText(f"FP {slot} ({slot_label}): {fp_ref}\nFile: {Path(fp_path).name}")
            logger.debug(f"Loading footprint preview for slot {slot}: {fp_ref} from {fp_path}")
            svg_str = self.preview_cache.get_svg(fp_path, fp_ref)
            self.footprint_viewer.load_footprint(fp_path, fp_ref, svg_str, title=fp_ref)
            if hasattr(self, "fp_clear_btn"):
                self.fp_clear_btn.setEnabled(True)
        else:
            self.lbl_fp_path.setText(f"FP {slot} ({slot_label}): Not assigned")
            self.footprint_viewer.show_placeholder(f"No Footprint {slot} assigned")
            if hasattr(self, "fp_clear_btn"):
                self.fp_clear_btn.setEnabled(False)

    def _clear_previews(self) -> None:
        self.symbol_viewer.show_placeholder("Select a component")
        self.lbl_sym_path.setText("Ref: None")
        self.footprint_viewer.show_placeholder("Select a component")
        slot = getattr(self, "active_fp_slot", 1)
        slot_label = "Primary" if slot == 1 else f"Slot {slot}"
        self.lbl_fp_path.setText(f"FP {slot} ({slot_label}): None")
        if hasattr(self, "btn_fp_slot1"):
            self.btn_fp_slot1.setText("FP 1 (Primary) ○")
            self.btn_fp_slot1.setToolTip("Footprint 1 (Primary): None")
        if hasattr(self, "btn_fp_slot2"):
            self.btn_fp_slot2.setText("FP 2 ○")
            self.btn_fp_slot2.setToolTip("Footprint 2: None")
        if hasattr(self, "btn_fp_slot3"):
            self.btn_fp_slot3.setText("FP 3 ○")
            self.btn_fp_slot3.setToolTip("Footprint 3: None")
        if hasattr(self, "fp_clear_btn"):
            self.fp_clear_btn.setEnabled(False)
        self.lbl_it_details.setText("Select a component to inspect InvenTree status.")
        if hasattr(self, "btn_it_unlink"):
            self.btn_it_unlink.setEnabled(False)

    def _get_displayed_altium_records(self) -> list[dict[str, Any]]:
        """Return the list of Altium component records currently visible in proxy model."""
        records = []
        for proxy_row in range(self.proxy_model.rowCount()):
            src_idx = self.proxy_model.mapToSource(self.proxy_model.index(proxy_row, 0))
            if src_idx.isValid():
                rec = self.table_model.get_record(src_idx.row())
                if rec:
                    records.append(rec)
        return records

    def _on_filter_changed(self, text: str) -> None:
        self.proxy_model.setFilterRegularExpression(text)
        total = len(self.table_model.records)
        disp_count = len(self._get_displayed_altium_records())
        if text.strip():
            self.lbl_record_count.setText(f"{disp_count} of {total} components")
        else:
            self.lbl_record_count.setText(f"{total} component{'s' if total != 1 else ''}")
        if hasattr(self, "warehouse_view") and not self.warehouse_view.isHidden():
            self.warehouse_view.set_altium_context(
                self.table_model.current_table,
                self._get_displayed_altium_records(),
            )

    def _on_altium_data_changed(self, top_left: QModelIndex, bottom_right: QModelIndex, roles: list[int] | None = None) -> None:
        """Keep warehouse view synchronized when Altium table cells are edited."""
        if hasattr(self, "warehouse_view") and not self.warehouse_view.isHidden():
            self.warehouse_view.set_altium_context(
                self.table_model.current_table,
                self._get_displayed_altium_records(),
            )

    # ---------------- Component CRUD ----------------
    def _on_add_component(self) -> None:
        table_name = self.table_model.current_table
        if not table_name:
            QMessageBox.warning(self, "No Category Selected", "Please select a category table from the left sidebar first.")
            return

        logger.info(f"Adding new component to table '{table_name}'")
        try:
            # Clear filter so the new row is immediately visible
            if self.filter_input.text():
                self.filter_input.clear()

            new_id = self.db_manager.insert_record(table_name, {})
            self.table_model.load_table(table_name)
            count = self.table_model.rowCount()
            self.lbl_record_count.setText(f"{count} component{'s' if count != 1 else ''}")

            # Find and select the new row, and activate editor on Package or Value
            for r in range(self.table_model.rowCount()):
                if self.table_model.records[r].get("ID") == new_id:
                    col_idx = 1
                    if "Package" in self.table_model.columns:
                        col_idx = self.table_model.columns.index("Package")
                    elif "Value" in self.table_model.columns:
                        col_idx = self.table_model.columns.index("Value")
                    src_idx = self.table_model.index(r, col_idx)
                    proxy_idx = self.proxy_model.mapFromSource(src_idx)

                    self.table_view.selectRow(proxy_idx.row())
                    self.table_view.setCurrentIndex(proxy_idx)
                    self.table_view.scrollTo(proxy_idx)
                    self.table_view.edit(proxy_idx)
                    break

            # Update warehouse alignment view
            if hasattr(self, "warehouse_view") and not self.warehouse_view.isHidden():
                self.warehouse_view.set_altium_context(
                    table_name,
                    self._get_displayed_altium_records(),
                )

            self.statusBar().showMessage(f"Added new component (ID {new_id}) to table '{table_name}'")
        except Exception as exc:
            logger.error(f"Failed to add component to {table_name}: {exc}", exc_info=True)
            QMessageBox.critical(self, "Error Adding Component", f"Failed to insert record:\n{exc}")

    def _on_delete_component(self) -> None:
        row = self._get_current_source_row()
        if row is None:
            QMessageBox.warning(self, "No Selection", "Please select a component to delete.")
            return

        rec = self.table_model.get_record(row)
        if not rec:
            return

        row_id = rec.get("ID")
        pn = rec.get("Part Number") or f"ID {row_id}"

        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete component '{pn}' (ID: {row_id})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        table_name = self.table_model.current_table
        logger.info(f"Deleting component ID {row_id} from {table_name}")
        try:
            self.db_manager.delete_record(table_name, row_id)
            # Clear link override for this deleted component
            self.link_manager.clear_override(table_name, row_id)

            self.table_model.load_table(table_name)
            count = len(self.table_model.records)
            self.lbl_record_count.setText(f"{count} component{'s' if count != 1 else ''}")
            self._clear_previews()

            # Refresh warehouse split view so no orphaned/ghost rows remain!
            if hasattr(self, "warehouse_view") and not self.warehouse_view.isHidden():
                self.warehouse_view.set_altium_context(
                    table_name,
                    self._get_displayed_altium_records(),
                )

            self.statusBar().showMessage(f"Deleted component {pn}")
        except Exception as exc:
            logger.error(f"Failed to delete component {row_id}: {exc}", exc_info=True)
            QMessageBox.critical(self, "Error Deleting", f"Failed to delete record:\n{exc}")

    def _on_refresh_current_table(self) -> None:
        if self.table_model.current_table:
            logger.info(f"Refreshing table {self.table_model.current_table}")
            self.table_model.load_table(self.table_model.current_table)
            self._on_table_row_selected()
            if hasattr(self, "warehouse_view") and not self.warehouse_view.isHidden():
                self.warehouse_view.set_altium_context(
                    self.table_model.current_table,
                    self._get_displayed_altium_records(),
                )
            self.statusBar().showMessage(f"Table refreshed: {self.table_model.current_table}")

    # ---------------- Symbol & Footprint Browsers ----------------
    def _on_browse_symbol(self) -> None:
        row = self._get_current_source_row()
        if row is None:
            QMessageBox.warning(self, "No Component Selected", "Please select a component from the table first.")
            return

        rec = self.table_model.get_record(row)
        init_p = str(rec.get("Library Path") or "") if rec else ""
        init_r = str(rec.get("Library Ref") or "") if rec else ""

        dialog = LibraryBrowserDialog(
            mode="SYMBOL",
            cache=self.preview_cache,
            initial_path=init_p,
            initial_part=init_r,
            parent=self,
        )
        if dialog.exec():
            rel_path, part_name = dialog.get_selection()
            if rel_path and part_name:
                logger.info(f"Assigning symbol {part_name} ({rel_path}) to row {row}")
                self.table_model.update_record_in_model(
                    row,
                    {"Library Path": rel_path, "Library Ref": part_name},
                )
                self._on_table_row_selected()
                self.statusBar().showMessage(f"Assigned symbol: {part_name}")

    def _on_browse_footprint(self, slot: int | None = None) -> None:
        if slot is None:
            slot = getattr(self, "active_fp_slot", 1)

        row = self._get_current_source_row()
        if row is None:
            QMessageBox.warning(self, "No Component Selected", "Please select a component from the table first.")
            return

        rec = self.table_model.get_record(row)
        ref_col, path_col = self._get_fp_column_names(slot)
        init_p = str(rec.get(path_col) or "") if rec else ""
        init_r = str(rec.get(ref_col) or "") if rec else ""

        dialog = LibraryBrowserDialog(
            mode="FOOTPRINT",
            cache=self.preview_cache,
            initial_path=init_p,
            initial_part=init_r,
            parent=self,
        )
        if dialog.exec():
            rel_path, part_name = dialog.get_selection()
            if rel_path and part_name:
                logger.info(f"Assigning Footprint {slot} {part_name} ({rel_path}) to row {row}")
                self.table_model.update_record_in_model(
                    row,
                    {path_col: rel_path, ref_col: part_name},
                )
                self.active_fp_slot = slot
                if slot == 1 and hasattr(self, "btn_fp_slot1"):
                    self.btn_fp_slot1.setChecked(True)
                elif slot == 2 and hasattr(self, "btn_fp_slot2"):
                    self.btn_fp_slot2.setChecked(True)
                elif slot == 3 and hasattr(self, "btn_fp_slot3"):
                    self.btn_fp_slot3.setChecked(True)
                self._on_table_row_selected()
                self.statusBar().showMessage(f"Assigned Footprint {slot}: {part_name}")

    def _on_clear_footprint(self, slot: int | None = None) -> None:
        if slot is None:
            slot = getattr(self, "active_fp_slot", 1)

        row = self._get_current_source_row()
        if row is None:
            QMessageBox.warning(self, "No Component Selected", "Please select a component from the table first.")
            return

        rec = self.table_model.get_record(row)
        if not rec:
            return

        ref_col, path_col = self._get_fp_column_names(slot)
        current_ref = rec.get(ref_col)
        current_path = rec.get(path_col)
        if not current_ref and not current_path:
            return

        slot_label = "Primary Footprint" if slot == 1 else f"Footprint {slot}"
        confirm = QMessageBox.question(
            self,
            "Clear Footprint",
            f"Are you sure you want to remove {slot_label} ('{current_ref}') from this component?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        logger.info(f"Clearing Footprint {slot} for row {row}")
        self.table_model.update_record_in_model(
            row,
            {path_col: None, ref_col: None},
        )
        self._on_table_row_selected()
        self.statusBar().showMessage(f"Cleared {slot_label}")

    def _on_open_settings(self) -> None:
        dialog = SettingsDialog(self.inventree_client, self.db_manager, parent=self)
        if dialog.exec():
            # 1. Check if database changed
            if dialog.db_changed:
                new_db_path = get_db_path()
                logger.info(f"Database path changed to: {new_db_path}")
                self.db_manager.set_db_path(new_db_path)
                self.lbl_status_db.setText(f"DB: {new_db_path.name}")
                self._load_categories()
                self.statusBar().showMessage(f"Database switched to: {new_db_path.name}")

            # 2. Check if InvenTree changed
            if dialog.inventree_changed:
                it_ok, it_msg = self.inventree_client.test_connection()
                self.lbl_status_it.setText(f"InvenTree: {'Connected' if it_ok else 'Offline'}")
                self.lbl_status_it.setStyleSheet(f"padding: 0 8px; color: {'#40ff80' if it_ok else '#ff5555'};")
                if hasattr(self, "warehouse_view") and not self.warehouse_view.isHidden():
                    self.warehouse_view.set_altium_context(
                        self.table_model.current_table,
                        self._get_displayed_altium_records(),
                    )
                self.statusBar().showMessage("InvenTree settings updated.")

            # 3. Check if library paths changed
            if dialog.libraries_changed:
                self.statusBar().showMessage("Altium library paths updated.")

            # 4. Check if field mappings changed
            if getattr(dialog, "mappings_changed", False):
                self.statusBar().showMessage("InvenTree field mappings updated.")

            # 5. Check if theme changed
            if getattr(dialog, "theme_changed", False):
                self.statusBar().showMessage(f"Theme updated to: {dialog.new_theme}")
                self.tab_border_cat.update()
                self.tab_border_inspector.update()
                self.update()

    def _on_inventree_settings(self) -> None:
        self._on_open_settings()

    # ---------------- InvenTree Sync & Field Mapping ----------------
    def _apply_field_mappings(self, table_name: str, it_part_data: dict[str, Any]) -> dict[str, Any]:
        """
        Map InvenTree attributes/parameters to Altium columns based on user configuration,
        only applying fields if the target column exists in the database table ("if present").
        """
        if not table_name or not it_part_data:
            return {}

        available_cols = set(self.db_manager.get_columns(table_name))
        mappings = AppSettingsManager.get_instance().get_field_mappings()

        updates: dict[str, Any] = {}
        for m in mappings:
            if not m.get("enabled", True):
                continue
            it_field = (m.get("inventree_field") or "").strip()
            db_col = (m.get("db_column") or "").strip()

            # Only sync if the column actually exists in this Altium table ("if present")
            if not db_col or db_col not in available_cols:
                continue

            val = None
            if it_field == "total_in_stock":
                val = it_part_data.get("formatted_stock")
                if val is None:
                    val = it_part_data.get("total_in_stock")
            elif it_field in it_part_data:
                val = it_part_data.get(it_field)
            else:
                # Search custom parameters case-insensitively
                params = it_part_data.get("parameters") or {}
                for pk, pv in params.items():
                    if pk.lower() == it_field.lower():
                        val = pv
                        break

            if val is not None:
                updates[db_col] = val

        return updates

    def _on_sync_selected_inventree(self) -> None:
        row = self._get_current_source_row()
        if row is None:
            QMessageBox.warning(self, "No Component Selected", "Please select a component to sync.")
            return

        rec = self.table_model.get_record(row)
        if not rec:
            return

        table_name = self.table_model.current_table
        if not table_name:
            return

        row_id = rec.get("ID")
        part_pk = None
        linked_ipn = ""

        # 1. Look up in Python application's link database by Access ID (table_name + row_id)
        if row_id is not None:
            link = self.link_manager.get_link(table_name, row_id)
            if link and not link.get("unlinked") and link.get("inventree_pk"):
                part_pk = int(link["inventree_pk"])
                linked_ipn = str(link.get("inventree_ipn") or "")

        # 2. If not linked in link database, check if Access record has an explicit IPN field
        if not part_pk and row_id is not None:
            db_ipn = str(rec.get("IPN") or "").strip()
            if db_ipn:
                self.statusBar().showMessage(f"Looking up warehouse part by IPN '{db_ipn}'...")
                part = self.inventree_client.find_part_by_ipn(db_ipn)
                if part:
                    part_pk = int(part["pk"])
                    linked_ipn = str(part.get("IPN") or db_ipn)
                    self.link_manager.set_link(table_name, row_id, part)
                    logger.info(f"Auto-linked component [{table_name}] ID={row_id} to InvenTree PK={part_pk} ({linked_ipn})")

        # 3. If still not linked, DO NOT search or guess by Part Number!
        if not part_pk:
            comp_name = rec.get("Part Number") or f"ID #{row_id}"
            reply = QMessageBox.question(
                self,
                "Component Not Linked",
                f"Component '{comp_name}' (ID #{row_id}) is not linked to any warehouse part.\n\n"
                f"Would you like to search and link it with an InvenTree part now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._on_edit_warehouse_link(rec)
            return

        # 4. Perform sync using the unique warehouse ID (part_pk)
        fmt_units, omit_pcs = AppSettingsManager.get_instance().get_stock_unit_options()
        sync_data = self.inventree_client.get_part_sync_data(part_pk, format_units=fmt_units, omit_pcs=omit_pcs)
        updates = self._apply_field_mappings(table_name, sync_data)
        if "IPN" in self.table_model.columns and linked_ipn and not updates.get("IPN"):
            updates["IPN"] = linked_ipn
        logger.info(f"InvenTree sync result for PK {part_pk} ({linked_ipn}): {updates}")

        if updates:
            self.table_model.update_record_in_model(row, updates)

        self._on_table_row_selected()
        summary_str = ", ".join(f"{k}={v}" for k, v in updates.items())
        self.statusBar().showMessage(f"Synced InvenTree: {summary_str or 'No mapped fields changed'}")

    def _find_row_index_by_id(self, row_id: int) -> int | None:
        """Find the source table_model row index for a given Access record ID."""
        for r, rec in enumerate(self.table_model.records):
            if rec.get("ID") == row_id:
                return r
        return None

    def _on_search_link_inventree(self) -> None:
        """Called by inspect panel 'Edit Link...' button."""
        self._on_edit_warehouse_link()

    def _on_edit_warehouse_link(
        self,
        rec: dict[str, Any] | None = None,
        current_it_part: dict[str, Any] | None = None,
    ) -> None:
        if rec is None:
            row = self._get_current_source_row()
            if row is None:
                QMessageBox.warning(self, "No Component Selected", "Please select a component from the table first.")
                return
            rec = self.table_model.get_record(row)

        if not rec:
            return

        table_name = self.table_model.current_table
        row_id = rec.get("ID")
        if not table_name or row_id is None:
            return

        initial_q = ""
        if current_it_part:
            initial_q = str(current_it_part.get("IPN") or current_it_part.get("name") or "").strip()
        if not initial_q:
            initial_q = str(rec.get("IPN") or rec.get("Part Number") or rec.get("Value") or "").strip()

        dialog = InvenTreeSearchDialog(self.inventree_client, initial_query=initial_q, parent=self)
        if dialog.exec():
            selected = dialog.get_selected_part()
            if selected:
                pk = selected.get("pk")
                ipn = str(selected.get("IPN") or selected.get("ipn") or "")
                name = str(selected.get("name") or ipn)
                logger.info(f"Linking Altium [{table_name}] ID={row_id} to InvenTree PK={pk} ({ipn})")

                # 1. Persist explicit link in link_manager
                self.link_manager.set_link(table_name, row_id, {
                    "pk": pk,
                    "IPN": ipn,
                    "name": name,
                })

                # 2. Fetch warehouse data and apply mapped fields
                fmt_units, omit_pcs = AppSettingsManager.get_instance().get_stock_unit_options()
                sync_data = self.inventree_client.get_part_sync_data(int(pk), format_units=fmt_units, omit_pcs=omit_pcs)
                updates = self._apply_field_mappings(table_name, sync_data)
                if "IPN" in self.table_model.columns and ipn:
                    updates["IPN"] = ipn
                if not rec.get("Part Number") and ipn:
                    updates["Part Number"] = ipn

                src_row = self._find_row_index_by_id(row_id)
                if src_row is not None and updates:
                    self.table_model.update_record_in_model(src_row, updates)

                # 3. Refresh warehouse split view if visible
                if hasattr(self, "warehouse_view") and not self.warehouse_view.isHidden():
                    self.warehouse_view.set_altium_context(
                        table_name,
                        self._get_displayed_altium_records(),
                    )

                # 4. Refresh selection & status
                self._on_table_row_selected()
                self.statusBar().showMessage(f"Linked component to InvenTree '{ipn}' (PK: {pk})")

    def _on_unlink_component(self, rec: dict[str, Any] | None = None) -> None:
        if rec is None:
            row = self._get_current_source_row()
            if row is None:
                QMessageBox.warning(self, "No Component Selected", "Please select a component to unlink.")
                return
            rec = self.table_model.get_record(row)

        if not rec:
            return

        table_name = self.table_model.current_table
        row_id = rec.get("ID")
        pn = rec.get("Part Number") or f"ID #{row_id}"
        if not table_name or row_id is None:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Unlink",
            f"Are you sure you want to remove the warehouse link for component '{pn}'?\n\n"
            f"This will clear its Stock and Location in Altium library and mark it as unlinked.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        logger.info(f"Unlinking component [{table_name}] ID={row_id} ('{pn}')")

        # 1. Mark as explicitly unlinked in link_manager
        self.link_manager.remove_link(table_name, row_id)

        # 2. Clear Stock, Location, and IPN in Access DB & Table Model
        updates: dict[str, Any] = {
            "Stock": None,
            "Location": "",
        }
        if "IPN" in self.table_model.columns:
            updates["IPN"] = ""
        src_row = self._find_row_index_by_id(row_id)
        if src_row is not None:
            self.table_model.update_record_in_model(src_row, updates)

        # 3. Refresh warehouse split view
        if hasattr(self, "warehouse_view") and not self.warehouse_view.isHidden():
            self.warehouse_view.set_altium_context(
                table_name,
                self._get_displayed_altium_records(),
            )

        # 4. Refresh selection & status
        self._on_table_row_selected()
        self.statusBar().showMessage(f"Unlinked component '{pn}' from warehouse.")

    def _on_unlink_selected_inventree(self) -> None:
        row = self._get_current_source_row()
        if row is None:
            QMessageBox.warning(self, "No Component Selected", "Please select a component to unlink.")
            return
        rec = self.table_model.get_record(row)
        if rec:
            self._on_unlink_component(rec)

    def _on_link_warehouse_part_to_selected_altium(self, it_part: dict[str, Any]) -> None:
        table_name = self.table_model.current_table
        if not table_name:
            QMessageBox.warning(self, "No Category Selected", "Please select a category table first.")
            return

        row = self._get_current_source_row()
        if row is None:
            QMessageBox.warning(
                self,
                "No Altium Component Selected",
                "Please select an Altium component row in the left table to link with this warehouse part.",
            )
            return

        rec = self.table_model.get_record(row)
        if not rec:
            return

        row_id = rec.get("ID")
        alt_pn = rec.get("Part Number") or f"ID #{row_id}"
        ipn = it_part.get("IPN") or it_part.get("name") or "Part"
        pk = it_part.get("pk")
        if not pk or row_id is None:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Link",
            f"Link Altium component '{alt_pn}' with InvenTree part '{ipn}' (PK: {pk})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        logger.info(f"Explicitly linking Altium [{table_name}] ID={row_id} ('{alt_pn}') -> InvenTree PK={pk} ('{ipn}')")

        # 1. Save link in link_manager
        self.link_manager.set_link(table_name, row_id, it_part)

        # 2. Get latest sync data and apply mapped fields
        fmt_units, omit_pcs = AppSettingsManager.get_instance().get_stock_unit_options()
        sync_data = self.inventree_client.get_part_sync_data(int(pk), format_units=fmt_units, omit_pcs=omit_pcs)
        updates = self._apply_field_mappings(table_name, sync_data)
        if "IPN" in self.table_model.columns and ipn:
            updates["IPN"] = ipn
        if updates:
            self.table_model.update_record_in_model(row, updates)

        # 3. Refresh warehouse split view
        if hasattr(self, "warehouse_view") and not self.warehouse_view.isHidden():
            self.warehouse_view.set_altium_context(
                table_name,
                self._get_displayed_altium_records(),
            )

        # 4. Refresh selection & status
        self._on_table_row_selected()
        self.statusBar().showMessage(f"Linked '{alt_pn}' to InvenTree '{ipn}'")

    def _on_restore_link_override(self, table_name: str, row_id: int) -> None:
        self.link_manager.clear_override(table_name, row_id)
        if hasattr(self, "warehouse_view") and not self.warehouse_view.isHidden():
            self.warehouse_view.set_altium_context(
                table_name,
                self._get_displayed_altium_records(),
            )
        self._on_table_row_selected()
        self.statusBar().showMessage("Cleared manual link override; returned to auto-matching.")

    def _show_altium_table_context_menu(self, pos) -> None:
        idx = self.table_view.indexAt(pos)
        if not idx.isValid():
            return

        source_idx = self.proxy_model.mapToSource(idx)
        if not source_idx.isValid():
            return

        row = source_idx.row()
        rec = self.table_model.get_record(row)
        if not rec:
            return

        table_name = self.table_model.current_table
        row_id = rec.get("ID")
        pn = rec.get("Part Number") or f"ID #{row_id}"

        menu = QMenu(self)

        act_edit = menu.addAction(AppIcons.link(), f"Edit InvenTree Link for '{pn}'...")
        act_edit.triggered.connect(lambda: self._on_edit_warehouse_link(rec))

        has_override = bool(table_name and row_id and self.link_manager.get_link(table_name, row_id))
        is_unlinked = bool(table_name and row_id and self.link_manager.is_explicitly_unlinked(table_name, row_id))
        has_stock_or_loc = bool(rec.get("Stock") is not None or rec.get("Location"))

        if not is_unlinked and (has_override or has_stock_or_loc):
            act_unlink = menu.addAction(AppIcons.delete(), f"Remove Link for '{pn}' (Unlink)")
            act_unlink.triggered.connect(lambda: self._on_unlink_component(rec))

        if has_override:
            act_clear = menu.addAction(AppIcons.refresh(), "Restore Default Auto-Match")
            act_clear.triggered.connect(lambda: self._on_restore_link_override(table_name, row_id))

        menu.addSeparator()

        act_sync = menu.addAction(AppIcons.sync_inventree(), "Sync InvenTree Status")
        act_sync.triggered.connect(self._on_sync_selected_inventree)

        menu.addSeparator()

        act_browse_sym = menu.addAction(AppIcons.edit(), "Browse Schematic Symbol...")
        act_browse_sym.triggered.connect(self._on_browse_symbol)

        fp_menu = menu.addMenu(AppIcons.browse_footprint(), "Assign PCB Footprint")

        fp1_val = rec.get("Footprint Ref")
        fp1_label = f"Footprint 1 (Primary): {fp1_val}" if fp1_val else "Footprint 1 (Primary)..."
        act_fp1 = fp_menu.addAction(fp1_label)
        act_fp1.triggered.connect(lambda: self._on_browse_footprint(1))

        fp2_val = rec.get("Footprint Ref 2")
        fp2_label = f"Footprint 2: {fp2_val}" if fp2_val else "Footprint 2..."
        act_fp2 = fp_menu.addAction(fp2_label)
        act_fp2.triggered.connect(lambda: self._on_browse_footprint(2))

        fp3_val = rec.get("Footprint Ref 3")
        fp3_label = f"Footprint 3: {fp3_val}" if fp3_val else "Footprint 3..."
        act_fp3 = fp_menu.addAction(fp3_label)
        act_fp3.triggered.connect(lambda: self._on_browse_footprint(3))

        if fp1_val or fp2_val or fp3_val:
            fp_menu.addSeparator()
        if fp1_val:
            act_clr_fp1 = fp_menu.addAction(AppIcons.delete(), f"Clear Footprint 1 ('{fp1_val}')")
            act_clr_fp1.triggered.connect(lambda: self._on_clear_footprint(1))
        if fp2_val:
            act_clr_fp2 = fp_menu.addAction(AppIcons.delete(), f"Clear Footprint 2 ('{fp2_val}')")
            act_clr_fp2.triggered.connect(lambda: self._on_clear_footprint(2))
        if fp3_val:
            act_clr_fp3 = fp_menu.addAction(AppIcons.delete(), f"Clear Footprint 3 ('{fp3_val}')")
            act_clr_fp3.triggered.connect(lambda: self._on_clear_footprint(3))

        menu.addSeparator()

        act_del = menu.addAction(AppIcons.delete(), "Delete Component")
        act_del.triggered.connect(self._on_delete_component)

        col_idx = source_idx.column()
        if table_name and 0 <= col_idx < len(self.table_model.columns):
            clicked_col = self.table_model.columns[col_idx]
            menu.addSeparator()
            cfg = EngineeringValueParser.get_column_config(table_name, clicked_col)
            unit_hint = f" ({cfg.get('default_unit', '')})" if cfg else ""
            act_col_unit = menu.addAction(
                AppIcons.unit_settings(),
                f"Configure Unit & Scale for '{clicked_col}'{unit_hint}...",
            )
            act_col_unit.triggered.connect(lambda: self._on_configure_column_unit(table_name, clicked_col))

        menu.exec(self.table_view.viewport().mapToGlobal(pos))

    def _on_bulk_sync_inventree(self) -> None:
        table_name = self.table_model.current_table
        if not table_name:
            QMessageBox.warning(self, "No Category Selected", "Please select a category table first.")
            return

        records = self.table_model.records
        if not records:
            QMessageBox.information(self, "Empty Table", "There are no components in this table to sync.")
            return

        logger.info(f"Starting bulk sync with InvenTree for table {table_name} ({len(records)} parts)")
        progress = QProgressDialog(f"Syncing {len(records)} components with InvenTree...", "Cancel", 0, len(records), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(200)

        fmt_units, omit_pcs = AppSettingsManager.get_instance().get_stock_unit_options()
        updates: list[tuple[int, dict[str, Any]]] = []
        synced_count = 0
        skipped_unlinked_count = 0

        for idx, rec in enumerate(records):
            if progress.wasCanceled():
                logger.info("Bulk sync canceled by user.")
                break
            progress.setValue(idx)
            row_id = rec.get("ID")
            if row_id is None:
                continue

            part_pk = None
            linked_ipn = ""
            link = self.link_manager.get_link(table_name, row_id)
            if link and not link.get("unlinked") and link.get("inventree_pk"):
                part_pk = int(link["inventree_pk"])
                linked_ipn = str(link.get("inventree_ipn") or "")
            elif rec.get("IPN"):
                db_ipn = str(rec.get("IPN") or "").strip()
                if db_ipn:
                    part = self.inventree_client.find_part_by_ipn(db_ipn)
                    if part:
                        part_pk = int(part["pk"])
                        linked_ipn = str(part.get("IPN") or db_ipn)
                        self.link_manager.set_link(table_name, row_id, part)

            if part_pk:
                sync_data = self.inventree_client.get_part_sync_data(part_pk, format_units=fmt_units, omit_pcs=omit_pcs)
                field_updates = self._apply_field_mappings(table_name, sync_data)
                if "IPN" in self.table_model.columns and linked_ipn and not field_updates.get("IPN"):
                    field_updates["IPN"] = linked_ipn
                if field_updates:
                    updates.append((row_id, field_updates))
                synced_count += 1
            else:
                skipped_unlinked_count += 1

        progress.setValue(len(records))

        if updates:
            self.db_manager.batch_update_mapped_records(table_name, updates)
            self.table_model.load_table(table_name)
            self._on_table_row_selected()

        logger.info(f"Bulk sync completed: {synced_count} updated, {skipped_unlinked_count} skipped (unlinked).")
        msg = (
            f"Bulk sync completed:\n"
            f"• {synced_count} components updated from InvenTree\n"
            f"• {skipped_unlinked_count} components skipped (not linked to warehouse)"
        )
        QMessageBox.information(self, "InvenTree Bulk Sync", msg)
        self.statusBar().showMessage(f"Bulk sync completed: {synced_count} updated, {skipped_unlinked_count} skipped")

    # ---------------- Column Layout Customization & Persistence ----------------
    def _get_column_layouts_file(self) -> Path:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return CACHE_DIR / "column_layouts.json"

    def _load_column_layouts(self) -> dict:
        f = self._get_column_layouts_file()
        if f.exists():
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    return json.load(fp)
            except Exception as e:
                logger.warning(f"Could not load column layouts: {e}")
        return {}

    def _save_column_layouts(self, data: dict) -> None:
        f = self._get_column_layouts_file()
        try:
            with open(f, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not save column layouts: {e}")

    def _save_current_table_column_layout(self) -> None:
        table_name = self.table_model.current_table
        if not table_name or not self.table_model.columns:
            return

        header = self.table_view.horizontalHeader()
        order = []
        widths = {}
        for visual_idx in range(header.count()):
            logical_idx = header.logicalIndex(visual_idx)
            if 0 <= logical_idx < len(self.table_model.columns):
                col_name = self.table_model.columns[logical_idx]
                order.append(col_name)
                widths[col_name] = header.sectionSize(logical_idx)

        layouts = self._load_column_layouts()
        layouts[table_name] = {"order": order, "widths": widths}
        self._save_column_layouts(layouts)
        logger.debug(f"Saved column layout for '{table_name}': {order}")

    def _get_header_title_min_width(self, col_name: str) -> int:
        """Calculate minimum width needed to fully display the header title without clipping."""
        header = self.table_view.horizontalHeader()
        font = header.font()
        font.setBold(True)
        fm = QFontMetrics(font)
        # Extra 36px provides padding on both sides and prevents truncation
        return max(fm.horizontalAdvance(col_name) + 36, 65)

    def _auto_fit_columns(self) -> None:
        """Fit all column widths based on header title text and cell contents."""
        header = self.table_view.horizontalHeader()
        header.blockSignals(True)
        try:
            for c_idx, col_name in enumerate(self.table_model.columns):
                h_min = self._get_header_title_min_width(col_name)
                c_w = self.table_view.sizeHintForColumn(c_idx)
                if "Path" in col_name:
                    c_w = min(c_w, 220)
                if col_name in ("Description", "Part Number"):
                    c_w = max(c_w, 150)
                ideal_w = max(h_min, c_w)
                header.resizeSection(c_idx, ideal_w)
        finally:
            header.blockSignals(False)

    def _restore_current_table_column_layout(self) -> bool:
        table_name = self.table_model.current_table
        if not table_name or not self.table_model.columns:
            return False

        layouts = self._load_column_layouts()
        table_layout = layouts.get(table_name)
        if not table_layout:
            return False

        header = self.table_view.horizontalHeader()
        header.blockSignals(True)
        try:
            # 1. Restore visual section order
            saved_order = table_layout.get("order", [])
            for target_visual, col_name in enumerate(saved_order):
                if col_name in self.table_model.columns:
                    logical_idx = self.table_model.columns.index(col_name)
                    current_visual = header.visualIndex(logical_idx)
                    if current_visual != target_visual:
                        header.moveSection(current_visual, target_visual)

            # 2. Restore column widths, ensuring each column is at least wide enough for its header title
            saved_widths = table_layout.get("widths", {})
            for logical_idx, col_name in enumerate(self.table_model.columns):
                w = saved_widths.get(col_name, 0)
                min_title_w = self._get_header_title_min_width(col_name)
                final_w = max(w, min_title_w)
                header.resizeSection(logical_idx, final_w)
        finally:
            header.blockSignals(False)
        return True

    def _reset_current_table_column_layout(self) -> None:
        table_name = self.table_model.current_table
        if not table_name:
            return

        layouts = self._load_column_layouts()
        if table_name in layouts:
            del layouts[table_name]
            self._save_column_layouts(layouts)

        header = self.table_view.horizontalHeader()
        header.blockSignals(True)
        try:
            for logical_idx in range(header.count()):
                current_visual = header.visualIndex(logical_idx)
                if current_visual != logical_idx:
                    header.moveSection(current_visual, logical_idx)
        finally:
            header.blockSignals(False)

        self._auto_fit_columns()
        self._save_current_table_column_layout()
        self.statusBar().showMessage("Column order and widths reset to defaults.")

    def _on_section_moved(self, logical_idx: int, old_visual: int, new_visual: int) -> None:
        self._save_current_table_column_layout()

    def _show_header_context_menu(self, pos) -> None:
        header = self.table_view.horizontalHeader()
        logical_idx = header.logicalIndexAt(pos)
        table_name = self.table_model.current_table
        col_name = ""
        if 0 <= logical_idx < len(self.table_model.columns):
            col_name = self.table_model.columns[logical_idx]

        menu = QMenu(self)

        # If user right-clicked a specific column
        if col_name and table_name:
            cfg = EngineeringValueParser.get_column_config(table_name, col_name)
            if cfg:
                unit_sym = cfg.get("default_unit", "")
                act_unit = menu.addAction(
                    AppIcons.unit_settings(),
                    f"Configure Unit & Scale for '{col_name}' ({unit_sym})...",
                )
                act_rm_unit = menu.addAction(
                    AppIcons.delete(),
                    f"Remove Unit from '{col_name}'",
                )
                act_rm_unit.triggered.connect(lambda: self._on_remove_column_unit(table_name, col_name))
            else:
                act_unit = menu.addAction(
                    AppIcons.unit_settings(),
                    f"Configure Unit & Scale for '{col_name}'...",
                )
            act_unit.triggered.connect(lambda: self._on_configure_column_unit(table_name, col_name))
            menu.addSeparator()

        act_fit = menu.addAction(AppIcons.table(), "Fit Columns to Header & Content")
        act_reset = menu.addAction(AppIcons.refresh(), "Reset Column Order & Widths")

        if table_name:
            menu.addSeparator()
            act_manage_schema = menu.addAction(AppIcons.edit(), f"Manage Columns / Schema for '{table_name}'...")
            act_manage_schema.triggered.connect(lambda: self._on_manage_table_schema(table_name))

        action = menu.exec(header.mapToGlobal(pos))
        if action == act_fit:
            self._auto_fit_columns()
            self._save_current_table_column_layout()
        elif action == act_reset:
            self._reset_current_table_column_layout()

    def _on_configure_column_unit(self, table_name: str, col_name: str) -> None:
        dialog = ColumnUnitConfigDialog(table_name=table_name, col_name=col_name, parent=self)
        if dialog.exec():
            cfg = EngineeringValueParser.get_column_config(table_name, col_name)
            if cfg:
                u = cfg.get("default_unit", "")
                self.statusBar().showMessage(f"Unit configured for '{col_name}': {u}")
            else:
                self.statusBar().showMessage(f"Unit removed/disabled for '{col_name}'.")

    def _on_remove_column_unit(self, table_name: str, col_name: str) -> None:
        ColumnUnitConfigManager.get_instance().disable_config(table_name, col_name)
        self.statusBar().showMessage(f"Removed unit & scale rules from '{col_name}'.")

    def closeEvent(self, event) -> None:
        try:
            self._save_current_table_column_layout()
        except Exception as exc:
            logger.error(f"Error saving column layouts on close: {exc}")
        super().closeEvent(event)

    # ----------------- Warehouse Split View Handlers -----------------
    def _sync_table_spacers(self, wh_rows: int | None = None) -> None:
        """Keep left Altium table row count and scroll range strictly matched with right warehouse table."""
        if not hasattr(self, "warehouse_view") or self.warehouse_view.isHidden():
            self.table_model.set_spacer_count(0)
            self.table_view.clearSpans()
            return

        if wh_rows is None:
            wh_rows = self.warehouse_view.table_model.rowCount()

        alt_displayed = len(self._get_displayed_altium_records())
        needed_spacers = max(0, wh_rows - alt_displayed)

        sep_title = ""
        if needed_spacers > 0:
            unlinked_count = max(0, needed_spacers - 1)
            sep_title = f"═══ End of Altium Components ({unlinked_count} unlinked warehouse parts below) ═══"

        self.table_model.set_spacer_count(needed_spacers, sep_title)

        # Clear and set separator span on Altium table if separator exists
        self.table_view.clearSpans()
        if needed_spacers > 0 and alt_displayed < self.proxy_model.rowCount():
            self.table_view.setSpan(alt_displayed, 0, 1, len(self.table_model.columns))

    def _on_toggle_warehouse_view(self, checked: bool) -> None:
        logger.info(f"Warehouse split view toggled: {checked}")
        self.warehouse_view.setVisible(checked)
        if checked:
            self.center_splitter.setSizes([550, 550])
            self.warehouse_view.set_altium_context(
                self.table_model.current_table,
                self._get_displayed_altium_records(),
            )
            self._sync_table_spacers()
            self.statusBar().showMessage("Warehouse split view enabled.")
        else:
            self._sync_table_spacers()
            self.statusBar().showMessage("Warehouse split view closed.")

    def _on_warehouse_part_inspected(self, part: dict[str, Any]) -> None:
        ipn = part.get("IPN") or "—"
        name = part.get("name") or "—"
        stock = part.get("total_in_stock")
        units = part.get("units") or ""
        loc = part.get("location_name") or "Unknown"
        fmt_units, omit_pcs = AppSettingsManager.get_instance().get_stock_unit_options()
        stock_str = format_stock_value(stock, units if fmt_units else None, omit_pcs=omit_pcs) or "0"
        self.lbl_it_details.setText(
            f"<b>Warehouse Part (IPN):</b> {ipn}<br>"
            f"<b>Name:</b> {name}<br>"
            f"<b>Stock:</b> <span style='color: #40ff80; font-weight: bold;'>{stock_str}</span><br>"
            f"<b>Location:</b> <span style='color: #4da6ff; font-weight: bold;'>{loc}</span>"
        )

    def _on_focus_altium_row(self, altium_idx: int) -> None:
        if 0 <= altium_idx < self.proxy_model.rowCount():
            self.table_view.selectRow(altium_idx)
            proxy_idx = self.proxy_model.index(altium_idx, 0)
            if proxy_idx.isValid():
                self.table_view.scrollTo(proxy_idx)

    def _on_create_component_from_warehouse(self, part: dict[str, Any]) -> None:
        table_name = self.table_model.current_table
        if not table_name:
            QMessageBox.warning(self, "No Category Selected", "Please select an Altium category table first.")
            return

        ipn = str(part.get("IPN") or "").strip()
        name = str(part.get("name") or "").strip()
        it_pk = part.get("pk")
        logger.info(f"Creating Altium component from warehouse part: IPN={ipn}, Name={name} in table {table_name}")

        fmt_units, omit_pcs = AppSettingsManager.get_instance().get_stock_unit_options()
        sync_data = self.inventree_client.get_part_sync_data(int(it_pk), format_units=fmt_units, omit_pcs=omit_pcs) if it_pk else part

        mapped_fields = self._apply_field_mappings(table_name, sync_data)
        data: dict[str, Any] = {
            "Description": name,
        }
        if "IPN" in self.table_model.columns and ipn:
            data["IPN"] = ipn
        data.update(mapped_fields)

        if table_name == "Resistor":
            # 1. Package detection
            pkg_detected = None
            for pkg in ["0402", "0603", "0805", "1206", "1210", "2012", "2512"]:
                if pkg in ipn or pkg in name:
                    pkg_detected = pkg
                    break
            data["Package"] = pkg_detected or "0805"

            # 2. Value detection
            val_found = None
            vm = re.search(r"(\d+(?:\.\d+)?\s*[kKMmGgµuUnNpfF]?\s*(?:[ΩΩ]|ohm|ohms))", name, re.IGNORECASE)
            if vm:
                p_res = EngineeringValueParser.parse(vm.group(1), default_unit="Ω")
                if p_res["valid"]:
                    val_found = p_res["formatted"]

            if not val_found:
                tokens = ipn.split("-")
                raw_val = tokens[2] if len(tokens) >= 3 and tokens[0].upper() == "R" else ipn
                # Convert shorthand e.g. 1R5K -> 1.5k, 100R -> 100
                m_sh = re.match(r"^(\d+)[rR](\d+)([kKmM])?$", raw_val)
                if m_sh:
                    raw_val = f"{m_sh.group(1)}.{m_sh.group(2)}{m_sh.group(3) or ''}"
                p_res = EngineeringValueParser.parse(raw_val, default_unit="Ω")
                if p_res["valid"]:
                    val_found = p_res["formatted"]
                else:
                    val_found = raw_val

            data["Value"] = val_found or "10kΩ"

            # 3. Tolerance detection
            tol_found = None
            tm = re.search(r"([±\s]?\d+(?:\.\d+)?%)", name)
            if tm:
                tol_raw = tm.group(1).replace("±", "").strip()
                tol_found = tol_raw
            elif len(ipn.split("-")) > 3:
                tol_found = ipn.split("-")[3]
            data["Tolerance"] = tol_found or "1%"

            # 4. Power detection
            for pwr in ["1/16 W", "1/10 W", "1/8 W", "1/4 W", "1/2 W", "1 W", "2 W", "5 W", "10 W"]:
                if pwr.replace(" ", "").lower() in name.replace(" ", "").lower():
                    data["Power"] = pwr
                    break
        else:
            data["Part Number"] = ipn

        # 5. Auto-populate Symbol and Footprint from existing table records
        for r in self.table_model.records:
            if not data.get("Library Ref") and r.get("Library Ref"):
                data["Library Ref"] = r.get("Library Ref")
                data["Library Path"] = r.get("Library Path")
            if data.get("Package") and r.get("Package") == data.get("Package"):
                if not data.get("Footprint Ref") and r.get("Footprint Ref"):
                    data["Footprint Ref"] = r.get("Footprint Ref")
                    data["Footprint Path"] = r.get("Footprint Path")
                    if r.get("Footprint Ref 2"):
                        data["Footprint Ref 2"] = r.get("Footprint Ref 2")
                        data["Footprint Path 2"] = r.get("Footprint Path 2")
                    if r.get("Footprint Ref 3"):
                        data["Footprint Ref 3"] = r.get("Footprint Ref 3")
                        data["Footprint Path 3"] = r.get("Footprint Path 3")
                    break

        try:
            new_id = self.db_manager.insert_record(table_name, data)

            # Explicitly link the newly created Altium component to the warehouse part
            it_pk = part.get("pk")
            if it_pk:
                self.link_manager.set_link(table_name, new_id, it_pk, ipn, name)
                logger.info(f"Explicitly linked new {table_name}:{new_id} to InvenTree PK {it_pk} ({ipn})")

            self.table_model.load_table(table_name)
            count = len(self.table_model.records)
            self.lbl_record_count.setText(f"{count} component{'s' if count != 1 else ''}")

            # Update warehouse alignment view
            if hasattr(self, "warehouse_view") and not self.warehouse_view.isHidden():
                self.warehouse_view.set_altium_context(
                    table_name,
                    self._get_displayed_altium_records(),
                )

            # Focus newly created row in Altium table
            for r in range(len(self.table_model.records)):
                if self.table_model.records[r].get("ID") == new_id:
                    src_idx = self.table_model.index(r, 1)
                    proxy_idx = self.proxy_model.mapFromSource(src_idx)
                    self.table_view.selectRow(proxy_idx.row())
                    self.table_view.scrollTo(proxy_idx)
                    break

            self.statusBar().showMessage(f"Created & linked component '{ipn}' in table '{table_name}'")
            QMessageBox.information(
                self,
                "Component Created & Linked",
                f"Component '{ipn}' was successfully created in Altium table '{table_name}' and linked with warehouse inventory!\n\n"
                f"Stock: {data.get('Stock', '—')}\nLocation: {data.get('Location', '—')}",
            )
        except Exception as exc:
            logger.error(f"Failed to create component from warehouse: {exc}", exc_info=True)
            QMessageBox.critical(self, "Error Creating Component", f"Failed to insert component:\n{exc}")
