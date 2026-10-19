# -*- coding: utf-8 -*-
from __future__ import annotations
import array
import logging
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
    QMatrix4x4,
    QVector3D,
    QVector4D,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtOpenGL import QOpenGLShaderProgram, QOpenGLShader, QOpenGLBuffer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QButtonGroup,
)
from ..altium.footprint_3d import Footprint3DModel, Pad3D, Polygon3D, MeshBatch3D

logger = logging.getLogger(__name__)


def _get_pad_profile_2d(pad: Pad3D) -> list[tuple[float, float]]:
    """
    Generate an ordered Counter-Clockwise (CCW) 2D polygon profile of the pad in local coordinates (centered at 0, 0).
    Supports Altium pad shapes:
    - ROUND / OVAL / OBLONG (Shape 1): Circle (when W == H) or Oblong/Capsule with semicircular ends (when W != H).
    - ROUNDED_RECTANGLE (Shape 9): Rectangle with corner rounding based on corner_radius_percentage.
    - OCTAGONAL (Shape 3): Octagon with 45-degree chamfered corners.
    - RECTANGULAR (Shape 2): Standard 4-corner rectangle.
    """
    hw = pad.width / 2.0
    hh = pad.height / 2.0
    shape = getattr(pad, "shape", "RECTANGULAR").upper()
    pts: list[tuple[float, float]] = []

    if shape in ("ROUND", "OVAL", "OBLONG"):
        if abs(pad.width - pad.height) < 1e-4:
            # Circle
            r = min(hw, hh)
            steps = 24
            for i in range(steps):
                th = 2.0 * math.pi * i / steps
                pts.append((r * math.cos(th), r * math.sin(th)))
        elif hh > hw:
            # Taller than wide: semicircles on top/bottom, straight sides on left/right
            r = hw
            steps = 8
            pts.append((hw, -hh + r))
            pts.append((hw, hh - r))
            for i in range(1, steps):
                th = math.pi * i / steps
                pts.append((r * math.cos(th), (hh - r) + r * math.sin(th)))
            pts.append((-hw, hh - r))
            pts.append((-hw, -hh + r))
            for i in range(1, steps):
                th = math.pi + math.pi * i / steps
                pts.append((r * math.cos(th), (-hh + r) + r * math.sin(th)))
        else:
            # Wider than tall: semicircles on left/right, straight sides on top/bottom
            r = hh
            steps = 8
            pts.append((-hw + r, hh))
            pts.append((hw - r, hh))
            for i in range(1, steps):
                th = math.pi / 2.0 - math.pi * i / steps
                pts.append(((hw - r) + r * math.cos(th), r * math.sin(th)))
            pts.append((hw - r, -hh))
            pts.append((-hw + r, -hh))
            for i in range(1, steps):
                th = -math.pi / 2.0 - math.pi * i / steps
                pts.append(((-hw + r) + r * math.cos(th), r * math.sin(th)))

    elif shape == "ROUNDED_RECTANGLE":
        cr_pct = getattr(pad, "corner_radius_percentage", 25.0) or 25.0
        ratio = max(0.0, min(1.0, cr_pct / 100.0))
        r = min(hw, hh) * ratio
        if r < 1e-4:
            pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        else:
            steps = 5
            pts.append((-hw + r, hh))
            pts.append((hw - r, hh))
            for i in range(1, steps):
                th = math.pi / 2.0 - (math.pi / 2.0) * i / steps
                pts.append(((hw - r) + r * math.cos(th), (hh - r) + r * math.sin(th)))
            pts.append((hw, hh - r))
            pts.append((hw, -hh + r))
            for i in range(1, steps):
                th = 0.0 - (math.pi / 2.0) * i / steps
                pts.append(((hw - r) + r * math.cos(th), (-hh + r) + r * math.sin(th)))
            pts.append((hw - r, -hh))
            pts.append((-hw + r, -hh))
            for i in range(1, steps):
                th = -math.pi / 2.0 - (math.pi / 2.0) * i / steps
                pts.append(((-hw + r) + r * math.cos(th), (-hh + r) + r * math.sin(th)))
            pts.append((-hw, -hh + r))
            pts.append((-hw, hh - r))
            for i in range(1, steps):
                th = math.pi - (math.pi / 2.0) * i / steps
                pts.append(((-hw + r) + r * math.cos(th), (hh - r) + r * math.sin(th)))

    elif shape == "OCTAGONAL":
        chamfer = min(hw, hh) / 2.0
        pts = [
            (-hw + chamfer, hh), (hw - chamfer, hh),
            (hw, hh - chamfer), (hw, -hh + chamfer),
            (hw - chamfer, -hh), (-hw + chamfer, -hh),
            (-hw, -hh + chamfer), (-hw, hh - chamfer)
        ]
    else:
        pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]

    n = len(pts)
    if n >= 3:
        sa = 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
        if sa < 0:
            pts.reverse()
    return pts


def _ray_segment_intersect(
    ray_dx: float, ray_dy: float, x1: float, y1: float, x2: float, y2: float
) -> float | None:
    """Find distance t > 0 along ray (t*ray_dx, t*ray_dy) intersecting segment (x1, y1)-(x2, y2)."""
    dx = x2 - x1
    dy = y2 - y1
    det = ray_dx * dy - ray_dy * dx
    if abs(det) < 1e-9:
        return None
    t = (x1 * dy - y1 * dx) / det
    u = (x1 * ray_dy - y1 * ray_dx) / det
    if t > 1e-6 and -1e-6 <= u <= 1.0 + 1e-6:
        return t
    return None


def _ray_polygon_intersect(
    ray_dx: float, ray_dy: float, polygon: list[tuple[float, float]]
) -> tuple[float, float] | None:
    """Find intersection point of ray from origin with a star-convex 2D polygon."""
    n = len(polygon)
    for i in range(n):
        nxt = (i + 1) % n
        t = _ray_segment_intersect(
            ray_dx, ray_dy, polygon[i][0], polygon[i][1], polygon[nxt][0], polygon[nxt][1]
        )
        if t is not None:
            return (t * ray_dx, t * ray_dy)
    return None


def _get_annular_pad_profiles(
    pad: Pad3D, outer_poly: list[tuple[float, float]], r_hole: float, num_circle_pts: int = 24
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """
    Generate synchronized CCW outer and inner hole profiles for a through-hole pad.
    Both profiles share the exact same radial ray angles so they form an annular quad strip.
    """
    angles: list[float] = []
    for x, y in outer_poly:
        a = math.atan2(y, x)
        if a < 0:
            a += 2.0 * math.pi
        angles.append(a)

    for k in range(num_circle_pts):
        angles.append(2.0 * math.pi * k / float(num_circle_pts))

    angles.sort()
    unique_angles: list[float] = []
    for a in angles:
        if not unique_angles or (a - unique_angles[-1]) > 0.015:
            unique_angles.append(a)
    if len(unique_angles) > 1 and (2.0 * math.pi - unique_angles[-1] + unique_angles[0]) < 0.015:
        unique_angles.pop()

    loc_out: list[tuple[float, float]] = []
    loc_in: list[tuple[float, float]] = []
    for a in unique_angles:
        rdx, rdy = math.cos(a), math.sin(a)
        pt_out = _ray_polygon_intersect(rdx, rdy, outer_poly)
        if pt_out is None:
            pt_out = ((pad.width / 2.0) * rdx, (pad.height / 2.0) * rdy)
        loc_out.append(pt_out)
        loc_in.append((r_hole * rdx, r_hole * rdy))

    return loc_out, loc_in


class Footprint3DViewer(QOpenGLWidget):
    """
    Hardware-accelerated 3D CAD viewport for Altium footprint models using QOpenGLWidget.
    Features OpenCASCADE geometry, hardware depth testing (Z-Buffer), smooth mouse orbit,
    pan, zoom, preset views, PCB ground plane, solder pads, 3D dimension arrows, and HUD card.
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

        # OpenGL pipeline state
        self._gl_program: QOpenGLShaderProgram | None = None
        self._gl_funcs = None
        self._gl_initialized: bool = False
        self._vbo: QOpenGLBuffer | None = None

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

        self.btn_bottom = QPushButton("Bottom")
        self.btn_bottom.setToolTip("Bottom View (XY) - Inspect Bottom Layer & Solder Pads")
        self.btn_bottom.setStyleSheet(btn_style)
        self.btn_bottom.clicked.connect(self.view_bottom)
        toolbar_layout.addWidget(self.btn_bottom)

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
                    # Check if normals are parallel in the SAME direction and lie on the same plane
                    if dot_n > 0.999:
                        rd = rnx * rep.points[0][0] + rny * rep.points[0][1] + rnz * rep.points[0][2]
                        if abs(d - rd) < 0.01:  # within 10 microns
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

    def view_bottom(self) -> None:
        self.yaw = 0.0
        self.pitch = -89.0
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
    # OpenGL Pipeline & Projection
    # -------------------------------------------------------------------------

    def initializeGL(self) -> None:
        """Initialize OpenGL shaders, hardware depth testing, VBO buffer, and viewport parameters."""
        try:
            self._gl_funcs = self.context().functions()
            self._gl_funcs.glEnable(0x0B71)  # GL_DEPTH_TEST
            self._gl_funcs.glDepthFunc(0x0203)  # GL_LEQUAL

            self._gl_program = QOpenGLShaderProgram(self)
            v_shader = """#version 120
attribute vec3 a_pos;
attribute vec3 a_norm;
uniform mat4 u_mvp;
uniform mat4 u_rot;
uniform vec3 u_color;
varying vec3 v_norm;
varying vec3 v_color;

void main() {
    gl_Position = u_mvp * vec4(a_pos, 1.0);
    v_norm = (u_rot * vec4(a_norm, 0.0)).xyz;
    v_color = u_color;
}
"""
            f_shader = """#version 120
varying vec3 v_norm;
varying vec3 v_color;

void main() {
    vec3 n = normalize(v_norm);
    if (length(v_norm) < 0.01) n = vec3(0.0, 0.0, 1.0);
    vec3 v = vec3(0.0, 0.0, 1.0);

    // Three-point camera-space studio lighting
    vec3 l1 = normalize(vec3(0.40, 0.55, 0.72));
    vec3 l2 = normalize(vec3(-0.45, -0.30, 0.50));
    vec3 l3 = normalize(vec3(0.0, 0.85, 0.35));

    float d1 = max(dot(n, l1), 0.0);
    float d2 = max(dot(n, l2), 0.0) * 0.40;
    float d3 = max(dot(n, l3), 0.0) * 0.25;
    float back1 = max(dot(-n, l1), 0.0) * 0.25;
    float diffuse = max(d1, back1) + d2 + d3;

    // Specular Blinn-Phong highlight
    vec3 h1 = normalize(l1 + v);
    float spec = pow(max(dot(n, h1), 0.0), 28.0) * 0.38;

    // Subtle edge rim light / Fresnel sheen
    float fresnel = pow(1.0 - abs(dot(n, v)), 3.0) * 0.16;

    // Minimum albedo clamp: lift dark CAD colors (e.g. black IC epoxy resin) to visible dark charcoal
    vec3 albedo = max(v_color, vec3(0.20, 0.22, 0.26));

    float light = clamp(0.42 + 0.58 * diffuse, 0.0, 1.0);
    vec3 col = albedo * light + vec3(spec + fresnel);
    gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
"""
            self._gl_program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, v_shader)
            self._gl_program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, f_shader)
            self._gl_program.link()

            self._vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            self._vbo.create()
            self._gl_initialized = True
        except Exception as exc:
            logger.debug(f"OpenGL shader initialization warning: {exc}")
            self._gl_initialized = False

    def resizeGL(self, w: int, h: int) -> None:
        if self._gl_funcs:
            self._gl_funcs.glViewport(0, 0, w, h)

    def _calc_mvp_matrix(self) -> QMatrix4x4:
        """Calculate the camera Model-View-Projection matrix for 3D rendering."""
        mvp = QMatrix4x4()
        half_w = (self.width() / 2.0) / max(1.0, self.zoom)
        half_h = (self.height() / 2.0) / max(1.0, self.zoom)
        mvp.ortho(-half_w, half_w, -half_h, half_h, -2000.0, 2000.0)

        # Center in available space above the bottom HUD card
        hud_clearance = 56.0 if self.model else 0.0
        cy_offset = ((self.height() - hud_clearance) / 2.0 + 8.0) - (self.height() / 2.0)

        mvp.translate(self.pan_x / max(1.0, self.zoom), (-self.pan_y - cy_offset) / max(1.0, self.zoom), 0.0)
        mvp.rotate(self.pitch - 90.0, 1.0, 0.0, 0.0)
        mvp.rotate(-self.yaw, 0.0, 0.0, 1.0)
        return mvp

    def _ensure_mesh_batches(self) -> list[MeshBatch3D]:
        """Ensure the current model has pre-triangulated vertex/normal batches for OpenGL."""
        if not self.model:
            return []
        if self.model.mesh_batches:
            return self.model.mesh_batches

        batches_by_color: dict[tuple[int, int, int], tuple[list[float], list[float]]] = {}
        for poly in self.model.polygons:
            c_key = poly.color
            if c_key not in batches_by_color:
                batches_by_color[c_key] = ([], [])
            v_list, n_list = batches_by_color[c_key]
            if len(poly.points) == 3:
                for p in poly.points:
                    v_list.extend(p)
                    n_list.extend(poly.normal)
            elif len(poly.points) > 3:
                p0 = poly.points[0]
                for i in range(1, len(poly.points) - 1):
                    p1 = poly.points[i]
                    p2 = poly.points[i + 1]
                    v_list.extend(p0)
                    v_list.extend(p1)
                    v_list.extend(p2)
                    n_list.extend(poly.normal)
                    n_list.extend(poly.normal)
                    n_list.extend(poly.normal)

        self.model.mesh_batches = [
            MeshBatch3D(
                vertices=v,
                normals=n,
                color=(c[0] / 255.0, c[1] / 255.0, c[2] / 255.0),
                count=len(v) // 3,
            )
            for c, (v, n) in batches_by_color.items()
        ]
        return self.model.mesh_batches

    def _project(self, pt: tuple[float, float, float]) -> tuple[float, float, float]:
        """Project a 3D world point (x, y, z) in mm to 2D screen coords (u, v) and camera depth."""
        mvp = self._calc_mvp_matrix()
        v = mvp.map(QVector4D(pt[0], pt[1], pt[2], 1.0))
        u = (v.x() + 1.0) * self.width() / 2.0
        v_screen = (1.0 - v.y()) * self.height() / 2.0
        return u, v_screen, v.z()

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
                self.yaw = (self.yaw - dx * 0.6) % 360.0
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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.model:
            self.fit_to_view()

    # -------------------------------------------------------------------------
    # Painting & 3D Scene Rendering
    # -------------------------------------------------------------------------

    def _render_pads_gl(self, stride: int) -> None:
        """Render 3D copper solder pads extruded with 0.1mm thickness downwards from Z=0 to Z=-0.1mm."""
        if not self.model or not self.model.pads or not self._vbo:
            return

        pad_verts = []
        for pad in self.model.pads:
            rot_rad = math.radians(pad.rotation)
            cos_r = math.cos(rot_rad)
            sin_r = math.sin(rot_rad)
            local_pts = _get_pad_profile_2d(pad)

            z_top = getattr(pad, "z_top", 0.0)
            z_bot = getattr(pad, "z_bottom", -0.1)

            has_hole = (
                getattr(pad, "is_thru_hole", False)
                and getattr(pad, "hole_diameter", 0.0) > 0.05
            )
            r_hole = (pad.hole_diameter / 2.0) if has_hole else 0.0

            if has_hole and r_hole < min(pad.width, pad.height) / 2.0:
                loc_out, loc_in = _get_annular_pad_profiles(pad, local_pts, r_hole)
                # Outer barrel radius for the plated through-hole tube wall
                t_wall = min(0.06, (min(pad.width, pad.height) / 2.0 - r_hole) * 0.4)
                r_barrel = r_hole + max(0.02, t_wall)
                ratio_bar = r_barrel / r_hole if r_hole > 1e-6 else 1.0
                loc_bar = [(xi * ratio_bar, yi * ratio_bar) for xi, yi in loc_in]

                z_top_pad = getattr(pad, "z_top", 0.0)
                z_top_shelf = z_top_pad - 0.1
                z_bot_pad = -1.0  # -1.0 mm board bottom surface
                z_bot_shelf = z_bot_pad + 0.1  # -0.9 mm

                top_out = [
                    (pad.x + lx * cos_r - ly * sin_r, pad.y + lx * sin_r + ly * cos_r, z_top_pad)
                    for lx, ly in loc_out
                ]
                top_in = [
                    (pad.x + lx * cos_r - ly * sin_r, pad.y + lx * sin_r + ly * cos_r, z_top_pad)
                    for lx, ly in loc_in
                ]
                shelf_top_out = [
                    (pad.x + lx * cos_r - ly * sin_r, pad.y + lx * sin_r + ly * cos_r, z_top_shelf)
                    for lx, ly in loc_out
                ]
                shelf_top_bar = [
                    (pad.x + lx * cos_r - ly * sin_r, pad.y + lx * sin_r + ly * cos_r, z_top_shelf)
                    for lx, ly in loc_bar
                ]
                shelf_bot_bar = [
                    (pad.x + lx * cos_r - ly * sin_r, pad.y + lx * sin_r + ly * cos_r, z_bot_shelf)
                    for lx, ly in loc_bar
                ]
                shelf_bot_out = [
                    (pad.x + lx * cos_r - ly * sin_r, pad.y + lx * sin_r + ly * cos_r, z_bot_shelf)
                    for lx, ly in loc_out
                ]
                bot_out = [
                    (pad.x + lx * cos_r - ly * sin_r, pad.y + lx * sin_r + ly * cos_r, z_bot_pad)
                    for lx, ly in loc_out
                ]
                bot_in = [
                    (pad.x + lx * cos_r - ly * sin_r, pad.y + lx * sin_r + ly * cos_r, z_bot_pad)
                    for lx, ly in loc_in
                ]

                n_pts = len(top_out)

                # 1. Top face annular ring (normal 0, 0, 1)
                for i in range(n_pts):
                    nxt = (i + 1) % n_pts
                    pad_verts.extend(top_out[i]); pad_verts.extend((0.0, 0.0, 1.0))
                    pad_verts.extend(top_out[nxt]); pad_verts.extend((0.0, 0.0, 1.0))
                    pad_verts.extend(top_in[nxt]); pad_verts.extend((0.0, 0.0, 1.0))

                    pad_verts.extend(top_out[i]); pad_verts.extend((0.0, 0.0, 1.0))
                    pad_verts.extend(top_in[nxt]); pad_verts.extend((0.0, 0.0, 1.0))
                    pad_verts.extend(top_in[i]); pad_verts.extend((0.0, 0.0, 1.0))

                # 2. Top pad outer vertical side walls (z_top_pad to z_top_shelf)
                for i in range(n_pts):
                    nxt = (i + 1) % n_pts
                    edge_x = top_out[nxt][0] - top_out[i][0]
                    edge_y = top_out[nxt][1] - top_out[i][1]
                    edge_len = math.sqrt(edge_x * edge_x + edge_y * edge_y)
                    if edge_len > 1e-6:
                        nx = edge_y / edge_len
                        ny = -edge_x / edge_len
                    else:
                        nx, ny = 1.0, 0.0
                    p0 = top_out[i]
                    p1 = top_out[nxt]
                    p2 = shelf_top_out[nxt]
                    p3 = shelf_top_out[i]
                    for p in [p0, p1, p2, p0, p2, p3]:
                        pad_verts.extend(p)
                        pad_verts.extend((nx, ny, 0.0))

                # 3. Top pad bottom shelf (Z = z_top_shelf, normal 0, 0, -1)
                for i in range(n_pts):
                    nxt = (i + 1) % n_pts
                    pad_verts.extend(shelf_top_out[i]); pad_verts.extend((0.0, 0.0, -1.0))
                    pad_verts.extend(shelf_top_bar[nxt]); pad_verts.extend((0.0, 0.0, -1.0))
                    pad_verts.extend(shelf_top_out[nxt]); pad_verts.extend((0.0, 0.0, -1.0))

                    pad_verts.extend(shelf_top_out[i]); pad_verts.extend((0.0, 0.0, -1.0))
                    pad_verts.extend(shelf_top_bar[i]); pad_verts.extend((0.0, 0.0, -1.0))
                    pad_verts.extend(shelf_top_bar[nxt]); pad_verts.extend((0.0, 0.0, -1.0))

                # 4. Outer cylindrical barrel of the plated tube (z_top_shelf to z_bot_shelf, outward radial normals)
                for i in range(n_pts):
                    nxt = (i + 1) % n_pts
                    dx_i = shelf_top_bar[i][0] - pad.x
                    dy_i = shelf_top_bar[i][1] - pad.y
                    l_i = math.sqrt(dx_i * dx_i + dy_i * dy_i) or 1.0
                    nx_i, ny_i = dx_i / l_i, dy_i / l_i

                    dx_nxt = shelf_top_bar[nxt][0] - pad.x
                    dy_nxt = shelf_top_bar[nxt][1] - pad.y
                    l_nxt = math.sqrt(dx_nxt * dx_nxt + dy_nxt * dy_nxt) or 1.0
                    nx_nxt, ny_nxt = dx_nxt / l_nxt, dy_nxt / l_nxt

                    p0 = shelf_top_bar[i]
                    p1 = shelf_top_bar[nxt]
                    p2 = shelf_bot_bar[nxt]
                    p3 = shelf_bot_bar[i]

                    pad_verts.extend(p0); pad_verts.extend((nx_i, ny_i, 0.0))
                    pad_verts.extend(p1); pad_verts.extend((nx_nxt, ny_nxt, 0.0))
                    pad_verts.extend(p2); pad_verts.extend((nx_nxt, ny_nxt, 0.0))

                    pad_verts.extend(p0); pad_verts.extend((nx_i, ny_i, 0.0))
                    pad_verts.extend(p2); pad_verts.extend((nx_nxt, ny_nxt, 0.0))
                    pad_verts.extend(p3); pad_verts.extend((nx_i, ny_i, 0.0))

                # 5. Bottom pad top shelf (Z = z_bot_shelf, normal 0, 0, 1)
                for i in range(n_pts):
                    nxt = (i + 1) % n_pts
                    pad_verts.extend(shelf_bot_out[i]); pad_verts.extend((0.0, 0.0, 1.0))
                    pad_verts.extend(shelf_bot_out[nxt]); pad_verts.extend((0.0, 0.0, 1.0))
                    pad_verts.extend(shelf_bot_bar[nxt]); pad_verts.extend((0.0, 0.0, 1.0))

                    pad_verts.extend(shelf_bot_out[i]); pad_verts.extend((0.0, 0.0, 1.0))
                    pad_verts.extend(shelf_bot_bar[nxt]); pad_verts.extend((0.0, 0.0, 1.0))
                    pad_verts.extend(shelf_bot_bar[i]); pad_verts.extend((0.0, 0.0, 1.0))

                # 6. Bottom pad outer vertical side walls (z_bot_shelf to z_bot_pad)
                for i in range(n_pts):
                    nxt = (i + 1) % n_pts
                    edge_x = shelf_bot_out[nxt][0] - shelf_bot_out[i][0]
                    edge_y = shelf_bot_out[nxt][1] - shelf_bot_out[i][1]
                    edge_len = math.sqrt(edge_x * edge_x + edge_y * edge_y)
                    if edge_len > 1e-6:
                        nx = edge_y / edge_len
                        ny = -edge_x / edge_len
                    else:
                        nx, ny = 1.0, 0.0
                    p0 = shelf_bot_out[i]
                    p1 = shelf_bot_out[nxt]
                    p2 = bot_out[nxt]
                    p3 = bot_out[i]
                    for p in [p0, p1, p2, p0, p2, p3]:
                        pad_verts.extend(p)
                        pad_verts.extend((nx, ny, 0.0))

                # 7. Bottom face annular ring (Z = z_bot_pad, normal 0, 0, -1)
                for i in range(n_pts):
                    nxt = (i + 1) % n_pts
                    pad_verts.extend(bot_out[i]); pad_verts.extend((0.0, 0.0, -1.0))
                    pad_verts.extend(bot_in[nxt]); pad_verts.extend((0.0, 0.0, -1.0))
                    pad_verts.extend(bot_out[nxt]); pad_verts.extend((0.0, 0.0, -1.0))

                    pad_verts.extend(bot_out[i]); pad_verts.extend((0.0, 0.0, -1.0))
                    pad_verts.extend(bot_in[i]); pad_verts.extend((0.0, 0.0, -1.0))
                    pad_verts.extend(bot_in[nxt]); pad_verts.extend((0.0, 0.0, -1.0))

                # 8. Inner tube wall (hollow bore spanning z_top_pad down to z_bot_pad, inward radial normals)
                for i in range(n_pts):
                    nxt = (i + 1) % n_pts
                    dx_i = top_in[i][0] - pad.x
                    dy_i = top_in[i][1] - pad.y
                    l_i = math.sqrt(dx_i * dx_i + dy_i * dy_i) or 1.0
                    in_nx_i, in_ny_i = -dx_i / l_i, -dy_i / l_i

                    dx_nxt = top_in[nxt][0] - pad.x
                    dy_nxt = top_in[nxt][1] - pad.y
                    l_nxt = math.sqrt(dx_nxt * dx_nxt + dy_nxt * dy_nxt) or 1.0
                    in_nx_nxt, in_ny_nxt = -dx_nxt / l_nxt, -dy_nxt / l_nxt

                    p0 = top_in[i]
                    p1 = top_in[nxt]
                    p2 = bot_in[nxt]
                    p3 = bot_in[i]

                    pad_verts.extend(p0); pad_verts.extend((in_nx_i, in_ny_i, 0.0))
                    pad_verts.extend(p2); pad_verts.extend((in_nx_nxt, in_ny_nxt, 0.0))
                    pad_verts.extend(p1); pad_verts.extend((in_nx_nxt, in_ny_nxt, 0.0))

                    pad_verts.extend(p0); pad_verts.extend((in_nx_i, in_ny_i, 0.0))
                    pad_verts.extend(p3); pad_verts.extend((in_nx_i, in_ny_i, 0.0))
                    pad_verts.extend(p2); pad_verts.extend((in_nx_nxt, in_ny_nxt, 0.0))

            else:
                # Solid pad without hole (SMD)
                top_pts = [
                    (pad.x + lx * cos_r - ly * sin_r, pad.y + lx * sin_r + ly * cos_r, z_top)
                    for lx, ly in local_pts
                ]
                bot_pts = [
                    (pad.x + lx * cos_r - ly * sin_r, pad.y + lx * sin_r + ly * cos_r, z_bot)
                    for lx, ly in local_pts
                ]
                center_top = (pad.x, pad.y, z_top)
                center_bot = (pad.x, pad.y, z_bot)

                n_pts = len(top_pts)

                # 1. Top face fan triangulation (normal 0, 0, 1)
                for i in range(n_pts):
                    nxt = (i + 1) % n_pts
                    pad_verts.extend(center_top)
                    pad_verts.extend((0.0, 0.0, 1.0))
                    pad_verts.extend(top_pts[i])
                    pad_verts.extend((0.0, 0.0, 1.0))
                    pad_verts.extend(top_pts[nxt])
                    pad_verts.extend((0.0, 0.0, 1.0))

                # 2. Bottom face fan triangulation (normal 0, 0, -1)
                for i in range(n_pts):
                    nxt = (i + 1) % n_pts
                    pad_verts.extend(center_bot)
                    pad_verts.extend((0.0, 0.0, -1.0))
                    pad_verts.extend(bot_pts[nxt])
                    pad_verts.extend((0.0, 0.0, -1.0))
                    pad_verts.extend(bot_pts[i])
                    pad_verts.extend((0.0, 0.0, -1.0))

                # 3. Vertical side walls connecting Z=0 to Z=-0.1mm
                for i in range(n_pts):
                    nxt = (i + 1) % n_pts
                    edge_x = top_pts[nxt][0] - top_pts[i][0]
                    edge_y = top_pts[nxt][1] - top_pts[i][1]
                    edge_len = math.sqrt(edge_x * edge_x + edge_y * edge_y)
                    if edge_len > 1e-6:
                        nx = edge_y / edge_len
                        ny = -edge_x / edge_len
                    else:
                        nx, ny = 1.0, 0.0

                    p0 = top_pts[i]
                    p1 = top_pts[nxt]
                    p2 = bot_pts[nxt]
                    p3 = bot_pts[i]

                    for p in [p0, p1, p2, p0, p2, p3]:
                        pad_verts.extend(p)
                        pad_verts.extend((nx, ny, 0.0))

        if pad_verts:
            arr = array.array("f", pad_verts)
            self._vbo.bind()
            self._vbo.allocate(arr.tobytes(), len(arr.tobytes()))
            if self._gl_program:
                self._gl_program.setUniformValue("u_color", QVector3D(0.85, 0.48, 0.22))  # Metallic copper pad
                self._gl_program.enableAttributeArray("a_pos")
                self._gl_program.setAttributeBuffer("a_pos", 0x1406, 0, 3, stride)  # GL_FLOAT
                self._gl_program.enableAttributeArray("a_norm")
                self._gl_program.setAttributeBuffer("a_norm", 0x1406, 12, 3, stride)
            if self._gl_funcs:
                self._gl_funcs.glDrawArrays(0x0004, 0, len(pad_verts) // 6)
            if self._gl_program:
                self._gl_program.disableAttributeArray("a_pos")
                self._gl_program.disableAttributeArray("a_norm")
            self._vbo.release()

    def _render_layer_graphics_gl(self, stride: int) -> None:
        """Render 2D layer graphics (Silkscreen white, Mechanical cyan) with physical line thickness."""
        if not self.model or (not self.model.lines and not self.model.arcs) or not self._vbo:
            return

        batches_by_color: dict[tuple[float, float, float], list[float]] = {}

        # 1. Tracks & Regions as ribbon quads
        for line in self.model.lines:
            c_key = line.color
            if c_key not in batches_by_color:
                batches_by_color[c_key] = []
            dx = line.x2 - line.x1
            dy = line.y2 - line.y1
            length = math.sqrt(dx * dx + dy * dy)
            if length < 1e-6:
                continue
            hw = max(0.04, line.width / 2.0)
            nx = -dy / length * hw
            ny = dx / length * hw
            z = getattr(line, "z", 0.002)
            norm_z = -1.0 if z < -0.5 else 1.0
            c0 = (line.x1 + nx, line.y1 + ny, z)
            c1 = (line.x2 + nx, line.y2 + ny, z)
            c2 = (line.x2 - nx, line.y2 - ny, z)
            c3 = (line.x1 - nx, line.y1 - ny, z)
            for p in [c0, c1, c2, c0, c2, c3]:
                batches_by_color[c_key].extend(p)
                batches_by_color[c_key].extend((0.0, 0.0, norm_z))

        # 2. Arcs as curved ribbon quads
        for arc in self.model.arcs:
            c_key = arc.color
            if c_key not in batches_by_color:
                batches_by_color[c_key] = []
            hw = max(0.04, arc.width / 2.0)
            r_in = max(0.01, arc.radius - hw)
            r_out = arc.radius + hw
            a_diff = (arc.angle_end - arc.angle_start) % 360.0
            if abs(a_diff) < 0.01:
                a_diff = 360.0
            steps = max(8, int(a_diff / 12.0))
            z = getattr(arc, "z", 0.002)
            norm_z = -1.0 if z < -0.5 else 1.0
            for i in range(steps):
                th1 = math.radians(arc.angle_start + a_diff * i / steps)
                th2 = math.radians(arc.angle_start + a_diff * (i + 1) / steps)
                p_in1 = (arc.cx + r_in * math.cos(th1), arc.cy + r_in * math.sin(th1), z)
                p_out1 = (arc.cx + r_out * math.cos(th1), arc.cy + r_out * math.sin(th1), z)
                p_in2 = (arc.cx + r_in * math.cos(th2), arc.cy + r_in * math.sin(th2), z)
                p_out2 = (arc.cx + r_out * math.cos(th2), arc.cy + r_out * math.sin(th2), z)
                for p in [p_in1, p_out1, p_out2, p_in1, p_out2, p_in2]:
                    batches_by_color[c_key].extend(p)
                    batches_by_color[c_key].extend((0.0, 0.0, norm_z))

        for color, verts in batches_by_color.items():
            if not verts:
                continue
            arr = array.array("f", verts)
            self._vbo.bind()
            self._vbo.allocate(arr.tobytes(), len(arr.tobytes()))
            if self._gl_program:
                self._gl_program.setUniformValue("u_color", QVector3D(*color))
                self._gl_program.enableAttributeArray("a_pos")
                self._gl_program.setAttributeBuffer("a_pos", 0x1406, 0, 3, stride)
                self._gl_program.enableAttributeArray("a_norm")
                self._gl_program.setAttributeBuffer("a_norm", 0x1406, 12, 3, stride)
            if self._gl_funcs:
                self._gl_funcs.glDrawArrays(0x0004, 0, len(verts) // 6)
            if self._gl_program:
                self._gl_program.disableAttributeArray("a_pos")
                self._gl_program.disableAttributeArray("a_norm")
            self._vbo.release()

    def paintGL(self) -> None:
        """Render the 3D scene using hardware OpenGL depth testing and 2D overlays."""
        if not self._gl_initialized:
            self.initializeGL()

        # 1. Clear background color and depth buffer
        if self._gl_funcs:
            self._gl_funcs.glClearColor(0.08, 0.09, 0.12, 1.0)
            self._gl_funcs.glClear(0x00004000 | 0x00000100)  # GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT

        if not self.model or not self.model.polygons:
            p = QPainter(self)
            p.setPen(QColor("#7e889b"))
            p.setFont(QFont("Segoe UI", 12))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.placeholder_text)
            p.end()
            return

        mvp = self._calc_mvp_matrix()
        rot = QMatrix4x4()
        rot.rotate(self.pitch - 90.0, 1.0, 0.0, 0.0)
        rot.rotate(-self.yaw, 0.0, 0.0, 1.0)

        batches = self._ensure_mesh_batches()

        # 2. Hardware 3D rendering with OpenGL depth testing
        if self._gl_funcs and self._gl_program and self._gl_program.isLinked() and self._vbo and batches:
            self._gl_funcs.glEnable(0x0B71)  # GL_DEPTH_TEST
            self._gl_funcs.glDepthFunc(0x0203)  # GL_LEQUAL
            self._gl_program.bind()
            self._gl_program.setUniformValue("u_mvp", mvp)
            self._gl_program.setUniformValue("u_rot", rot)

            stride = 6 * 4  # 6 floats (x, y, z, nx, ny, nz) * 4 bytes = 24 bytes

            # Render 3D copper solder pads (0.0 to -0.1mm)
            self._render_pads_gl(stride)

            # Render 2D footprint layer graphics (Silkscreen white, Mechanical cyan)
            self._render_layer_graphics_gl(stride)

            # Render 3D component geometry batches
            for b in batches:
                if b.count <= 0:
                    continue
                interleaved = []
                for i in range(b.count):
                    interleaved.extend([b.vertices[i * 3], b.vertices[i * 3 + 1], b.vertices[i * 3 + 2]])
                    interleaved.extend([b.normals[i * 3], b.normals[i * 3 + 1], b.normals[i * 3 + 2]])
                arr = array.array("f", interleaved)

                self._vbo.bind()
                self._vbo.allocate(arr.tobytes(), len(arr.tobytes()))
                self._gl_program.setUniformValue("u_color", QVector3D(*b.color))
                self._gl_program.enableAttributeArray("a_pos")
                self._gl_program.setAttributeBuffer("a_pos", 0x1406, 0, 3, stride)  # GL_FLOAT
                self._gl_program.enableAttributeArray("a_norm")
                self._gl_program.setAttributeBuffer("a_norm", 0x1406, 12, 3, stride)
                self._gl_funcs.glDrawArrays(0x0004, 0, b.count)  # GL_TRIANGLES
                self._gl_program.disableAttributeArray("a_pos")
                self._gl_program.disableAttributeArray("a_norm")
                self._vbo.release()

            self._gl_program.release()
            self._gl_funcs.glDisable(0x0B71)

        # 3. Draw 2D overlays on top: PCB coordinate lines, pad labels, dimension arrows, HUD
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        self._draw_pad_labels(p)
        if self.show_dimensions:
            self._draw_3d_dimension_lines(p)
        self._draw_hud_badge(p)

        p.end()

    def _draw_pad_labels(self, p: QPainter) -> None:
        """Draw pad designator labels ("1", "2", etc.) at pad centers."""
        if not self.model or not self.model.pads:
            return
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QColor("#ffffff"))
        z_lbl = 0.005 if self.pitch >= 0.0 else -1.005
        for pad in self.model.pads:
            if pad.designator:
                up, vp, _ = self._project((pad.x, pad.y, z_lbl))
                p.drawText(QRectF(up - 15, vp - 10, 30, 20), Qt.AlignmentFlag.AlignCenter, pad.designator)

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
            rot_rad = math.radians(pad.rotation)
            cos_r = math.cos(rot_rad)
            sin_r = math.sin(rot_rad)

            corners_local = _get_pad_profile_2d(pad)
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

            # Draw drill hole circle if through-hole
            if getattr(pad, "is_thru_hole", False) and getattr(pad, "hole_diameter", 0.0) > 0.05:
                r_hole = pad.hole_diameter / 2.0
                hole_world = [
                    (
                        pad.x + r_hole * math.cos(2.0 * math.pi * k / 24.0),
                        pad.y + r_hole * math.sin(2.0 * math.pi * k / 24.0),
                        0.001,
                    )
                    for k in range(24)
                ]
                hole_proj = [self._project(c)[:2] for c in hole_world]
                p.setBrush(QBrush(QColor("#14171f")))  # PCB dark substrate
                p.setPen(QPen(QColor("#00bcd4"), 1.0))  # Cyan drill circle
                p.drawPolygon(QPolygonF([QPointF(u, v) for u, v in hole_proj]))

            # Pad designator label
            if pad.designator:
                up, vp, _ = self._project((pad.x, pad.y, 0.0))
                p.setPen(QColor("#ffffff"))
                p.drawText(QRectF(up - 15, vp - 10, 30, 20), Qt.AlignmentFlag.AlignCenter, pad.designator)

    def _draw_3d_mesh(self, p: QPainter) -> None:
        """Render depth-sorted 3D polygons with camera-space back-face culling and Lambertian lighting."""
        if not self.model:
            return

        rad_yaw = math.radians(self.yaw)
        rad_pitch = math.radians(self.pitch)
        cyaw, syaw = math.cos(rad_yaw), math.sin(rad_yaw)
        cpitch, spitch = math.cos(rad_pitch), math.sin(rad_pitch)

        # Light vector shining from front-top-right
        lx, ly, lz = 0.35, -0.55, 0.75
        l_len = math.sqrt(lx * lx + ly * ly + lz * lz)
        lx, ly, lz = lx / l_len, ly / l_len, lz / l_len

        faces_to_render = []

        if self._planar_groups:
            # Render using coplanar surface grouping:
            # For each coplanar group, test group normal against camera view direction (Back-Face Culling),
            # calculate collective camera depth, and sort faces by area descending so base surfaces
            # are drawn before surface details/text.
            for g in self._planar_groups:
                rep = g[0]
                rnx, rny, rnz = rep.normal
                # Normal transform into camera coordinates
                rnx1 = rnx * cyaw - rny * syaw
                rny1 = rnx * syaw + rny * cyaw
                rny2 = rny1 * cpitch - rnz * spitch

                # Back-face culling: camera looks into +Y. If normal points along +Y (away from camera), cull.
                if rny2 >= -1e-4:
                    continue

                g_items = []
                all_y2 = []
                for poly in g:
                    proj_pts = [self._project(pt) for pt in poly.points]
                    for pt in proj_pts:
                        all_y2.append(pt[2])

                    # One-sided Lambertian lighting calculation
                    nx, ny, nz = poly.normal
                    dot = nx * lx + ny * ly + nz * lz
                    intensity = max(0.0, dot)
                    factor = 0.40 + 0.60 * intensity

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
                nx, ny, nz = poly.normal
                nx1 = nx * cyaw - ny * syaw
                ny1 = nx * syaw + ny * cyaw
                ny2 = ny1 * cpitch - nz * spitch

                # Back-face culling
                if ny2 >= -1e-4:
                    continue

                proj_pts = [self._project(pt) for pt in poly.points]
                avg_depth = sum(pt[2] for pt in proj_pts) / len(proj_pts)

                dot = nx * lx + ny * ly + nz * lz
                intensity = max(0.0, dot)
                factor = 0.40 + 0.60 * intensity

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
