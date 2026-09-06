# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt, QDir, QModelIndex, Signal
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
)
from ..config import (
    SYMBOLS_DIR,
    FOOTPRINTS_DIR,
    get_symbols_dir,
    get_footprints_dir,
    to_relative_path,
    to_absolute_path,
)
from ..altium.parser import AltiumParser
from ..altium.preview_cache import PreviewCache
from ..altium.library_history import LibraryHistoryManager
from .svg_viewer import SvgViewer
from .footprint_preview_widget import FootprintPreviewWidget
from .icons import AppIcons

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

        # Pane 1: File Tree
        tree_container = QWidget()
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(6)
        tree_label = QLabel("Library Files:")
        tree_label.setStyleSheet("font-weight: bold; color: #a0a0c0; font-size: 12px;")
        tree_layout.addWidget(tree_label)

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
        tree_layout.addWidget(self.tree_view)
        splitter.addWidget(tree_container)

        # Pane 2: Parts List & History with Search
        parts_container = QWidget()
        parts_layout = QVBoxLayout(parts_container)
        parts_layout.setContentsMargins(0, 0, 0, 0)
        parts_layout.setSpacing(6)

        # Search Bar
        self.search_input = QLineEdit(parts_container)
        self.search_input.setPlaceholderText("Filter components...")
        self.search_input.addAction(AppIcons.search(), QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter_active_list)
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
        self.parts_list.itemClicked.connect(self._on_part_clicked)
        self.parts_list.itemDoubleClicked.connect(self._on_part_double_clicked)
        tab_file_layout.addWidget(self.parts_list)
        self.tabs_parts.addTab(tab_file_widget, "In Library File")

        # Tab 2: Recent History
        tab_hist_widget = QWidget()
        tab_hist_layout = QVBoxLayout(tab_hist_widget)
        tab_hist_layout.setContentsMargins(4, 6, 4, 4)
        tab_hist_layout.setSpacing(4)

        self.history_list = QListWidget(tab_hist_widget)
        self.history_list.itemClicked.connect(self._on_history_item_clicked)
        self.history_list.itemDoubleClicked.connect(self._on_history_item_double_clicked)
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

    def _on_file_selected(self, index: QModelIndex) -> None:
        file_path = self.fs_model.filePath(index)
        p = Path(file_path)
        if not p.is_file():
            return

        self.selected_file_path = file_path
        self.parts_list.clear()
        self._all_parts_in_current_file = self.parser.list_parts(file_path)

        # Switch to "In Library File" tab
        self.tabs_parts.setCurrentIndex(0)
        self.tabs_parts.setTabText(0, f"In File ({len(self._all_parts_in_current_file)})")

        for part_name in self._all_parts_in_current_file:
            self.parts_list.addItem(QListWidgetItem(part_name))

        if self._all_parts_in_current_file:
            first_item = self.parts_list.item(0)
            self.parts_list.setCurrentItem(first_item)
            self._on_part_clicked(first_item)
        else:
            self.selected_part_name = ""
            self.lbl_selection.setText("Selected: None")
            self.lbl_part_info.setText(f"File: {to_relative_path(file_path)}\nNo parts found")
            self.btn_select.setEnabled(False)
            self.svg_viewer.show_placeholder("No parts found in library file")

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
        filter_str = text.strip().lower()
        active_tab = self.tabs_parts.currentIndex()

        if active_tab == 0:
            # Filter parts in file
            self.parts_list.clear()
            for part in self._all_parts_in_current_file:
                if not filter_str or filter_str in part.lower():
                    self.parts_list.addItem(QListWidgetItem(part))
        else:
            # Filter history
            self.history_list.clear()
            history = self.history_manager.get_history(self.mode)
            for item_data in history:
                part_name = item_data.get("part_name", "")
                file_path = item_data.get("file_path", "")
                if not filter_str or filter_str in part_name.lower() or filter_str in file_path.lower():
                    item = QListWidgetItem(part_name)
                    item.setData(Qt.ItemDataRole.UserRole, file_path)
                    item.setToolTip(f"Component: {part_name}\nFile: {file_path}")
                    self.history_list.addItem(item)

    def _on_part_clicked(self, item: QListWidgetItem) -> None:
        part_name = item.text()
        self.selected_part_name = part_name
        rel_path = to_relative_path(self.selected_file_path)
        self.lbl_selection.setText(f"{part_name}  ({Path(self.selected_file_path).name})")
        self.lbl_part_info.setText(f"File: {rel_path}\nPart: {part_name}")
        self.btn_select.setEnabled(True)

        # Render preview
        svg_str = self.cache.get_svg(self.selected_file_path, part_name, width=500, height=500)
        if hasattr(self.svg_viewer, "load_footprint"):
            self.svg_viewer.load_footprint(self.selected_file_path, part_name, svg_str, title=part_name)
        else:
            self.svg_viewer.load_svg(svg_str, part_name)

    def _on_part_double_clicked(self, item: QListWidgetItem) -> None:
        self._on_part_clicked(item)
        self._confirm_selection()

    def _on_history_item_clicked(self, item: QListWidgetItem) -> None:
        part_name = item.text()
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
            svg_str = self.cache.get_svg(str(abs_p), part_name, width=500, height=500)
            if hasattr(self.svg_viewer, "load_footprint"):
                self.svg_viewer.load_footprint(str(abs_p), part_name, svg_str, title=part_name)
            else:
                self.svg_viewer.load_svg(svg_str, part_name)

            # Highlight in tree view
            idx = self.fs_model.index(str(abs_p))
            if idx.isValid():
                self.tree_view.blockSignals(True)
                self.tree_view.setCurrentIndex(idx)
                self.tree_view.scrollTo(idx)
                self.tree_view.blockSignals(False)
        else:
            self.svg_viewer.show_placeholder(f"File not found:\n{rel_path}")

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
