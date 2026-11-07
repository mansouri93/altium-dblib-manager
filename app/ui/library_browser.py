# -*- coding: utf-8 -*-
from __future__ import annotations
import os
from pathlib import Path
from PySide6.QtCore import Qt, QDir, QModelIndex, Signal, QSize
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTreeView,
    QFileSystemModel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QPushButton,
    QLabel,
    QWidget,
    QMessageBox,
    QSizePolicy,
    QHeaderView,
    QFrame,
    QTabWidget,
    QStackedWidget,
    QComboBox,
)
from ..config import (
    SYMBOLS_DIR,
    FOOTPRINTS_DIR,
    get_symbols_dir,
    get_footprints_dir,
    to_relative_path,
    to_absolute_path,
)
from ..altium.parser import AltiumParser, part_id_to_name
from ..altium.preview_cache import PreviewCache
from ..altium.library_history import LibraryHistoryManager
from .svg_viewer import SvgViewer
from .footprint_preview_widget import FootprintPreviewWidget
from .icons import AppIcons

def matches_all_keywords(target: str, query: str) -> bool:
    """
    Check if all whitespace-separated keywords in query are present in target.
    Matching is case-insensitive and independent of keyword order.
    """
    if not query:
        return True
    keywords = [kw.lower() for kw in query.strip().split() if kw]
    if not keywords:
        return True
    target_lower = target.lower()
    return all(kw in target_lower for kw in keywords)

COMPACT_LIST_STYLE = """
    QListWidget {
        background-color: #13131a;
        border: 1px solid #2b2b3c;
        border-radius: 4px;
        padding: 2px;
        outline: none;
    }
    QListWidget::item {
        padding: 0px 6px;
        margin: 0px;
        height: 20px;
        font-size: 11.5px;
        color: #c0c0d8;
        border: 1px solid transparent;
        border-radius: 2px;
    }
    QListWidget::item:hover {
        background-color: #222235;
        color: #ffffff;
        border-color: #383852;
    }
    QListWidget::item:selected {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007acc, stop:1 #0099ff);
        color: #ffffff;
        font-weight: 600;
        border-color: #58a6ff;
    }
"""


class LibraryBrowserDialog(QDialog):
    """
    Dialog for browsing Altium library files (.SchLib or .PcbLib),
    listing parts with live search, history tracking, and SVG preview.
    """

    def __init__(
        self,
        mode: str = "SYMBOL",  # "SYMBOL" or "FOOTPRINT"
        cache: PreviewCache | None = None,
        initial_path: str = "",
        initial_part: str = "",
        root_dir: str | Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode.upper()
        if root_dir:
            self.root_dir = Path(root_dir)
        else:
            self.root_dir = get_symbols_dir() if self.mode == "SYMBOL" else get_footprints_dir()
        self.cache = cache or PreviewCache()
        self.parser = self.cache.parser
        self.history_manager = LibraryHistoryManager.get_instance()

        self.selected_file_path: str = ""
        self.selected_part_name: str = ""
        self._all_parts_in_current_file: list[str] = []
        self._cached_library_files: list[Path] | None = None

        self.setWindowTitle(f"Altium Library Browser — {self.mode.title()}s")
        self.resize(1080, 680)
        self.setMinimumSize(850, 520)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # Top Information Banner
        header_widget = QWidget(self)
        header_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(2, 2, 2, 4)
        header_layout.setSpacing(10)

        icon_lbl = QLabel(header_widget)
        icon = AppIcons.browse_symbol() if self.mode == "SYMBOL" else AppIcons.browse_footprint()
        icon_lbl.setPixmap(icon.pixmap(24, 24))
        header_layout.addWidget(icon_lbl)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        title_lbl = QLabel(f"Browse Altium {self.mode.title()}s", header_widget)
        title_lbl.setStyleSheet("font-size: 13.5px; font-weight: bold; color: #58a6ff;")
        desc_lbl = QLabel(
            "Select a library file from the tree or choose from recent history, "
            "and preview its graphical representation.",
            header_widget,
        )
        desc_lbl.setStyleSheet("color: #8f8fa8; font-size: 11.5px;")
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(desc_lbl)
        header_layout.addLayout(text_layout)
        header_layout.addStretch()

        main_layout.addWidget(header_widget)

        # 3-Pane Splitter: [File Tree] | [Parts List + Recent History Tabs] | [SVG Preview]
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Pane 1: File Tree with dedicated Search Bar
        tree_container = QWidget()
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(6)
        tree_label = QLabel("Library Files:")
        tree_label.setStyleSheet("font-weight: bold; color: #a0a0c0; font-size: 12px;")
        tree_layout.addWidget(tree_label)

        self.file_search_input = QLineEdit(tree_container)
        self.file_search_input.setPlaceholderText(f"Filter {self.mode.lower()} files (Press Enter)...")
        act_file_search = self.file_search_input.addAction(AppIcons.search(), QLineEdit.ActionPosition.LeadingPosition)
        act_file_search.triggered.connect(self._on_file_search_enter)
        self.file_search_input.setClearButtonEnabled(True)
        self.file_search_input.returnPressed.connect(self._on_file_search_enter)
        self.file_search_input.textChanged.connect(self._on_file_search_text_changed)
        tree_layout.addWidget(self.file_search_input)

        self.tree_stack = QStackedWidget(tree_container)

        self.fs_model = QFileSystemModel(self)
        root_dir = self.root_dir
        filters = ["*.SCHLIB", "*.schlib"] if self.mode == "SYMBOL" else ["*.PCBLIB", "*.pcblib"]

        self.fs_model.setRootPath(str(root_dir))
        self.fs_model.setNameFilters(filters)
        self.fs_model.setNameFilterDisables(False)

        self.tree_view = QTreeView(self)
        self.tree_view.setModel(self.fs_model)
        self.tree_view.setRootIndex(self.fs_model.index(str(root_dir)))
        self.tree_view.setHeaderHidden(True)
        self.tree_view.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree_view.setColumnHidden(1, True)  # Size
        self.tree_view.setColumnHidden(2, True)  # Type
        self.tree_view.setColumnHidden(3, True)  # Date
        self.tree_view.clicked.connect(self._on_file_selected)
        if self.tree_view.selectionModel():
            self.tree_view.selectionModel().currentChanged.connect(
                lambda cur, prev: self._on_file_selected(cur) if cur.isValid() else None
            )
        self.tree_stack.addWidget(self.tree_view)

        self.file_search_list = QListWidget(self)
        self.file_search_list.setStyleSheet(COMPACT_LIST_STYLE)
        self.file_search_list.setIconSize(QSize(14, 14))
        self.file_search_list.setSpacing(0)
        self.file_search_list.itemClicked.connect(self._on_search_file_clicked)
        self.file_search_list.itemDoubleClicked.connect(self._on_search_file_double_clicked)
        self.file_search_list.currentItemChanged.connect(
            lambda cur, prev: self._on_search_file_clicked(cur) if cur else None
        )
        self.tree_stack.addWidget(self.file_search_list)

        tree_layout.addWidget(self.tree_stack)
        splitter.addWidget(tree_container)

        # Pane 2: Parts List & History with Search
        parts_container = QWidget()
        parts_layout = QVBoxLayout(parts_container)
        parts_layout.setContentsMargins(0, 0, 0, 0)
        parts_layout.setSpacing(6)

        # Search Bar
        self.search_input = QLineEdit(parts_container)
        self.search_input.setPlaceholderText(f"Filter {self.mode.lower()}s (Press Enter)...")
        act_parts_search = self.search_input.addAction(AppIcons.search(), QLineEdit.ActionPosition.LeadingPosition)
        act_parts_search.triggered.connect(self._on_parts_search_enter)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self._on_parts_search_enter)
        self.search_input.textChanged.connect(self._on_parts_search_text_changed)
        parts_layout.addWidget(self.search_input)

        # Tab Widget: [ In Library File ] | [ Recent History ]
        self.tabs_parts = QTabWidget(parts_container)
        self.tabs_parts.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #2b2b40;
                background-color: #171724;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #1e1e2e;
                color: #a0a0c0;
                padding: 6px 10px;
                border: 1px solid #2b2b40;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 11.5px;
                font-weight: 500;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #26263d;
                color: #58a6ff;
                font-weight: bold;
                border-color: #3d3d5c;
            }
            QTabBar::tab:hover:!selected {
                background-color: #222235;
                color: #ffffff;
            }
        """)

        # Tab 1: Components in Current File
        tab_file_widget = QWidget()
        tab_file_layout = QVBoxLayout(tab_file_widget)
        tab_file_layout.setContentsMargins(4, 6, 4, 4)
        tab_file_layout.setSpacing(4)

        self.parts_list = QListWidget(tab_file_widget)
        self.parts_list.setStyleSheet(COMPACT_LIST_STYLE)
        self.parts_list.setSpacing(0)
        self.parts_list.itemClicked.connect(self._on_part_clicked)
        self.parts_list.itemDoubleClicked.connect(self._on_part_double_clicked)
        self.parts_list.currentItemChanged.connect(
            lambda cur, prev: self._on_part_clicked(cur) if cur else None
        )
        tab_file_layout.addWidget(self.parts_list)
        self.tabs_parts.addTab(tab_file_widget, "In Library File")

        # Tab 2: Recent History
        tab_hist_widget = QWidget()
        tab_hist_layout = QVBoxLayout(tab_hist_widget)
        tab_hist_layout.setContentsMargins(4, 6, 4, 4)
        tab_hist_layout.setSpacing(4)

        self.history_list = QListWidget(tab_hist_widget)
        self.history_list.setStyleSheet(COMPACT_LIST_STYLE)
        self.history_list.setIconSize(QSize(14, 14))
        self.history_list.setSpacing(0)
        self.history_list.itemClicked.connect(self._on_history_item_clicked)
        self.history_list.itemDoubleClicked.connect(self._on_history_item_double_clicked)
        self.history_list.currentItemChanged.connect(
            lambda cur, prev: self._on_history_item_clicked(cur) if cur else None
        )
        tab_hist_layout.addWidget(self.history_list)

        hist_btn_layout = QHBoxLayout()
        hist_btn_layout.setContentsMargins(0, 2, 0, 0)
        self.btn_clear_history = QPushButton("Clear History")
        self.btn_clear_history.setIcon(AppIcons.delete())
        self.btn_clear_history.setFixedHeight(22)
        self.btn_clear_history.setStyleSheet("font-size: 10.5px; padding: 2px 8px; color: #ff8888;")
        self.btn_clear_history.clicked.connect(self._on_clear_history)
        hist_btn_layout.addStretch()
        hist_btn_layout.addWidget(self.btn_clear_history)
        tab_hist_layout.addLayout(hist_btn_layout)

        self.tabs_parts.addTab(tab_hist_widget, AppIcons.history(), "Recent History")
        self.tabs_parts.currentChanged.connect(self._on_tab_changed)

        parts_layout.addWidget(self.tabs_parts)
        splitter.addWidget(parts_container)

        # Pane 3: SVG Preview
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(6)

        if self.mode in ("FOOTPRINT", "footprint"):
            self.svg_viewer = FootprintPreviewWidget(f"{self.mode.title()} Preview", self)
        else:
            # Sub-part selector bar (visible only when symbol has multiple parts)
            self.sym_part_bar = QWidget(self)
            sym_part_layout = QHBoxLayout(self.sym_part_bar)
            sym_part_layout.setContentsMargins(2, 0, 2, 2)
            sym_part_layout.setSpacing(6)

            lbl_sym_part = QLabel("Sub-part:", self.sym_part_bar)
            lbl_sym_part.setStyleSheet("color: #a0a0c0; font-size: 11px; font-weight: bold;")
            sym_part_layout.addWidget(lbl_sym_part)

            self.combo_sym_parts = QComboBox(self.sym_part_bar)
            self.combo_sym_parts.setCursor(Qt.CursorShape.PointingHandCursor)
            self.combo_sym_parts.setStyleSheet("""
                QComboBox {
                    background-color: #212130;
                    color: #e0e0ff;
                    border: 1px solid #33334d;
                    border-radius: 4px;
                    padding: 3px 8px;
                    font-size: 11px;
                    font-weight: 500;
                    min-width: 90px;
                }
                QComboBox:hover {
                    background-color: #2a2a3e;
                    border-color: #4a4a6e;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 16px;
                }
                QComboBox QAbstractItemView {
                    background-color: #1e1e28;
                    color: #e0e0ff;
                    selection-background-color: #007acc;
                    border: 1px solid #33334d;
                }
            """)
            self.combo_sym_parts.currentIndexChanged.connect(self._on_sym_part_changed)
            sym_part_layout.addWidget(self.combo_sym_parts)
            sym_part_layout.addStretch()
            self.sym_part_bar.setVisible(False)
            preview_layout.addWidget(self.sym_part_bar)

            self.svg_viewer = SvgViewer(f"{self.mode.title()} Preview", self)
        preview_layout.addWidget(self.svg_viewer)

        self.lbl_part_info = QLabel("No component selected")
        self.lbl_part_info.setStyleSheet("color: #8888aa; font-size: 11px;")
        preview_layout.addWidget(self.lbl_part_info)
        splitter.addWidget(preview_container)

        # Splitter sizing and stretch factors
        splitter.setSizes([320, 260, 480])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 5)
        main_layout.addWidget(splitter, stretch=1)

        # Bottom Button Bar
        btn_layout = QHBoxLayout()
        self.lbl_selection = QLabel("Selected: None")
        self.lbl_selection.setStyleSheet("color: #4da6ff; font-weight: bold;")
        btn_layout.addWidget(self.lbl_selection)

        btn_layout.addStretch()

        self.btn_cancel = QPushButton(" Cancel")
        self.btn_cancel.setIcon(AppIcons.cancel())
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_select = QPushButton(" Assign to Part")
        self.btn_select.setIcon(AppIcons.check())
        self.btn_select.setObjectName("PrimaryButton")
        self.btn_select.setEnabled(False)
        self.btn_select.clicked.connect(self._confirm_selection)
        btn_layout.addWidget(self.btn_select)

        main_layout.addLayout(btn_layout)

        # Load history and handle initial navigation
        self._load_history_tab()
        self._handle_initial_selection(initial_path, initial_part)

    def _load_history_tab(self) -> None:
        self.history_list.clear()
        history = self.history_manager.get_history(self.mode)
        count = len(history)
        self.tabs_parts.setTabText(1, f"Recent ({count})")
        self.btn_clear_history.setEnabled(count > 0)

        for item_data in history:
            part_name = item_data.get("part_name", "")
            file_path = item_data.get("file_path", "")
            last_used = item_data.get("last_used", "")
            time_display = last_used[:16].replace("T", " ") if last_used else ""

            item = QListWidgetItem(part_name)
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            item.setToolTip(f"Component: {part_name}\nFile: {file_path}\nLast used: {time_display}")
            self.history_list.addItem(item)

    def _handle_initial_selection(self, initial_path: str, initial_part: str) -> None:
        if initial_path:
            abs_p = to_absolute_path(initial_path)
            if abs_p and abs_p.is_file():
                idx = self.fs_model.index(str(abs_p))
                if idx.isValid():
                    self.tree_view.setCurrentIndex(idx)
                    self.tree_view.scrollTo(idx)
                    self._on_file_selected(idx)
                    if initial_part:
                        for i in range(self.parts_list.count()):
                            if self.parts_list.item(i).text() == initial_part:
                                item = self.parts_list.item(i)
                                self.parts_list.setCurrentItem(item)
                                self._on_part_clicked(item)
                                break
                    return

        # If no initial selection but history exists, start on Recent tab
        history = self.history_manager.get_history(self.mode)
        if history:
            self.tabs_parts.setCurrentIndex(1)
            # Pre-select first recent item
            if self.history_list.count() > 0:
                item = self.history_list.item(0)
                self.history_list.setCurrentItem(item)
                self._on_history_item_clicked(item)

    def _get_all_library_files(self) -> list[Path]:
        """Lazy-load and cache the list of all library files for the current mode."""
        if self._cached_library_files is not None:
            return self._cached_library_files

        exts = {".schlib"} if self.mode == "SYMBOL" else {".pcblib"}
        files: list[Path] = []
        if self.root_dir and self.root_dir.is_dir():
            for root, _, filenames in os.walk(self.root_dir):
                for fn in filenames:
                    if Path(fn).suffix.lower() in exts:
                        files.append(Path(root) / fn)
        files.sort(key=lambda p: p.name.lower())
        self._cached_library_files = files
        return self._cached_library_files

    def _filter_tree_files(self, text: str) -> None:
        """Filter library files in Pane 1 by whitespace-separated keywords."""
        keywords = [k.lower() for k in text.strip().split() if k]

        if not keywords:
            self.tree_stack.setCurrentIndex(0)
            if self.selected_file_path:
                idx = self.fs_model.index(self.selected_file_path)
                if idx.isValid():
                    self.tree_view.blockSignals(True)
                    self.tree_view.setCurrentIndex(idx)
                    self.tree_view.scrollTo(idx)
                    self.tree_view.blockSignals(False)
            return

        self.tree_stack.setCurrentIndex(1)
        self.file_search_list.clear()

        all_files = self._get_all_library_files()
        matching_count = 0

        for file_path in all_files:
            rel = to_relative_path(file_path)
            target = f"{file_path.name} {rel}"
            if matches_all_keywords(target, text):
                matching_count += 1
                parent_folder = file_path.parent.name
                item_text = f"{file_path.name}  [{parent_folder}]" if parent_folder else file_path.name
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, str(file_path.resolve()))
                item.setToolTip(f"File: {file_path.name}\nPath: {rel}")
                icon = AppIcons.browse_symbol() if self.mode == "SYMBOL" else AppIcons.browse_footprint()
                item.setIcon(icon)
                self.file_search_list.addItem(item)

        if matching_count == 0:
            placeholder_item = QListWidgetItem("No matching library files found")
            placeholder_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.file_search_list.addItem(placeholder_item)

    def _on_file_search_enter(self) -> None:
        """Trigger file tree search when Enter key or Search icon is pressed."""
        self._filter_tree_files(self.file_search_input.text())

    def _on_file_search_text_changed(self, text: str) -> None:
        """Automatically restore the standard tree view when the search input is cleared."""
        if not text.strip():
            self._filter_tree_files("")

    def _load_file(self, file_path: str | Path) -> None:
        """Load component parts from a selected library file."""
        p = Path(file_path)
        if not p.is_file():
            return

        self.selected_file_path = str(p.resolve())
        self.parts_list.clear()
        self._all_parts_in_current_file = self.parser.list_parts(self.selected_file_path)

        # Switch to "In Library File" tab
        self.tabs_parts.setCurrentIndex(0)

        # Apply current filter text if present
        filter_text = self.search_input.text()
        if filter_text.strip():
            self._filter_active_list(filter_text)
        else:
            for part_name in self._all_parts_in_current_file:
                self.parts_list.addItem(QListWidgetItem(part_name))
            self.tabs_parts.setTabText(0, f"In File ({len(self._all_parts_in_current_file)})")

        if self.parts_list.count() > 0:
            first_item = self.parts_list.item(0)
            self.parts_list.setCurrentItem(first_item)
            self._on_part_clicked(first_item)
        else:
            self.selected_part_name = ""
            self.lbl_selection.setText("Selected: None")
            self.lbl_part_info.setText(f"File: {to_relative_path(self.selected_file_path)}\nNo parts found")
            self.btn_select.setEnabled(False)
            if hasattr(self, "sym_part_bar"):
                self.sym_part_bar.setVisible(False)
            self.svg_viewer.show_placeholder("No parts found in library file")

    def _on_file_selected(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        file_path = self.fs_model.filePath(index)
        if file_path:
            self._load_file(file_path)

    def _on_search_file_clicked(self, item: QListWidgetItem | None) -> None:
        if not item:
            return
        file_path = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if file_path:
            self._load_file(file_path)

    def _on_search_file_double_clicked(self, item: QListWidgetItem) -> None:
        self._on_search_file_clicked(item)

    def _on_tab_changed(self, index: int) -> None:
        self.search_input.clear()
        if index == 1:
            # Switched to history tab
            if self.history_list.currentItem():
                self._on_history_item_clicked(self.history_list.currentItem())
        elif index == 0:
            # Switched to file tab
            if self.parts_list.currentItem():
                self._on_part_clicked(self.parts_list.currentItem())

    def _filter_active_list(self, text: str) -> None:
        """Filter parts in file or recent history by whitespace-separated keywords."""
        active_tab = self.tabs_parts.currentIndex()

        if active_tab == 0:
            # Filter parts in file
            self.parts_list.clear()
            for part in self._all_parts_in_current_file:
                if matches_all_keywords(part, text):
                    self.parts_list.addItem(QListWidgetItem(part))
            self.tabs_parts.setTabText(0, f"In File ({self.parts_list.count()})")
        else:
            # Filter history
            self.history_list.clear()
            history = self.history_manager.get_history(self.mode)
            for item_data in history:
                part_name = item_data.get("part_name", "")
                file_path = item_data.get("file_path", "")
                target_str = f"{part_name} {file_path}"
                if matches_all_keywords(target_str, text):
                    item = QListWidgetItem(part_name)
                    item.setData(Qt.ItemDataRole.UserRole, file_path)
                    item.setToolTip(f"Component: {part_name}\nFile: {file_path}")
                    self.history_list.addItem(item)
            self.tabs_parts.setTabText(1, f"Recent ({self.history_list.count()})")

    def _on_parts_search_enter(self) -> None:
        """Trigger component search when Enter key or Search icon is pressed."""
        self._filter_active_list(self.search_input.text())

    def _on_parts_search_text_changed(self, text: str) -> None:
        """Automatically restore the complete component list when the search input is cleared."""
        if not text.strip():
            self._filter_active_list("")

    def _on_part_clicked(self, item: QListWidgetItem | None) -> None:
        if not item:
            return
        part_name = item.text().strip()
        if not part_name:
            return
        self.selected_part_name = part_name
        rel_path = to_relative_path(self.selected_file_path)
        self.lbl_selection.setText(f"{part_name}  ({Path(self.selected_file_path).name})")
        self.lbl_part_info.setText(f"File: {rel_path}\nPart: {part_name}")
        self.btn_select.setEnabled(True)

        # Render preview
        self._render_active_preview(reload_parts=True)

    def _on_part_double_clicked(self, item: QListWidgetItem) -> None:
        self._on_part_clicked(item)
        self._confirm_selection()

    def _on_history_item_clicked(self, item: QListWidgetItem | None) -> None:
        if not item:
            return
        part_name = item.text().strip()
        rel_path = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not part_name or not rel_path:
            return

        self.selected_part_name = part_name
        self.selected_file_path = rel_path
        abs_p = to_absolute_path(rel_path)
        file_name = Path(rel_path).name
        self.lbl_selection.setText(f"{part_name}  ({file_name})")
        self.lbl_part_info.setText(f"File: {rel_path}\nPart: {part_name}")
        self.btn_select.setEnabled(True)

        # Render preview
        if abs_p and abs_p.exists():
            self._render_active_preview(reload_parts=True)

            # Highlight in tree view
            idx = self.fs_model.index(str(abs_p))
            if idx.isValid():
                sel_m = self.tree_view.selectionModel()
                if sel_m:
                    sel_m.blockSignals(True)
                self.tree_view.blockSignals(True)
                self.tree_view.setCurrentIndex(idx)
                self.tree_view.scrollTo(idx)
                self.tree_view.blockSignals(False)
                if sel_m:
                    sel_m.blockSignals(False)
        else:
            if hasattr(self, "sym_part_bar"):
                self.sym_part_bar.setVisible(False)
            self.svg_viewer.show_placeholder(f"File not found:\n{rel_path}")

    def _on_sym_part_changed(self) -> None:
        """Handle user changing active sub-part in Library Browser."""
        if not self.selected_file_path or not self.selected_part_name:
            return
        if not hasattr(self, "sym_part_bar") or not self.sym_part_bar.isVisible():
            return
        self._render_active_preview(reload_parts=False)

    def _render_active_preview(self, reload_parts: bool = True) -> None:
        """Render active preview with sub-part support for schematic symbols."""
        if not self.selected_file_path or not self.selected_part_name:
            return

        abs_p = to_absolute_path(self.selected_file_path)
        path_str = str(abs_p) if abs_p and abs_p.exists() else self.selected_file_path

        if hasattr(self, "sym_part_bar") and hasattr(self, "combo_sym_parts"):
            if reload_parts:
                subpart_count = self.cache.get_subpart_count(path_str, self.selected_part_name)
                self.combo_sym_parts.blockSignals(True)
                self.combo_sym_parts.clear()
                if subpart_count > 1:
                    for i in range(1, subpart_count + 1):
                        self.combo_sym_parts.addItem(part_id_to_name(i), i)
                    self.combo_sym_parts.setCurrentIndex(0)
                    self.sym_part_bar.setVisible(True)
                else:
                    self.sym_part_bar.setVisible(False)
                self.combo_sym_parts.blockSignals(False)

            subpart_id = 1
            part_tag = ""
            if self.sym_part_bar.isVisible():
                subpart_id = self.combo_sym_parts.currentData() or 1
                part_tag = f" [{part_id_to_name(subpart_id)}]"

            svg_str = self.cache.get_svg(path_str, self.selected_part_name, width=500, height=500, subpart_id=subpart_id)
            if hasattr(self.svg_viewer, "load_footprint"):
                self.svg_viewer.load_footprint(path_str, self.selected_part_name, svg_str, title=self.selected_part_name)
            else:
                self.svg_viewer.load_svg(svg_str, f"{self.selected_part_name}{part_tag}")
        else:
            svg_str = self.cache.get_svg(path_str, self.selected_part_name, width=500, height=500)
            if hasattr(self.svg_viewer, "load_footprint"):
                self.svg_viewer.load_footprint(path_str, self.selected_part_name, svg_str, title=self.selected_part_name)
            else:
                self.svg_viewer.load_svg(svg_str, self.selected_part_name)

    def _on_history_item_double_clicked(self, item: QListWidgetItem) -> None:
        self._on_history_item_clicked(item)
        self._confirm_selection()

    def _on_clear_history(self) -> None:
        reply = QMessageBox.question(
            self,
            "Clear History",
            f"Are you sure you want to clear all recently used {self.mode.lower()}s?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.history_manager.clear_history(self.mode)
            self._load_history_tab()

    def _confirm_selection(self) -> None:
        if not self.selected_file_path or not self.selected_part_name:
            QMessageBox.warning(self, "Selection Missing", "Please select a component first.")
            return

        # Save to persistent history
        self.history_manager.add_entry(
            self.mode,
            self.selected_file_path,
            self.selected_part_name,
        )
        self.accept()

    def get_selection(self) -> tuple[str, str]:
        """Return (relative_library_path, part_name)."""
        return to_relative_path(self.selected_file_path), self.selected_part_name
