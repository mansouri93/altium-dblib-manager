# -*- coding: utf-8 -*-
from __future__ import annotations
import math
from typing import Any
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QPolygonF,
    QFont,
    QWheelEvent,
    QMouseEvent,
    QLinearGradient,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QButtonGroup,
)
from ..altium.footprint_3d import Footprint3DModel, Pad3D, Polygon3D


class Footprint3DViewer(QWidget):
    """
    High-performance, pure Python/PySide6 3D CAD viewport for Altium footprint models.
    Supports smooth mouse orbit, pan, zoom, preset views, PCB ground plane, solder pads,
    directional Lambertian shading, 3D dimension arrows, and a real-world dimensions HUD card.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self.model: Footprint3DModel | None = None
        self.placeholder_text: str = "Select a footprint to preview in 3D"

        # Camera state
        self.yaw: float = 45.0      # degrees around Z
        self.pitch: float = 28.0    # degrees above XY plane
        self.zoom: float = 120.0    # pixels per millimeter
        self.pan_x: float = 0.0     # screen X offset
        self.pan_y: float = 0.0     # screen Y offset
        self.show_dimensions: bool = True

        # Mouse tracking
        self._mouse_pressed: bool = False
        self._last_mouse_pos: QPoint = QPoint()
        self._mouse_button: Qt.MouseButton = Qt.MouseButton.NoButton

        # Coplanar polygon grouping for stable detail/text rendering during rotation
        self._planar_groups: list[list] = []

        # Top Control Toolbar
        self._init_controls()

    def _init_controls(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        # Toolbar container
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(4)

        btn_style = """
            QPushButton {
                background: rgba(28, 33, 44, 0.88);
                color: #c0c6d8;
                border: 1px solid rgba(70, 85, 110, 0.5);
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(45, 55, 75, 0.95);
                color: #ffffff;
                border-color: #4da6ff;
            }
            QPushButton:pressed {
                background: #1a73e8;
                color: #ffffff;
            }
        """

        self.btn_iso = QPushButton("ISO")
        self.btn_iso.setToolTip("Isometric 3D View")
        self.btn_iso.setStyleSheet(btn_style)
        self.btn_iso.clicked.connect(self.view_isometric)
        toolbar_layout.addWidget(self.btn_iso)

        self.btn_top = QPushButton("Top")
        self.btn_top.setToolTip("Top View (XY)")
        self.btn_top.setStyleSheet(btn_style)
        self.btn_top.clicked.connect(self.view_top)
        toolbar_layout.addWidget(self.btn_top)

        self.btn_front = QPushButton("Front")
        self.btn_front.setToolTip("Front View (XZ) - Inspect Height & Standoff")
        self.btn_front.setStyleSheet(btn_style)
        self.btn_front.clicked.connect(self.view_front)
        toolbar_layout.addWidget(self.btn_front)

        self.btn_side = QPushButton("Side")
        self.btn_side.setToolTip("Side View (YZ)")
        self.btn_side.setStyleSheet(btn_style)
        self.btn_side.clicked.connect(self.view_side)
        toolbar_layout.addWidget(self.btn_side)

        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setToolTip("Fit View to Window")
        self.btn_reset.setStyleSheet(btn_style)
        self.btn_reset.clicked.connect(self.fit_to_view)
        toolbar_layout.addWidget(self.btn_reset)

        self.btn_dims = QPushButton("Dims ✓")
        self.btn_dims.setToolTip("Toggle 3D Dimension Overlays")
        self.btn_dims.setStyleSheet(btn_style)
        self.btn_dims.clicked.connect(self.toggle_dimensions)
        toolbar_layout.addWidget(self.btn_dims)

        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)
        layout.addStretch()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def set_model(self, model: Footprint3DModel | None) -> None:
        """Load and display a 3D footprint model with pre-grouped coplanar surfaces."""
        self.model = model
        self._planar_groups = []
        if model and model.polygons:
            # Group polygons by coplanar planes: same normal direction and plane distance
            for poly in model.polygons:
                pts = poly.points
                if len(pts) < 3:
                    continue
                nx, ny, nz = poly.normal
                # Plane distance from origin: d = n . p0
                d = nx * pts[0][0] + ny * pts[0][1] + nz * pts[0][2]

                placed = False
                for g in self._planar_groups:
                    rep = g[0]
                    rnx, rny, rnz = rep.normal
                    dot_n = nx * rnx + ny * rny + nz * rnz
                    # Check if normals are parallel and lie on the same plane
                    if abs(dot_n) > 0.999:
                        rd = rnx * rep.points[0][0] + rny * rep.points[0][1] + rnz * rep.points[0][2]
                        expected_d = rd if dot_n > 0 else -rd
                        if abs(d - expected_d) < 0.005:  # within 5 microns
                            g.append(poly)
                            placed = True
                            break
                if not placed:
                    self._planar_groups.append([poly])

            # Within each coplanar group, sort by area descending (largest base surface first)
            for g in self._planar_groups:
                g.sort(key=lambda p: getattr(p, "area", 0.0), reverse=True)

            self.fit_to_view()
        else:
            self.placeholder_text = "No 3D model available"
            self.update()

    def show_placeholder(self, message: str) -> None:
        """Display an empty state message."""
        self.model = None
        self._planar_groups = []
        self.placeholder_text = message
        self.update()

    def view_isometric(self) -> None:
        self.yaw = 45.0
        self.pitch = 28.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

    def view_top(self) -> None:
        self.yaw = 0.0
        self.pitch = 89.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

    def view_front(self) -> None:
        self.yaw = 0.0
        self.pitch = 0.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

    def view_side(self) -> None:
        self.yaw = 90.0
        self.pitch = 0.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

    def toggle_dimensions(self) -> None:
        self.show_dimensions = not self.show_dimensions
        self.btn_dims.setText("Dims ✓" if self.show_dimensions else "Dims ✗")
        self.update()

    def fit_to_view(self) -> None:
        """Calculate optimal zoom and centering to fit the model within viewport."""
        self.pan_x = 0.0
        self.pan_y = 0.0
        if not self.model or (self.model.length_mm <= 0 and self.model.width_mm <= 0):
            self.zoom = 120.0
            self.update()
            return

        # Max component footprint dimension + margin for leader lines
        max_dim = max(self.model.length_mm, self.model.width_mm, self.model.height_mm, 1.0)
        avail_w = max(50.0, float(self.width() - 40))
        avail_h = max(50.0, float(self.height() - 85))
        viewport_dim = min(avail_w, avail_h)
        self.zoom = (viewport_dim * 0.72) / max_dim
        self.update()

    # -------------------------------------------------------------------------
    # Projection & Mathematics
    # -------------------------------------------------------------------------

    def _project(self, pt: tuple[float, float, float]) -> tuple[float, float, float]:
        """Project a 3D world point (x, y, z) in mm to 2D screen coords (u, v) and camera depth y2."""
        x, y, z = pt
        rad_yaw = math.radians(self.yaw)
        rad_pitch = math.radians(self.pitch)

        # 1. Rotate around Z (Yaw)
        x1 = x * math.cos(rad_yaw) - y * math.sin(rad_yaw)
        y1 = x * math.sin(rad_yaw) + y * math.cos(rad_yaw)
        z1 = z

        # 2. Rotate around camera horizontal axis (Pitch)
        y2 = y1 * math.cos(rad_pitch) - z1 * math.sin(rad_pitch)
        z2 = y1 * math.sin(rad_pitch) + z1 * math.cos(rad_pitch)

        # 3. Viewport center + pan
        cx = self.width() / 2.0 + self.pan_x
        # Center in the available space above the bottom HUD card
        hud_clearance = 56.0 if self.model else 0.0
        cy = ((self.height() - hud_clearance) / 2.0 + 8.0) + self.pan_y

        u = cx + x1 * self.zoom
        v = cy - z2 * self.zoom
        return u, v, y2

    # -------------------------------------------------------------------------
    # Mouse Interaction
    # -------------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._mouse_pressed = True
        self._last_mouse_pos = event.pos()
        self._mouse_button = event.button()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._mouse_pressed:
            dx = event.position().x() - self._last_mouse_pos.x()
            dy = event.position().y() - self._last_mouse_pos.y()
            self._last_mouse_pos = event.pos()

            if self._mouse_button == Qt.MouseButton.LeftButton:
                # Orbit rotation
                self.yaw = (self.yaw + dx * 0.6) % 360.0
                self.pitch = max(-89.0, min(89.0, self.pitch + dy * 0.6))
                self.update()
            elif self._mouse_button in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
                # Pan translation
                self.pan_x += dx
                self.pan_y += dy
                self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._mouse_pressed = False
        self._mouse_button = Qt.MouseButton.NoButton
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.fit_to_view()
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 0.85
        self.zoom = max(5.0, min(5000.0, self.zoom * factor))
        self.update()
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.model and (self.pan_x == 0.0 and self.pan_y == 0.0):
            self.fit_to_view()
        else:
            self.update()

    # -------------------------------------------------------------------------
    # Painting & 3D Scene Rendering
    # -------------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 1. Viewport Background Gradient
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor("#14161d"))
        grad.setColorAt(1.0, QColor("#1c1f28"))
        painter.fillRect(self.rect(), grad)

        if not self.model or not self.model.polygons:
            # Draw placeholder message
            painter.setPen(QColor("#7e889b"))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.placeholder_text)
            return

        # 2. Draw PCB Ground Grid at Z=0
        self._draw_pcb_grid(painter)

        # 3. Draw Solder Pads at Z=0
        self._draw_pads(painter)

        # 4. Draw Shaded 3D Component Faces (Painter's Algorithm Depth-Sorted)
        self._draw_3d_mesh(painter)

        # 5. Draw 3D Dimension Overlays (Lines, Ticks, Text)
        if self.show_dimensions:
            self._draw_3d_dimension_lines(painter)

        # 6. Draw Real-World Dimensions HUD Badge Card
        self._draw_hud_badge(painter)

    def _draw_pcb_grid(self, p: QPainter) -> None:
        """Render a millimeter coordinate reference grid on the PCB surface (Z=0)."""
        ref_size = max(self.model.length_mm, self.model.width_mm, 2.0) * 1.6
        step = 0.5 if ref_size < 5.0 else (1.0 if ref_size < 20.0 else 2.5)
        n_lines = int(ref_size / step) + 1
        max_extent = n_lines * step

        # Grid lines
        p.setPen(QPen(QColor(48, 58, 72, 130), 1))
        for i in range(-n_lines, n_lines + 1):
            val = i * step
            # Lines parallel to Y
            u1, v1, _ = self._project((val, -max_extent, 0.0))
            u2, v2, _ = self._project((val, max_extent, 0.0))
            p.drawLine(QPointF(u1, v1), QPointF(u2, v2))
            # Lines parallel to X
            u3, v3, _ = self._project((-max_extent, val, 0.0))
            u4, v4, _ = self._project((max_extent, val, 0.0))
            p.drawLine(QPointF(u3, v3), QPointF(u4, v4))

        # Coordinate axes at origin (0, 0, 0)
        u0, v0, _ = self._project((0.0, 0.0, 0.0))
        # X axis (Red/Pink)
        ux, vx, _ = self._project((step * 1.5, 0.0, 0.0))
        p.setPen(QPen(QColor(235, 75, 75, 180), 1.5))
        p.drawLine(QPointF(u0, v0), QPointF(ux, vx))
        # Y axis (Green)
        uy, vy, _ = self._project((0.0, step * 1.5, 0.0))
        p.setPen(QPen(QColor(60, 200, 100, 180), 1.5))
        p.drawLine(QPointF(u0, v0), QPointF(uy, vy))

    def _draw_pads(self, p: QPainter) -> None:
        """Draw copper solder pads on the PCB surface."""
        if not self.model or not self.model.pads:
            return

        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        for pad in self.model.pads:
            hw = pad.width / 2.0
            hh = pad.height / 2.0
            rot_rad = math.radians(pad.rotation)
            cos_r = math.cos(rot_rad)
            sin_r = math.sin(rot_rad)

            corners_local = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
            corners_world = [
                (
                    pad.x + lx * cos_r - ly * sin_r,
                    pad.y + lx * sin_r + ly * cos_r,
                    0.0,
                )
                for lx, ly in corners_local
            ]

            proj_pts = [self._project(c)[:2] for c in corners_world]
            qpoly = QPolygonF([QPointF(u, v) for u, v in proj_pts])

            # Pad fill and border
            p.setBrush(QBrush(QColor(205, 105, 45, 235)))  # Copper
            p.setPen(QPen(QColor(245, 160, 80), 1.5))
            p.drawPolygon(qpoly)

            # Pad designator label
            if pad.designator:
                up, vp, _ = self._project((pad.x, pad.y, 0.0))
                p.setPen(QColor("#ffffff"))
                p.drawText(QRectF(up - 15, vp - 10, 30, 20), Qt.AlignmentFlag.AlignCenter, pad.designator)

    def _draw_3d_mesh(self, p: QPainter) -> None:
        """Render depth-sorted 3D polygons with directional Lambertian lighting."""
        if not self.model:
            return

        # Light vector shining from front-top-right
        lx, ly, lz = 0.35, -0.55, 0.75
        l_len = math.sqrt(lx * lx + ly * ly + lz * lz)
        lx, ly, lz = lx / l_len, ly / l_len, lz / l_len

        faces_to_render = []

        if self._planar_groups:
            # Render using coplanar surface grouping:
            # For each coplanar group, calculate collective camera depth,
            # and sort faces by area descending so base surfaces are drawn before surface details/text.
            for g in self._planar_groups:
                g_items = []
                all_y2 = []
                for poly in g:
                    proj_pts = [self._project(pt) for pt in poly.points]
                    for pt in proj_pts:
                        all_y2.append(pt[2])

                    # Two-sided Lambertian lighting calculation
                    nx, ny, nz = poly.normal
                    dot = nx * lx + ny * ly + nz * lz
                    intensity = abs(dot)
                    factor = 0.42 + 0.58 * intensity  # Ambient 0.42, Diffuse 0.58

                    r = int(min(255, poly.color[0] * factor))
                    g_col = int(min(255, poly.color[1] * factor))
                    b = int(min(255, poly.color[2] * factor))
                    color = QColor(r, g_col, b)
                    g_items.append((proj_pts, color))

                avg_g_depth = sum(all_y2) / len(all_y2) if all_y2 else 0.0
                n_items = len(g_items)

                # rank 0 = largest area (base surface), rank N-1 = smallest area (text/markings)
                # In Painter's algorithm (reverse=True), higher depth renders first.
                for rank, (proj_pts, color) in enumerate(g_items):
                    bias = (n_items - 1 - rank) * 1e-4
                    sort_depth = avg_g_depth + bias
                    faces_to_render.append((sort_depth, proj_pts, color))
        else:
            for poly in self.model.polygons:
                proj_pts = [self._project(pt) for pt in poly.points]
                avg_depth = sum(pt[2] for pt in proj_pts) / len(proj_pts)

                nx, ny, nz = poly.normal
                dot = nx * lx + ny * ly + nz * lz
                intensity = abs(dot)
                factor = 0.42 + 0.58 * intensity

                r = int(min(255, poly.color[0] * factor))
                g_col = int(min(255, poly.color[1] * factor))
                b = int(min(255, poly.color[2] * factor))
                color = QColor(r, g_col, b)

                faces_to_render.append((avg_depth, proj_pts, color))

        # Painter's Algorithm: Furthest from camera rendered first
        faces_to_render.sort(key=lambda x: x[0], reverse=True)

        for depth, proj_pts, color in faces_to_render:
            qpoly = QPolygonF([QPointF(pt[0], pt[1]) for pt in proj_pts])
            p.setBrush(QBrush(color))
            # Subtle CAD edge outline
            edge_r = max(0, color.red() - 35)
            edge_g = max(0, color.green() - 35)
            edge_b = max(0, color.blue() - 35)
            p.setPen(QPen(QColor(edge_r, edge_g, edge_b, 190), 1))
            p.drawPolygon(qpoly)

    def _draw_3d_dimension_lines(self, p: QPainter) -> None:
        """Render 3D dimension arrows, dashed extension lines, and metric labels."""
        if not self.model or self.model.length_mm <= 0:
            return

        min_x, min_y, min_z = self.model.bbox_min
        max_x, max_y, max_z = self.model.bbox_max
        len_x = self.model.length_mm
        len_y = self.model.width_mm
        len_z = self.model.height_mm
        standoff = self.model.standoff_mm

        # Dynamic offset based on component size
        span = max(len_x, len_y, len_z)
        offset = max(0.4, span * 0.25)

        # 1. Length dimension along X (in front, offset along -Y)
        self._render_leader_line(
            p,
            start_pt=(min_x, min_y, 0.0),
            end_pt=(max_x, min_y, 0.0),
            label=f"L: {len_x:.2f} mm",
            offset_3d=(0.0, -offset, 0.0),
            color=QColor("#4da6ff"),
        )

        # 2. Width dimension along Y (to the right, offset along +X)
        self._render_leader_line(
            p,
            start_pt=(max_x, min_y, 0.0),
            end_pt=(max_x, max_y, 0.0),
            label=f"W: {len_y:.2f} mm",
            offset_3d=(offset, 0.0, 0.0),
            color=QColor("#38d9a9"),
        )

        # 3. Height dimension along Z (vertical, offset along -X)
        self._render_leader_line(
            p,
            start_pt=(min_x, min_y, standoff),
            end_pt=(min_x, min_y, standoff + len_z),
            label=f"H: {len_z:.2f} mm",
            offset_3d=(-offset, 0.0, 0.0),
            color=QColor("#ff922b"),
        )

        # 4. Standoff clearance above PCB (when > 0.05 mm)
        if standoff > 0.05:
            self._render_leader_line(
                p,
                start_pt=(max_x, max_y, 0.0),
                end_pt=(max_x, max_y, standoff),
                label=f"Standoff: {standoff:.2f} mm",
                offset_3d=(offset * 0.8, offset * 0.8, 0.0),
                color=QColor("#e599f7"),
            )

    def _render_leader_line(
        self,
        p: QPainter,
        start_pt: tuple[float, float, float],
        end_pt: tuple[float, float, float],
        label: str,
        offset_3d: tuple[float, float, float],
        color: QColor,
    ) -> None:
        """Helper to render an engineering dimension leader line with tick marks."""
        s = (start_pt[0] + offset_3d[0], start_pt[1] + offset_3d[1], start_pt[2] + offset_3d[2])
        e = (end_pt[0] + offset_3d[0], end_pt[1] + offset_3d[1], end_pt[2] + offset_3d[2])
        u1, v1, _ = self._project(s)
        u2, v2, _ = self._project(e)

        # Extension dashed lines connecting from component edge
        p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 110), 1, Qt.PenStyle.DashLine))
        if any(offset_3d):
            o1, o2, _ = self._project(start_pt)
            p.drawLine(QPointF(o1, o2), QPointF(u1, v1))
            o3, o4, _ = self._project(end_pt)
            p.drawLine(QPointF(o3, o4), QPointF(u2, v2))

        # Main dimension line
        p.setPen(QPen(color, 1.5))
        p.drawLine(QPointF(u1, v1), QPointF(u2, v2))

        # Perpendicular end ticks
        dx, dy = u2 - u1, v2 - v1
        dist = math.hypot(dx, dy)
        if dist > 6:
            nx, ny = -dy / dist * 4, dx / dist * 4
            p.drawLine(QPointF(u1 - nx, v1 - ny), QPointF(u1 + nx, v1 + ny))
            p.drawLine(QPointF(u2 - nx, v2 - ny), QPointF(u2 + nx, v2 + ny))

        # Dimension pill badge
        mx, my = (u1 + u2) / 2.0, (v1 + v2) / 2.0
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(label) + 10
        th = fm.height() + 2

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(16, 20, 28, 225)))
        p.drawRoundedRect(QRectF(mx - tw / 2.0, my - th / 2.0, tw, th), 4, 4)

        p.setPen(color)
        p.drawText(
            QRectF(mx - tw / 2.0, my - th / 2.0, tw, th),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )

    def _draw_hud_badge(self, p: QPainter) -> None:
        """Render real-world dimensions HUD badge card in bottom viewport area."""
        if not self.model:
            return

        badge_w = min(290, self.width() - 24)
        badge_h = 58
        badge_x = 12
        badge_y = self.height() - badge_h - 10

        # Card background with border
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(18, 22, 30, 235)))
        p.drawRoundedRect(badge_x, badge_y, badge_w, badge_h, 6, 6)

        p.setPen(QPen(QColor(55, 70, 92, 220), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(badge_x, badge_y, badge_w, badge_h, 6, 6)

        # Card Title
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QColor("#74c0fc"))
        p.drawText(badge_x + 10, badge_y + 16, "3D Real-World Dimensions")

        # Dimension values in 2 columns
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor("#dce2f0"))
        col1_x = badge_x + 10
        col2_x = badge_x + int(badge_w / 2) + 5

        p.drawText(col1_x, badge_y + 34, f"L: {self.model.length_mm:.2f} mm")
        p.drawText(col2_x, badge_y + 34, f"W: {self.model.width_mm:.2f} mm")
        p.drawText(col1_x, badge_y + 50, f"H: {self.model.height_mm:.2f} mm")
        p.drawText(col2_x, badge_y + 50, f"Standoff: {self.model.standoff_mm:.2f} mm")
