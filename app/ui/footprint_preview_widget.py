# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QPushButton,
    QLabel,
    QButtonGroup,
)
from .svg_viewer import SvgViewer
from .footprint_3d_viewer import Footprint3DViewer
from ..altium.footprint_3d import Footprint3DParser, Footprint3DModel
from .icons import AppIcons

logger = logging.getLogger(__name__)


class FootprintPreviewWidget(QWidget):
    """
    Unified Footprint preview container supporting instant switching between
    2D SVG vector drawing and 3D interactive CAD model viewport with real-world dimensions.
    """
    modeChanged = Signal(str)  # "2D" or "3D"

    def __init__(self, title: str = "Footprint", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.title_text = title
        self._current_mode = "2D"  # "2D" or "3D"
        self._parser = Footprint3DParser()
        self._current_file_path: str = ""
        self._current_part_name: str = ""

        # Main Layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # Header Bar
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; color: #a0a0c0;")
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        # Segmented 2D / 3D Mode Switcher
        switcher_container = QWidget()
        switcher_container.setStyleSheet("""
            QWidget {
                background: rgba(20, 24, 32, 0.9);
                border: 1px solid rgba(60, 75, 95, 0.6);
                border-radius: 5px;
            }
        """)
        switcher_layout = QHBoxLayout(switcher_container)
        switcher_layout.setContentsMargins(2, 2, 2, 2)
        switcher_layout.setSpacing(2)

        tab_btn_style = """
            QPushButton {
                background: transparent;
                color: #8c96a8;
                border: none;
                border-radius: 3px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #e0e4f0;
                background: rgba(255, 255, 255, 0.06);
            }
            QPushButton:checked {
                background: #1a73e8;
                color: #ffffff;
            }
        """

        self.btn_mode_2d = QPushButton("2D View")
        self.btn_mode_2d.setCheckable(True)
        self.btn_mode_2d.setChecked(True)
        self.btn_mode_2d.setStyleSheet(tab_btn_style)
        self.btn_mode_2d.setToolTip("Switch to 2D Footprint View (Pads, Silkscreen, Courtyard)")
        self.btn_mode_2d.clicked.connect(lambda: self.set_mode("2D"))
        switcher_layout.addWidget(self.btn_mode_2d)

        self.btn_mode_3d = QPushButton("3D Model")
        self.btn_mode_3d.setCheckable(True)
        self.btn_mode_3d.setStyleSheet(tab_btn_style)
        self.btn_mode_3d.setToolTip("Switch to 3D CAD Model (Real-World Dimensions, Orbit, Height)")
        self.btn_mode_3d.clicked.connect(lambda: self.set_mode("3D"))
        switcher_layout.addWidget(self.btn_mode_3d)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.btn_mode_2d)
        self.mode_group.addButton(self.btn_mode_3d)

        header_layout.addWidget(switcher_container)

        # Header Zoom / Reset Action Controls
        self.btn_zoom_in = QPushButton()
        self.btn_zoom_in.setIcon(AppIcons.zoom_in())
        self.btn_zoom_in.setIconSize(QSize(15, 15))
        self.btn_zoom_in.setFixedSize(28, 28)
        self.btn_zoom_in.setToolTip("Zoom In")
        self.btn_zoom_in.clicked.connect(self._on_zoom_in)

        self.btn_zoom_out = QPushButton()
        self.btn_zoom_out.setIcon(AppIcons.zoom_out())
        self.btn_zoom_out.setIconSize(QSize(15, 15))
        self.btn_zoom_out.setFixedSize(28, 28)
        self.btn_zoom_out.setToolTip("Zoom Out")
        self.btn_zoom_out.clicked.connect(self._on_zoom_out)

        self.btn_reset = QPushButton()
        self.btn_reset.setIcon(AppIcons.zoom_reset())
        self.btn_reset.setIconSize(QSize(15, 15))
        self.btn_reset.setFixedSize(28, 28)
        self.btn_reset.setToolTip("Fit to Window / Reset View")
        self.btn_reset.clicked.connect(self.reset_view)

        header_layout.addWidget(self.btn_zoom_in)
        header_layout.addWidget(self.btn_zoom_out)
        header_layout.addWidget(self.btn_reset)

        main_layout.addLayout(header_layout)

        # Content Stacked Widget
        self.stack = QStackedWidget(self)

        # Page 0: 2D SvgViewer
        self.svg_viewer = SvgViewer(title="", parent=self)
        # Hide internal header of SvgViewer to avoid redundant duplicate headers
        if hasattr(self.svg_viewer, "title_label"):
            self.svg_viewer.title_label.hide()
        if hasattr(self.svg_viewer, "btn_zoom_in"):
            self.svg_viewer.btn_zoom_in.hide()
        if hasattr(self.svg_viewer, "btn_zoom_out"):
            self.svg_viewer.btn_zoom_out.hide()
        if hasattr(self.svg_viewer, "btn_reset"):
            self.svg_viewer.btn_reset.hide()

        self.stack.addWidget(self.svg_viewer)

        # Page 1: 3D CAD Viewport
        self.viewer_3d = Footprint3DViewer(self)
        self.stack.addWidget(self.viewer_3d)

        main_layout.addWidget(self.stack, stretch=1)

    # -------------------------------------------------------------------------
    # Mode Switching
    # -------------------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        """Switch view mode between '2D' and '3D'."""
        mode = mode.upper()
        if mode == "3D":
            self._current_mode = "3D"
            self.btn_mode_3d.setChecked(True)
            self.stack.setCurrentIndex(1)
            # If 3D model was not loaded yet for current part, load now
            if self._current_file_path and self._current_part_name and not self.viewer_3d.model:
                self._load_3d_model()
            else:
                self.viewer_3d.fit_to_view()
        else:
            self._current_mode = "2D"
            self.btn_mode_2d.setChecked(True)
            self.stack.setCurrentIndex(0)
            self.svg_viewer.update()

        self.modeChanged.emit(self._current_mode)

    def current_mode(self) -> str:
        return self._current_mode

    # -------------------------------------------------------------------------
    # Public Loading API (SvgViewer compatible + 3D extended)
    # -------------------------------------------------------------------------

    def set_title(self, text: str) -> None:
        self.title_label.setText(f"{self.title_text}: {text}" if text else self.title_text)

    def load_svg(self, svg_str: str, title: str = "") -> None:
        """Loads 2D SVG preview (backwards compatible with SvgViewer interface)."""
        if title:
            self.set_title(title)
        self.svg_viewer.load_svg(svg_str, title)

    def load_footprint(
        self,
        file_path: str | Path,
        part_name: str,
        svg_str: str = "",
        title: str = "",
    ) -> None:
        """Loads both 2D SVG graphic and 3D CAD model with dimension extraction."""
        self._current_file_path = str(file_path)
        self._current_part_name = part_name

        display_title = title or part_name
        if display_title:
            self.set_title(display_title)

        # 1. Load 2D SVG
        if svg_str:
            self.svg_viewer.load_svg(svg_str, display_title)

        # 2. Load 3D Model
        self._load_3d_model()

    def _load_3d_model(self) -> None:
        """Asynchronously or directly load 3D model for current footprint."""
        if not self._current_file_path or not self._current_part_name:
            self.viewer_3d.show_placeholder("Select a component")
            return

        try:
            model = self._parser.get_model(self._current_file_path, self._current_part_name)
            self.viewer_3d.set_model(model)
        except Exception as exc:
            logger.error(f"Error parsing 3D footprint model for {self._current_part_name}: {exc}", exc_info=True)
            self.viewer_3d.show_placeholder(f"3D error: {exc}")

    def show_placeholder(self, message: str) -> None:
        """Display placeholder on both 2D and 3D views."""
        self._current_file_path = ""
        self._current_part_name = ""
        self.svg_viewer.show_placeholder(message)
        self.viewer_3d.show_placeholder(message)

    # -------------------------------------------------------------------------
    # View Controls
    # -------------------------------------------------------------------------

    def zoom(self, factor: float) -> None:
        if self._current_mode == "2D":
            self.svg_viewer.zoom(factor)
        else:
            self.viewer_3d.zoom = max(5.0, min(5000.0, self.viewer_3d.zoom * factor))
            self.viewer_3d.update()

    def _on_zoom_in(self) -> None:
        self.zoom(1.2)

    def _on_zoom_out(self) -> None:
        self.zoom(0.8)

    def reset_view(self) -> None:
        if self._current_mode == "2D":
            self.svg_viewer.reset_view()
        else:
            self.viewer_3d.fit_to_view()
