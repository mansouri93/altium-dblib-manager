# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
    QMessageBox,
    QFrame,
    QApplication,
    QTabWidget,
    QFileDialog,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
    QComboBox,
)
from ..config import (
    get_db_path,
    get_symbols_dir,
    get_footprints_dir,
    save_app_settings,
    to_absolute_path,
    BASE_DIR,
    AppSettingsManager,
    DEFAULT_FIELD_MAPPINGS,
    get_current_theme,
    save_current_theme,
)
from .styles import get_available_themes, get_theme_palette, apply_theme
from ..db.access_manager import AccessDBManager
from ..inventree.client import InvenTreeClient
from .icons import AppIcons
from .smooth_scroll import enable_smooth_scroll

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """
    Comprehensive settings dialog for configuring:
    - Microsoft Access Database file (.accdb / .mdb)
    - Altium Schematic Symbols root directory (.SchLib)
    - Altium PCB Footprints root directory (.PcbLib)
    - InvenTree server connection URL, credentials, and API token
    """

    def __init__(
        self,
        inventree_client: InvenTreeClient,
        db_manager: AccessDBManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.it_client = inventree_client
        self.db_manager = db_manager

        self.initial_db_path = get_db_path()
        self.initial_symbols_dir = get_symbols_dir()
        self.initial_footprints_dir = get_footprints_dir()

        self.db_changed = False
        self.libraries_changed = False
        self.inventree_changed = False
        self.mappings_changed = False

        self.setWindowTitle("Application Settings")
        self.resize(710, 560)
        self.setMinimumSize(600, 500)

        self.theme_changed = False
        self._initial_theme = get_current_theme()
        self.new_theme = self._initial_theme
        self._apply_dialog_theme(self.new_theme)

        self._init_ui()
        self._load_values()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Header banner
        header_layout = QHBoxLayout()
        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(AppIcons.settings("#58a6ff").pixmap(30, 30))
        header_layout.addWidget(icon_lbl)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        lbl_title = QLabel("Application Settings", self)
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #58a6ff;")
        lbl_desc = QLabel(
            "Configure database source, Altium library directories, and InvenTree warehouse connection.",
            self,
        )
        lbl_desc.setStyleSheet("font-size: 11.5px; color: #8f8fa8;")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_desc)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Tab Widget
        self.tabs = QTabWidget(self)

        # Tab 1: Database & Altium Libraries
        tab_db_libs = QWidget()
        self._init_db_libs_tab(tab_db_libs)
        self.tabs.addTab(tab_db_libs, AppIcons.database(), "Database && Libraries")

        # Tab 2: InvenTree Warehouse Connection
        tab_inventree = QWidget()
        self._init_inventree_tab(tab_inventree)
        self.tabs.addTab(tab_inventree, AppIcons.server(), "InvenTree Connection")

        # Tab 3: InvenTree Field Mapping
        tab_mapping = QWidget()
        self._init_field_mapping_tab(tab_mapping)
        self.tabs.addTab(tab_mapping, AppIcons.link(), "Field Mapping")

        # Tab 4: Appearance & Themes
        tab_appearance = QWidget()
        self._init_appearance_tab(tab_appearance)
        self.tabs.addTab(tab_appearance, AppIcons.palette(), "Appearance")

        main_layout.addWidget(self.tabs, stretch=1)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton(" Save && Apply", self)
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setIcon(AppIcons.check())
        self.btn_save.clicked.connect(self._on_save_clicked)
        btn_layout.addWidget(self.btn_save)

        main_layout.addLayout(btn_layout)

    # ---------------- Tab 1: Database & Altium Libraries ----------------
    def _init_db_libs_tab(self, tab: QWidget) -> None:
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        # 1. Access Database Selection
        box_db = QGroupBox("Microsoft Access Database (.accdb / .mdb)", tab)
        box_db_layout = QVBoxLayout(box_db)
        box_db_layout.setSpacing(6)

        lbl_db_path = QLabel("Database File Path:", box_db)
        box_db_layout.addWidget(lbl_db_path)

        db_row = QHBoxLayout()
        self.txt_db_path = QLineEdit(box_db)
        self.txt_db_path.setPlaceholderText("Path to .accdb or .mdb file...")
        self.txt_db_path.textChanged.connect(self._update_db_info)
        db_row.addWidget(self.txt_db_path, stretch=1)

        btn_browse_db = QPushButton(" Browse...", box_db)
        btn_browse_db.setIcon(AppIcons.folder_open())
        btn_browse_db.clicked.connect(self._on_browse_db)
        db_row.addWidget(btn_browse_db)

        btn_create_db = QPushButton(" + New Database...", box_db)
        btn_create_db.setIcon(AppIcons.add())
        btn_create_db.clicked.connect(self._on_create_new_db)
        db_row.addWidget(btn_create_db)
        box_db_layout.addLayout(db_row)

        db_status_row = QHBoxLayout()
        self.btn_test_db = QPushButton(" Test DB Connection", box_db)
        self.btn_test_db.setIcon(AppIcons.database())
        self.btn_test_db.clicked.connect(self._on_test_db_connection)
        db_status_row.addWidget(self.btn_test_db)

        self.lbl_db_status = QLabel("", box_db)
        self.lbl_db_status.setStyleSheet("font-size: 11.5px;")
        db_status_row.addWidget(self.lbl_db_status, stretch=1)
        box_db_layout.addLayout(db_status_row)

        layout.addWidget(box_db)

        # 2. Schematic Symbols Directory Selection
        box_sym = QGroupBox("Schematic Symbols Root Directory (.SchLib)", tab)
        box_sym_layout = QVBoxLayout(box_sym)
        box_sym_layout.setSpacing(6)

        sym_row = QHBoxLayout()
        self.txt_symbols_dir = QLineEdit(box_sym)
        self.txt_symbols_dir.setPlaceholderText("Path to symbols folder...")
        self.txt_symbols_dir.textChanged.connect(self._update_symbols_info)
        sym_row.addWidget(self.txt_symbols_dir, stretch=1)

        btn_browse_sym = QPushButton(" Browse...", box_sym)
        btn_browse_sym.setIcon(AppIcons.folder_open())
        btn_browse_sym.clicked.connect(self._on_browse_symbols_dir)
        sym_row.addWidget(btn_browse_sym)
        box_sym_layout.addLayout(sym_row)

        self.lbl_symbols_info = QLabel("", box_sym)
        self.lbl_symbols_info.setStyleSheet("font-size: 11px; color: #8888aa;")
        box_sym_layout.addWidget(self.lbl_symbols_info)

        layout.addWidget(box_sym)

        # 3. PCB Footprints Directory Selection
        box_fp = QGroupBox("PCB Footprints Root Directory (.PcbLib)", tab)
        box_fp_layout = QVBoxLayout(box_fp)
        box_fp_layout.setSpacing(6)

        fp_row = QHBoxLayout()
        self.txt_footprints_dir = QLineEdit(box_fp)
        self.txt_footprints_dir.setPlaceholderText("Path to footprints folder...")
        self.txt_footprints_dir.textChanged.connect(self._update_footprints_info)
        fp_row.addWidget(self.txt_footprints_dir, stretch=1)

        btn_browse_fp = QPushButton(" Browse...", box_fp)
        btn_browse_fp.setIcon(AppIcons.folder_open())
        btn_browse_fp.clicked.connect(self._on_browse_footprints_dir)
        fp_row.addWidget(btn_browse_fp)
        box_fp_layout.addLayout(fp_row)

        self.lbl_footprints_info = QLabel("", box_fp)
        self.lbl_footprints_info.setStyleSheet("font-size: 11px; color: #8888aa;")
        box_fp_layout.addWidget(self.lbl_footprints_info)

        layout.addWidget(box_fp)
        layout.addStretch()

    # ---------------- Tab 2: InvenTree Connection ----------------
    def _init_inventree_tab(self, tab: QWidget) -> None:
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # Base URL
        lbl_url = QLabel("Server Base URL:", tab)
        lbl_url.setStyleSheet("font-weight: 500;")
        self.txt_it_url = QLineEdit(tab)
        self.txt_it_url.setPlaceholderText("e.g. http://inventree.localhost:8180")
        layout.addWidget(lbl_url)
        layout.addWidget(self.txt_it_url)

        # Username
        lbl_user = QLabel("Username:", tab)
        lbl_user.setStyleSheet("font-weight: 500;")
        self.txt_it_user = QLineEdit(tab)
        self.txt_it_user.setPlaceholderText("e.g. admin")
        layout.addWidget(lbl_user)
        layout.addWidget(self.txt_it_user)

        # Password
        lbl_pwd = QLabel("Password:", tab)
        lbl_pwd.setStyleSheet("font-weight: 500;")
        pwd_layout = QHBoxLayout()
        self.txt_it_pwd = QLineEdit(tab)
        self.txt_it_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_it_pwd.setPlaceholderText("Password")
        pwd_layout.addWidget(self.txt_it_pwd)

        self.btn_toggle_pwd = QPushButton("Show", tab)
        self.btn_toggle_pwd.setFixedWidth(55)
        self.btn_toggle_pwd.clicked.connect(self._toggle_password_visibility)
        pwd_layout.addWidget(self.btn_toggle_pwd)

        layout.addWidget(lbl_pwd)
        layout.addLayout(pwd_layout)

        # API Token
        lbl_token = QLabel("API Token (Optional):", tab)
        lbl_token.setStyleSheet("font-weight: 500;")
        lbl_token_hint = QLabel("Leave empty to automatically authenticate with username & password.", tab)
        lbl_token_hint.setStyleSheet("font-size: 11px; color: #7f7f98;")
        self.txt_it_token = QLineEdit(tab)
        self.txt_it_token.setPlaceholderText("Optional token string...")
        layout.addWidget(lbl_token)
        layout.addWidget(lbl_token_hint)
        layout.addWidget(self.txt_it_token)

        # Test Connection Row
        test_layout = QHBoxLayout()
        self.btn_test_it = QPushButton(" Test Connection", tab)
        self.btn_test_it.setIcon(AppIcons.sync_inventree())
        self.btn_test_it.clicked.connect(self._on_test_inventree_connection)
        test_layout.addWidget(self.btn_test_it)

        self.lbl_it_test_status = QLabel("", tab)
        self.lbl_it_test_status.setStyleSheet("font-size: 11.5px;")
        test_layout.addWidget(self.lbl_it_test_status, stretch=1)
        layout.addLayout(test_layout)

        layout.addStretch()

    # ---------------- Tab 3: Field Mapping ----------------
    def _init_field_mapping_tab(self, tab: QWidget) -> None:
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header note
        lbl_hint = QLabel(
            "Configure which InvenTree parameters and part attributes sync to Altium database columns.<br>"
            "<span style='color: #79c0ff;'>Note:</span> Parameters are only synced if the target column exists in the active database table.",
            tab,
        )
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet("font-size: 11.5px; color: #a0a0c0; line-height: 1.4;")
        layout.addWidget(lbl_hint)

        # Unit Formatting Options Box
        grp_opts = QGroupBox("Stock Unit Formatting", tab)
        opts_layout = QVBoxLayout(grp_opts)
        opts_layout.setContentsMargins(12, 10, 12, 10)
        opts_layout.setSpacing(6)

        self.chk_format_stock_units = QCheckBox("Format Stock with InvenTree units and decimals (e.g., 2.5m, 10m)", grp_opts)
        self.chk_format_stock_units.setStyleSheet("color: #e0e0f0; font-size: 12px;")
        opts_layout.addWidget(self.chk_format_stock_units)

        self.chk_omit_pcs = QCheckBox("Omit generic piece units ('pcs', 'pc') in Stock values (e.g., 125 instead of 125pcs)", grp_opts)
        self.chk_omit_pcs.setStyleSheet("color: #e0e0f0; font-size: 12px;")
        opts_layout.addWidget(self.chk_omit_pcs)

        layout.addWidget(grp_opts)

        # Table of mappings
        self.tbl_mappings = QTableWidget(tab)
        self.tbl_mappings.setColumnCount(3)
        self.tbl_mappings.setHorizontalHeaderLabels(["Sync?", "InvenTree Parameter / Field", "Altium DB Column"])
        self.tbl_mappings.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_mappings.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_mappings.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_mappings.verticalHeader().setVisible(False)
        self.tbl_mappings.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        enable_smooth_scroll(self.tbl_mappings, step_v=35, step_h=50)
        layout.addWidget(self.tbl_mappings, stretch=1)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_add_mapping = QPushButton(" + Add Mapping", tab)
        self.btn_add_mapping.clicked.connect(self._on_add_mapping_row)
        btn_layout.addWidget(self.btn_add_mapping)

        self.btn_del_mapping = QPushButton(" - Remove Selected", tab)
        self.btn_del_mapping.clicked.connect(self._on_remove_mapping_row)
        btn_layout.addWidget(self.btn_del_mapping)

        btn_layout.addStretch()

        self.btn_reset_mapping = QPushButton(" Reset Defaults", tab)
        self.btn_reset_mapping.clicked.connect(self._on_reset_mappings)
        btn_layout.addWidget(self.btn_reset_mapping)

        layout.addLayout(btn_layout)

    def _get_inventree_field_choices(self) -> list[str]:
        standard = [
            "total_in_stock",
            "location_name",
            "description",
            "name",
            "IPN",
            "link",
            "keywords",
            "units",
            "notes",
            "revision",
            "minimum_stock",
            "maximum_stock",
        ]
        try:
            custom_templates = self.it_client.get_part_parameter_templates()
            for t in custom_templates:
                if t not in standard:
                    standard.append(t)
        except Exception:
            pass
        return standard

    def _get_altium_col_choices(self) -> list[str]:
        standard = [
            "Stock",
            "Location",
            "Description",
            "Value",
            "Tolerance",
            "Power",
            "Package",
            "Manufacturer",
            "Manufacturer Part Number",
            "ComponentLink1URL",
            "Keywords",
            "Comment",
        ]
        if self.db_manager:
            try:
                tables = self.db_manager.list_tables()
                for t in tables:
                    for c in self.db_manager.get_columns(t):
                        if c not in standard and c != "ID":
                            standard.append(c)
            except Exception:
                pass
        return standard

    def _populate_mapping_table(self, mappings: list[dict[str, Any]]) -> None:
        self.tbl_mappings.setRowCount(0)
        it_choices = self._get_inventree_field_choices()
        db_choices = self._get_altium_col_choices()

        for m in mappings:
            self._add_mapping_row_widget(
                enabled=m.get("enabled", True),
                it_field=m.get("inventree_field", ""),
                db_col=m.get("db_column", ""),
                it_choices=it_choices,
                db_choices=db_choices,
            )

    def _add_mapping_row_widget(
        self,
        enabled: bool = True,
        it_field: str = "",
        db_col: str = "",
        it_choices: list[str] | None = None,
        db_choices: list[str] | None = None,
    ) -> None:
        if it_choices is None:
            it_choices = self._get_inventree_field_choices()
        if db_choices is None:
            db_choices = self._get_altium_col_choices()

        row = self.tbl_mappings.rowCount()
        self.tbl_mappings.insertRow(row)

        chk_container = QWidget()
        chk_layout = QHBoxLayout(chk_container)
        chk_layout.setContentsMargins(6, 2, 6, 2)
        chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chk = QCheckBox(chk_container)
        chk.setChecked(enabled)
        chk_layout.addWidget(chk)
        self.tbl_mappings.setCellWidget(row, 0, chk_container)

        cb_it = QComboBox()
        cb_it.setEditable(True)
        cb_it.addItems(it_choices)
        if it_field:
            idx = cb_it.findText(it_field)
            if idx >= 0:
                cb_it.setCurrentIndex(idx)
            else:
                cb_it.addItem(it_field)
                cb_it.setCurrentText(it_field)
        self.tbl_mappings.setCellWidget(row, 1, cb_it)

        cb_db = QComboBox()
        cb_db.setEditable(True)
        cb_db.addItems(db_choices)
        if db_col:
            idx = cb_db.findText(db_col)
            if idx >= 0:
                cb_db.setCurrentIndex(idx)
            else:
                cb_db.addItem(db_col)
                cb_db.setCurrentText(db_col)
        self.tbl_mappings.setCellWidget(row, 2, cb_db)

    def _on_add_mapping_row(self) -> None:
        self._add_mapping_row_widget(enabled=True, it_field="description", db_col="Description")

    def _on_remove_mapping_row(self) -> None:
        row = self.tbl_mappings.currentRow()
        if row >= 0:
            self.tbl_mappings.removeRow(row)
        elif self.tbl_mappings.rowCount() > 0:
            self.tbl_mappings.removeRow(self.tbl_mappings.rowCount() - 1)

    def _on_reset_mappings(self) -> None:
        self._populate_mapping_table(DEFAULT_FIELD_MAPPINGS)
        self.chk_format_stock_units.setChecked(True)
        self.chk_omit_pcs.setChecked(True)

    def _get_mappings_from_table(self) -> list[dict[str, Any]]:
        mappings = []
        for r in range(self.tbl_mappings.rowCount()):
            chk_container = self.tbl_mappings.cellWidget(r, 0)
            chk = chk_container.findChild(QCheckBox) if chk_container else None
            enabled = chk.isChecked() if chk else True

            cb_it = self.tbl_mappings.cellWidget(r, 1)
            cb_db = self.tbl_mappings.cellWidget(r, 2)

            it_val = cb_it.currentText().strip() if cb_it else ""
            db_val = cb_db.currentText().strip() if cb_db else ""

            if it_val and db_val:
                mappings.append({
                    "enabled": enabled,
                    "inventree_field": it_val,
                    "db_column": db_val,
                })
        return mappings

    # ---------------- Tab 4: Appearance & Themes ----------------
    def _init_appearance_tab(self, tab: QWidget) -> None:
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        box_theme = QGroupBox("Application Theme && Appearance", tab)
        box_layout = QVBoxLayout(box_theme)
        box_layout.setContentsMargins(14, 16, 14, 14)
        box_layout.setSpacing(12)

        # Theme selector row
        row_sel = QHBoxLayout()
        lbl_sel = QLabel("Active Theme:", box_theme)
        lbl_sel.setStyleSheet("font-weight: bold; font-size: 12.5px;")
        row_sel.addWidget(lbl_sel)

        self.combo_theme = QComboBox(box_theme)
        self.combo_theme.setFixedHeight(30)
        themes = get_available_themes()
        cur_idx = 0
        for i, t in enumerate(themes):
            self.combo_theme.addItem(t["name"], t["id"])
            if t["id"] == self.new_theme:
                cur_idx = i
        self.combo_theme.setCurrentIndex(cur_idx)
        self.combo_theme.currentIndexChanged.connect(self._on_theme_selection_changed)
        row_sel.addWidget(self.combo_theme, 1)
        box_layout.addLayout(row_sel)

        # Theme description
        self.lbl_theme_desc = QLabel(box_theme)
        self.lbl_theme_desc.setWordWrap(True)
        self.lbl_theme_desc.setStyleSheet("color: #8f8fa8; font-size: 11.5px; padding: 2px 0;")
        box_layout.addWidget(self.lbl_theme_desc)

        # Swatch palette preview
        lbl_palette = QLabel("Palette Preview:", box_theme)
        lbl_palette.setStyleSheet("font-size: 11.5px; font-weight: bold; color: #a0a0c0; margin-top: 4px;")
        box_layout.addWidget(lbl_palette)

        swatch_frame = QFrame(box_theme)
        swatch_frame.setObjectName("CardFrame")
        swatch_layout = QHBoxLayout(swatch_frame)
        swatch_layout.setContentsMargins(10, 10, 10, 10)
        swatch_layout.setSpacing(12)

        self.swatch_boxes = []
        for title in ["Window", "Surface", "Accent", "Highlight"]:
            box = QFrame(swatch_frame)
            box.setFixedSize(85, 42)
            b_layout = QVBoxLayout(box)
            b_layout.setContentsMargins(4, 4, 4, 4)
            b_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t_lbl = QLabel(title, box)
            t_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b_layout.addWidget(t_lbl)
            swatch_layout.addWidget(box)
            self.swatch_boxes.append((box, t_lbl))

        swatch_layout.addStretch()
        box_layout.addWidget(swatch_frame)

        # Live preview checkbox
        self.chk_live_preview = QCheckBox("Live preview theme immediately across application", box_theme)
        self.chk_live_preview.setChecked(True)
        box_layout.addWidget(self.chk_live_preview)

        layout.addWidget(box_theme)
        layout.addStretch()

        self._update_theme_preview(self.new_theme)

    def _on_theme_selection_changed(self, idx: int) -> None:
        theme_id = self.combo_theme.itemData(idx)
        self.new_theme = str(theme_id)
        self._update_theme_preview(self.new_theme)
        if getattr(self, "chk_live_preview", None) and self.chk_live_preview.isChecked():
            apply_theme(self.new_theme)
            self._apply_dialog_theme(self.new_theme)

    def _update_theme_preview(self, theme_id: str) -> None:
        pal = get_theme_palette(theme_id)
        if hasattr(self, "lbl_theme_desc"):
            self.lbl_theme_desc.setText(pal.get("desc", ""))
        if hasattr(self, "swatch_boxes"):
            colors = pal.get("swatch", ["#222", "#333", "#444", "#555"])
            border_c = pal.get("border_color", "#444")
            for i, col in enumerate(colors):
                if i < len(self.swatch_boxes):
                    box, t_lbl = self.swatch_boxes[i]
                    is_light = (pal.get("is_dark", True) is False) and i < 2
                    txt_col = "#0f172a" if is_light else "#ffffff"
                    box.setStyleSheet(f"background-color: {col}; border-radius: 6px; border: 1.5px solid {border_c};")
                    t_lbl.setStyleSheet(f"font-size: 10.5px; font-weight: bold; color: {txt_col}; background: transparent;")

    def _apply_dialog_theme(self, theme_id: str | None = None) -> None:
        pal = get_theme_palette(theme_id or getattr(self, "new_theme", "dark_modern"))
        qss = f"""
            QDialog {{
                background-color: {pal.get('bg_window')};
                color: {pal.get('text_primary')};
            }}
            QLabel {{
                color: {pal.get('text_primary')};
                font-size: 12px;
            }}
            QLineEdit {{
                background-color: {pal.get('bg_surface')};
                border: 1px solid {pal.get('border_color')};
                border-radius: 4px;
                padding: 4px 8px;
                min-height: 20px;
                color: {pal.get('text_primary')};
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {pal.get('accent_light')};
                background-color: {pal.get('bg_input')};
            }}
            QPushButton {{
                background-color: {pal.get('btn_bg')};
                color: {pal.get('text_primary')};
                border: 1px solid {pal.get('border_color')};
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {pal.get('btn_hover')};
                border-color: {pal.get('accent_light')};
                color: {pal.get('text_primary')};
            }}
            QPushButton#PrimaryButton {{
                background-color: {pal.get('accent_color')};
                border: 1px solid {pal.get('accent_light')};
                color: #ffffff;
                font-weight: bold;
            }}
            QPushButton#PrimaryButton:hover {{
                background-color: {pal.get('accent_hover')};
            }}
            QTabWidget::pane {{
                border: 1px solid {pal.get('border_color')};
                background-color: {pal.get('bg_card')};
                border-radius: 6px;
                top: -1px;
            }}
            QTabBar::tab {{
                background-color: {pal.get('bg_window')};
                color: {pal.get('text_secondary')};
                padding: 8px 14px;
                margin-right: 3px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                border: 1px solid {pal.get('border_color')};
                border-bottom: none;
                font-size: 12px;
                font-weight: 500;
            }}
            QTabBar::tab:selected {{
                background-color: {pal.get('bg_card')};
                color: {pal.get('accent_light')};
                border: 1px solid {pal.get('border_color')};
                border-bottom: 1px solid {pal.get('bg_card')};
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {pal.get('btn_hover')};
                color: {pal.get('text_primary')};
            }}
            QGroupBox {{
                border: 1px solid {pal.get('border_color')};
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 12px;
                font-weight: bold;
                font-size: 12px;
                color: {pal.get('text_secondary')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: {pal.get('accent_light')};
            }}
            QTableWidget {{
                background-color: {pal.get('bg_surface')};
                gridline-color: {pal.get('table_grid')};
                border: 1px solid {pal.get('border_color')};
                border-radius: 4px;
                color: {pal.get('text_primary')};
            }}
            QHeaderView::section {{
                background-color: {pal.get('header_bg_start')};
                color: {pal.get('text_secondary')};
                font-weight: bold;
                font-size: 11.5px;
                padding: 5px;
                border: 1px solid {pal.get('border_color')};
            }}
            QComboBox {{
                background-color: {pal.get('bg_surface')};
                border: 1px solid {pal.get('border_color')};
                border-radius: 4px;
                padding: 2px 6px;
                color: {pal.get('text_primary')};
                font-size: 12px;
            }}
            QComboBox:focus {{
                border-color: {pal.get('accent_light')};
            }}
            QComboBox QAbstractItemView {{
                background-color: {pal.get('bg_card')};
                color: {pal.get('text_primary')};
                selection-background-color: {pal.get('selection_bg')};
                selection-color: {pal.get('selection_text')};
                border: 1px solid {pal.get('border_color')};
            }}
        """
        self.setStyleSheet(qss)

    def reject(self) -> None:
        # Revert theme if user previewed another theme but cancelled
        if getattr(self, "new_theme", None) != getattr(self, "_initial_theme", None):
            apply_theme(self._initial_theme)
            self._apply_dialog_theme(self._initial_theme)
        super().reject()

    # ---------------- Value Loading & Updating ----------------
    def _load_values(self) -> None:
        # Altium & DB values
        self.txt_db_path.setText(str(self.initial_db_path))
        self.txt_symbols_dir.setText(str(self.initial_symbols_dir))
        self.txt_footprints_dir.setText(str(self.initial_footprints_dir))

        # InvenTree values
        conn = getattr(self.it_client, "conn", None)
        if conn:
            self.txt_it_url.setText(conn.base_url or "")
            self.txt_it_user.setText(conn.username or "")
            self.txt_it_pwd.setText(conn.password or "")
            self.txt_it_token.setText(conn.api_token or "")

        self._update_symbols_info()
        self._update_footprints_info()

        # Field mapping values
        fmt_units, omit_pcs = AppSettingsManager.get_instance().get_stock_unit_options()
        self.chk_format_stock_units.setChecked(fmt_units)
        self.chk_omit_pcs.setChecked(omit_pcs)
        mappings = AppSettingsManager.get_instance().get_field_mappings()
        self._populate_mapping_table(mappings)

    def _toggle_password_visibility(self) -> None:
        if self.txt_it_pwd.echoMode() == QLineEdit.EchoMode.Password:
            self.txt_it_pwd.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_pwd.setText("Hide")
        else:
            self.txt_it_pwd.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_pwd.setText("Show")

    def _update_db_info(self) -> None:
        self.lbl_db_status.setText("")

    def _update_symbols_info(self) -> None:
        p = Path(self.txt_symbols_dir.text().strip())
        if p.exists() and p.is_dir():
            count = len(list(p.rglob("*.SchLib")) + list(p.rglob("*.schlib")))
            self.lbl_symbols_info.setText(f"✓ Valid directory ({count} .SchLib files detected)")
            self.lbl_symbols_info.setStyleSheet("font-size: 11px; color: #40ff80;")
        else:
            self.lbl_symbols_info.setText("✕ Directory does not exist")
            self.lbl_symbols_info.setStyleSheet("font-size: 11px; color: #ff6666;")

    def _update_footprints_info(self) -> None:
        p = Path(self.txt_footprints_dir.text().strip())
        if p.exists() and p.is_dir():
            count = len(list(p.rglob("*.PcbLib")) + list(p.rglob("*.pcblib")))
            self.lbl_footprints_info.setText(f"✓ Valid directory ({count} .PcbLib files detected)")
            self.lbl_footprints_info.setStyleSheet("font-size: 11px; color: #40ff80;")
        else:
            self.lbl_footprints_info.setText("✕ Directory does not exist")
            self.lbl_footprints_info.setStyleSheet("font-size: 11px; color: #ff6666;")

    # ---------------- File / Directory Browser Handlers ----------------
    def _on_browse_db(self) -> None:
        current = self.txt_db_path.text().strip() or str(BASE_DIR)
        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select Microsoft Access Database",
            current,
            "Access Database (*.accdb *.mdb);;All Files (*.*)",
        )
        if selected_file:
            self.txt_db_path.setText(selected_file)
            self._on_test_db_connection()

    def _on_create_new_db(self) -> None:
        current_dir = str(Path(self.txt_db_path.text()).parent if self.txt_db_path.text() else BASE_DIR)
        selected_file, _ = QFileDialog.getSaveFileName(
            self,
            "Create New Microsoft Access Database",
            str(Path(current_dir) / "NewDatabase.accdb"),
            "Microsoft Access Database (*.accdb)",
        )
        if not selected_file:
            return
        if not selected_file.lower().endswith(".accdb") and not selected_file.lower().endswith(".mdb"):
            selected_file += ".accdb"

        try:
            AccessDBManager.create_new_database(selected_file)
            self.txt_db_path.setText(selected_file)
            self._on_test_db_connection()
            QMessageBox.information(
                self,
                "Database Created",
                f"New Microsoft Access database created successfully at:\n{selected_file}\n\n"
                f"Click 'Save & Apply' to switch to the new database."
            )
        except Exception as exc:
            logger.error(f"Failed to create new database: {exc}", exc_info=True)
            QMessageBox.critical(self, "Error Creating Database", f"Failed to create database:\n{exc}")

    def _on_browse_symbols_dir(self) -> None:
        current = self.txt_symbols_dir.text().strip() or str(BASE_DIR)
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Schematic Symbols Root Directory",
            current,
        )
        if selected_dir:
            self.txt_symbols_dir.setText(selected_dir)

    def _on_browse_footprints_dir(self) -> None:
        current = self.txt_footprints_dir.text().strip() or str(BASE_DIR)
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Select PCB Footprints Root Directory",
            current,
        )
        if selected_dir:
            self.txt_footprints_dir.setText(selected_dir)

    # ---------------- Test Connections ----------------
    def _on_test_db_connection(self) -> None:
        p_str = self.txt_db_path.text().strip()
        if not p_str:
            self.lbl_db_status.setText("<span style='color: #ff5555;'>✕ Please specify a database file.</span>")
            return

        p = Path(p_str)
        if not p.exists():
            self.lbl_db_status.setText(f"<span style='color: #ff5555;'>✕ File not found: {p.name}</span>")
            return

        self.lbl_db_status.setText("<span style='color: #58a6ff;'>Testing Access connection...</span>")
        QApplication.processEvents()

        test_mgr = AccessDBManager(p)
        ok, msg = test_mgr.test_connection()
        if ok:
            self.lbl_db_status.setText(f"<span style='color: #40ff80; font-weight: bold;'>✓ {msg}</span>")
        else:
            self.lbl_db_status.setText(f"<span style='color: #ff5555; font-weight: bold;'>✕ {msg}</span>")

    def _build_inventree_connection_object(self) -> Any:
        try:
            from inventree_client import InventreeConnection
            return InventreeConnection(
                base_url=self.txt_it_url.text().strip(),
                username=self.txt_it_user.text().strip(),
                password=self.txt_it_pwd.text(),
                api_token=self.txt_it_token.text().strip(),
            )
        except ImportError:
            class TempConn:
                def __init__(self, base_url, username, password, api_token):
                    self.base_url = base_url
                    self.username = username
                    self.password = password
                    self.api_token = api_token
            return TempConn(
                self.txt_it_url.text().strip(),
                self.txt_it_user.text().strip(),
                self.txt_it_pwd.text(),
                self.txt_it_token.text().strip(),
            )

    def _on_test_inventree_connection(self) -> None:
        conn = self._build_inventree_connection_object()
        self.lbl_it_test_status.setText("<span style='color: #58a6ff;'>Testing connection...</span>")
        QApplication.processEvents()

        try:
            from inventree_client import test_connection
            ok, msg = test_connection(conn)
            if ok:
                self.lbl_it_test_status.setText(f"<span style='color: #40ff80; font-weight: bold;'>✓ {msg}</span>")
            else:
                self.lbl_it_test_status.setText(f"<span style='color: #ff5555; font-weight: bold;'>✕ {msg}</span>")
        except Exception as exc:
            self.lbl_it_test_status.setText(f"<span style='color: #ff5555;'>✕ Error: {exc}</span>")

    # ---------------- Save & Apply ----------------
    def _on_save_clicked(self) -> None:
        new_db_str = self.txt_db_path.text().strip()
        new_sym_str = self.txt_symbols_dir.text().strip()
        new_fp_str = self.txt_footprints_dir.text().strip()

        # Validate DB path
        if not new_db_str:
            QMessageBox.warning(self, "Missing Database", "Please enter or browse to an Access database file.")
            self.tabs.setCurrentIndex(0)
            return

        new_db = Path(new_db_str)
        if not new_db.exists():
            QMessageBox.critical(self, "File Not Found", f"Database file does not exist:\n{new_db}")
            self.tabs.setCurrentIndex(0)
            return

        # Validate Symbol directory
        if not new_sym_str:
            QMessageBox.warning(self, "Missing Symbols Directory", "Please select a schematic symbols directory.")
            self.tabs.setCurrentIndex(0)
            return

        new_sym = Path(new_sym_str)
        if not new_sym.exists() or not new_sym.is_dir():
            QMessageBox.warning(self, "Directory Not Found", f"Symbols directory does not exist:\n{new_sym}")
            self.tabs.setCurrentIndex(0)
            return

        # Validate Footprint directory
        if not new_fp_str:
            QMessageBox.warning(self, "Missing Footprints Directory", "Please select a PCB footprints directory.")
            self.tabs.setCurrentIndex(0)
            return

        new_fp = Path(new_fp_str)
        if not new_fp.exists() or not new_fp.is_dir():
            QMessageBox.warning(self, "Directory Not Found", f"Footprints directory does not exist:\n{new_fp}")
            self.tabs.setCurrentIndex(0)
            return

        # Check what changed
        self.db_changed = Path(new_db).resolve() != Path(self.initial_db_path).resolve()
        self.libraries_changed = (
            Path(new_sym).resolve() != Path(self.initial_symbols_dir).resolve()
            or Path(new_fp).resolve() != Path(self.initial_footprints_dir).resolve()
        )

        # Save app settings
        save_app_settings(
            db_path=new_db,
            symbols_dir=new_sym,
            footprints_dir=new_fp,
        )

        # Save InvenTree settings if URL provided
        it_url = self.txt_it_url.text().strip()
        if it_url:
            conn = self._build_inventree_connection_object()
            try:
                from inventree_client import save_settings
                save_settings(conn)
                self.it_client.reload_settings()
                self.inventree_changed = True
                logger.info(f"Saved and reloaded InvenTree settings for {it_url}")
            except Exception as exc:
                logger.error(f"Failed to save InvenTree settings: {exc}")
                QMessageBox.critical(self, "Error Saving InvenTree Settings", f"Failed to write settings:\n{exc}")
                return

        # Save field mappings
        mappings = self._get_mappings_from_table()
        fmt_units = self.chk_format_stock_units.isChecked()
        omit_pcs = self.chk_omit_pcs.isChecked()
        AppSettingsManager.get_instance().save_field_mappings(mappings, format_units=fmt_units, omit_pcs=omit_pcs)
        self.mappings_changed = True

        # Save theme if changed
        if self.new_theme != self._initial_theme:
            save_current_theme(self.new_theme)
            apply_theme(self.new_theme)
            self.theme_changed = True

        logger.info(
            f"Settings saved successfully. db_changed={self.db_changed}, "
            f"libraries_changed={self.libraries_changed}, inventree_changed={self.inventree_changed}, "
            f"mappings_changed={self.mappings_changed}"
        )
        self.accept()
