# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from PySide6.QtCore import Qt, QByteArray, QSize
from PySide6.QtGui import QPainter, QWheelEvent
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGraphicsView,
    QGraphicsScene,
)
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from PySide6.QtSvg import QSvgRenderer
from .icons import AppIcons

logger = logging.getLogger(__name__)

class _SvgGraphicsView(QGraphicsView):
    """QGraphicsView that delegates plain mouse wheel scrolling to parent containers."""

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            # Forward to parent SvgViewer to perform zoom
            event.ignore()
        else:
            # Let parent QScrollArea handle vertical panel scrolling
            event.ignore()


class SvgViewer(QWidget):
    """Interactive SVG viewer with Pan and Zoom for Altium symbols and footprints."""

    def __init__(self, title: str = "Preview", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.title_text = title

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # Header bar
        header_layout = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; color: #a0a0c0;")
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        # Modern Icon Zoom Buttons
        self.btn_zoom_in = QPushButton()
        self.btn_zoom_in.setIcon(AppIcons.zoom_in())
        self.btn_zoom_in.setIconSize(QSize(15, 15))
        self.btn_zoom_in.setFixedSize(28, 28)
        self.btn_zoom_in.setToolTip("Zoom In (Ctrl + Scroll Up)")
        self.btn_zoom_in.clicked.connect(lambda: self.zoom(1.2))

        self.btn_zoom_out = QPushButton()
        self.btn_zoom_out.setIcon(AppIcons.zoom_out())
        self.btn_zoom_out.setIconSize(QSize(15, 15))
        self.btn_zoom_out.setFixedSize(28, 28)
        self.btn_zoom_out.setToolTip("Zoom Out (Ctrl + Scroll Down)")
        self.btn_zoom_out.clicked.connect(lambda: self.zoom(0.8))

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

        # Graphics Scene & View
        self.scene = QGraphicsScene(self)
        self.view = _SvgGraphicsView(self.scene, self)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        main_layout.addWidget(self.view)

        # CRITICAL: Keep reference to QSvgRenderer so it doesn't get garbage-collected by Python!
        self.renderer: QSvgRenderer | None = None
        self.svg_item: QGraphicsSvgItem | None = None
        self.current_scale = 1.0

    def set_title(self, text: str) -> None:
        self.title_label.setText(f"{self.title_text}: {text}" if text else self.title_text)

    def load_svg(self, svg_str: str, title: str = "") -> None:
        if title:
            self.set_title(title)

        try:
            self.scene.clear()
            self.svg_item = None
            self.renderer = None
            self.current_scale = 1.0

            if not svg_str or not svg_str.strip():
                self.show_placeholder("No preview available")
                return

            byte_arr = QByteArray(svg_str.encode("utf-8"))
            self.renderer = QSvgRenderer(byte_arr)

            if not self.renderer.isValid():
                logger.warning(f"Invalid SVG format received in SvgViewer ({title})")
                self.show_placeholder("Invalid SVG format")
                return

            self.svg_item = QGraphicsSvgItem()
            self.svg_item.setSharedRenderer(self.renderer)
            self.scene.addItem(self.svg_item)

            # Center and fit in view
            bounds = self.svg_item.boundingRect()
            if not bounds.isEmpty() and bounds.width() > 0 and bounds.height() > 0:
                self.scene.setSceneRect(bounds)
                self.view.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
            else:
                self.show_placeholder("Empty SVG bounds")
        except Exception as exc:
            logger.error(f"Error rendering SVG in SvgViewer: {exc}", exc_info=True)
            self.show_placeholder(f"Preview error: {exc}")

    def show_placeholder(self, message: str) -> None:
        self.scene.clear()
        self.svg_item = None
        self.renderer = None
        text_item = self.scene.addText(message)
        text_item.setDefaultTextColor(Qt.GlobalColor.darkGray)
        bounds = text_item.boundingRect()
        if not bounds.isEmpty():
            self.scene.setSceneRect(bounds)
            self.view.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def zoom(self, factor: float) -> None:
        self.current_scale *= factor
        self.view.scale(factor, factor)

    def reset_view(self) -> None:
        if self.svg_item and self.renderer and self.renderer.isValid():
            self.view.resetTransform()
            bounds = self.svg_item.boundingRect()
            if not bounds.isEmpty():
                self.view.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
            self.current_scale = 1.0

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom(1.15)
            else:
                self.zoom(0.85)
            event.accept()
        else:
            event.ignore()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.current_scale == 1.0 and self.svg_item and self.renderer and self.renderer.isValid():
            bounds = self.svg_item.boundingRect()
            if not bounds.isEmpty():
                self.view.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

