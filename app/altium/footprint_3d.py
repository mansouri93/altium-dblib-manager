# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
import logging
import math
from pathlib import Path
import re
from typing import Any
import zlib
import olefile
import pyaltiumlib
from ..config import to_absolute_path

logger = logging.getLogger(__name__)


@dataclass
class Pad3D:
    """Represents a PCB footprint solder pad in 3D space on the PCB plane."""
    x: float  # mm
    y: float  # mm
    width: float  # mm
    height: float  # mm
    rotation: float = 0.0  # degrees
    designator: str = ""
    is_thru_hole: bool = False
    hole_diameter: float = 0.0  # mm


@dataclass
class Polygon3D:
    """A 3D polygon face for shaded rendering and wireframe drawing."""
    points: list[tuple[float, float, float]]  # [(x, y, z), ...] in mm
    normal: tuple[float, float, float]  # unit normal (nx, ny, nz)
    color: tuple[int, int, int]  # RGB (0-255)
    center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    area: float = 0.0  # surface area in mm^2 for coplanar detail layering


@dataclass
class Body3DInfo:
    """Parameters extracted from Altium ComponentBody record for placing a 3D model."""
    model_id: str = ""
    name: str = ""
    stream_name: str = ""
    x_2d: float = 0.0          # mm
    y_2d: float = 0.0          # mm
    rot_2d: float = 0.0        # degrees (counter-clockwise planar rotation)
    rot_x: float = 0.0         # degrees Euler X
    rot_y: float = 0.0         # degrees Euler Y
    rot_z: float = 0.0         # degrees Euler Z
    dz: float = 0.0            # mm vertical offset
    standoff: float = 0.0      # mm standoff height
    overall_height: float = 0.0 # mm overall height
    body_color: tuple[int, int, int] | None = None


@dataclass
class Footprint3DModel:
    """Complete 3D model representation of a footprint component."""
    name: str
    length_mm: float = 0.0  # X dimension (طول)
    width_mm: float = 0.0   # Y dimension (عرض)
    height_mm: float = 0.0  # Z dimension (ارتفاع)
    standoff_mm: float = 0.0  # Height above PCB surface (ارتفاع از سطح بورد)
    bbox_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    polygons: list[Polygon3D] = field(default_factory=list)
    pads: list[Pad3D] = field(default_factory=list)
    has_3d_model: bool = False
    source_step_name: str = ""


def _parse_val_with_unit(s: str) -> float:
    """Parse Altium dimension string with mil or mm unit to float millimeters."""
    if not s:
        return 0.0
    s = s.strip().lower()
    try:
        if s.endswith("mil"):
            return float(s[:-3].strip()) * 0.0254
        elif s.endswith("mm"):
            return float(s[:-2].strip())
        elif s.endswith("in") or s.endswith("inch"):
            return float(s.replace("inch", "").replace("in", "").strip()) * 25.4
        elif s.endswith("um"):
            return float(s[:-2].strip()) * 0.001
        return float(s)
    except Exception:
        return 0.0


def _rotate_point(pt: tuple[float, float, float], rx: float, ry: float, rz: float) -> tuple[float, float, float]:
    """Rotate a 3D point by Euler angles rx, ry, rz in degrees (order: X then Y then Z)."""
    x, y, z = pt
    # Rot X
    if rx != 0.0:
        rad_x = math.radians(rx)
        cx, sx = math.cos(rad_x), math.sin(rad_x)
        y, z = y * cx - z * sx, y * sx + z * cx

    # Rot Y
    if ry != 0.0:
        rad_y = math.radians(ry)
        cy, sy = math.cos(rad_y), math.sin(rad_y)
        x, z = x * cy + z * sy, -x * sy + z * cy

    # Rot Z
    if rz != 0.0:
        rad_z = math.radians(rz)
        cz, sz = math.cos(rad_z), math.sin(rad_z)
        x, y = x * cz - y * sz, x * sz + y * cz

    return (x, y, z)


def _transform_point(
    pt: tuple[float, float, float],
    scale: float,
    rx: float,
    ry: float,
    rz: float,
    rot_2d: float,
    x_2d: float,
    y_2d: float,
    dz: float,
) -> tuple[float, float, float]:
    """
    Applies the full Altium transformation pipeline to a STEP vertex:
    1. Scale (e.g. inch -> mm)
    2. Local 3D Euler rotation (X -> Y -> Z)
    3. Planar 2D rotation on PCB
    4. Translation by (x_2d, y_2d, dz)
    """
    # 1. Scale
    p_sc = (pt[0] * scale, pt[1] * scale, pt[2] * scale)

    # 2. 3D Rotation (Euler XYZ)
    x, y, z = _rotate_point(p_sc, rx, ry, rz)

    # 3. 2D Rotation (counter-clockwise around Z)
    if rot_2d != 0.0:
        rad_2d = math.radians(rot_2d)
        c2, s2 = math.cos(rad_2d), math.sin(rad_2d)
        x, y = x * c2 - y * s2, x * s2 + y * c2

    # 4. 2D Translation & vertical elevation
    return (x + x_2d, y + y_2d, z + dz)


def _calc_polygon_normal_and_area(points: list[tuple[float, float, float]]) -> tuple[tuple[float, float, float], float]:
    """Calculate outward unit normal vector and surface area using Newell's method for arbitrary 3D polygon."""
    if len(points) < 3:
        return (0.0, 0.0, 1.0), 0.0
    nx, ny, nz = 0.0, 0.0, 0.0
    n = len(points)
    for i in range(n):
        curr = points[i]
        nxt = points[(i + 1) % n]
        nx += (curr[1] - nxt[1]) * (curr[2] + nxt[2])
        ny += (curr[2] - nxt[2]) * (curr[0] + nxt[0])
        nz += (curr[0] - nxt[0]) * (curr[1] + nxt[1])
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    area = 0.5 * length
    if length > 1e-6:
        return (nx / length, ny / length, nz / length), area
    return (0.0, 0.0, 1.0), area


def _calc_polygon_normal(points: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Calculate outward normal vector using Newell's method for arbitrary 3D polygon."""
    return _calc_polygon_normal_and_area(points)[0]


class Footprint3DParser:
    """Extracts and parses embedded 3D STEP models and copper pads from Altium .PcbLib files."""

    def __init__(self) -> None:
        self._cache: dict[str, Footprint3DModel] = {}

    def get_model(self, file_path: str | Path, part_name: str) -> Footprint3DModel:
        """Retrieve or parse 3D footprint model with bounding box and dimensions."""
        abs_path = to_absolute_path(file_path)
        if not abs_path or not abs_path.exists():
            return Footprint3DModel(name=part_name, has_3d_model=False)

        cache_key = f"{str(abs_path)}::{part_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        model = self._extract_model(abs_path, part_name)
        self._cache[cache_key] = model
        return model

    def _extract_model(self, pcb_path: Path, part_name: str) -> Footprint3DModel:
        """Parse OLE compound file and extract 3D STEP geometry and pads."""
        # 1. Extract pads from pyaltiumlib
        pads = self._extract_pads(pcb_path, part_name)

        # 2. Check OLE compound file
        try:
            ole = olefile.OleFileIO(str(pcb_path))
        except Exception as exc:
            logger.warning(f"Failed to open OLE file {pcb_path}: {exc}")
            return self._generate_fallback_model(part_name, pads)

        try:
            # Extract all 3D bodies configured on this footprint
            bodies = self._extract_all_bodies(ole, part_name)

            if not bodies:
                # If no body records found, check if a single Model 0 stream exists
                model_streams = [
                    "/".join(s) for s in ole.listdir()
                    if len(s) == 3 and s[0] == "Library" and s[1] == "Models" and s[2].isdigit()
                ]
                if model_streams:
                    bodies.append(Body3DInfo(stream_name=model_streams[0]))
                else:
                    ole.close()
                    return self._generate_fallback_model(part_name, pads)

            # Decompress and parse unique STEP model streams
            step_cache: dict[str, tuple[float, list[tuple[list[tuple[float, float, float]], tuple[int, int, int] | None]]]] = {}
            for body in bodies:
                s_name = body.stream_name
                if s_name not in step_cache:
                    s_parts = s_name.split("/")
                    if ole.exists(s_parts):
                        try:
                            raw_data = ole.openstream(s_parts).read()
                            step_text = ""
                            try:
                                step_text = zlib.decompress(raw_data).decode("latin1", errors="ignore")
                            except Exception:
                                step_text = raw_data.decode("latin1", errors="ignore")

                            if "ISO-10303-21" in step_text:
                                unit_sc, raw_polys = self._parse_step_polygons(step_text)
                                step_cache[s_name] = (unit_sc, raw_polys)
                        except Exception as exc:
                            logger.debug(f"Error reading model stream {s_name}: {exc}")

            ole.close()

            if not step_cache:
                return self._generate_fallback_model(part_name, pads)

            # Construct transformed 3D polygon meshes across all bodies
            model = self._build_model_from_bodies(part_name, bodies, step_cache, pads)
            return model
        except Exception as exc:
            logger.error(f"Error extracting 3D model for {part_name} in {pcb_path}: {exc}", exc_info=True)
            try:
                ole.close()
            except Exception:
                pass
            return self._generate_fallback_model(part_name, pads)

    def _extract_pads(self, pcb_path: Path, part_name: str) -> list[Pad3D]:
        """Extract copper pads from footprint using pyaltiumlib."""
        pads: list[Pad3D] = []
        try:
            lib = pyaltiumlib.read(str(pcb_path))
            part = lib.get_part(part_name)
            if not part or not hasattr(part, "Records"):
                return pads

            for record in part.Records:
                if "PcbPad" in str(type(record)):
                    loc = getattr(record, "location", None)
                    if hasattr(loc, "x") and hasattr(loc, "y"):
                        lx_mm = float(loc.x) * 0.0254
                        ly_mm = float(loc.y) * 0.0254
                    elif isinstance(loc, (list, tuple)) and len(loc) >= 2:
                        lx_mm = float(loc[0]) * 0.0254
                        ly_mm = float(loc[1]) * 0.0254
                    else:
                        lx_mm, ly_mm = 0.0, 0.0

                    sz = getattr(record, "size_top", None)
                    if hasattr(sz, "x") and hasattr(sz, "y"):
                        pw_mm = abs(float(sz.x)) * 0.0254
                        ph_mm = abs(float(sz.y)) * 0.0254
                    elif isinstance(sz, (list, tuple)) and len(sz) >= 2:
                        pw_mm = abs(float(sz[0])) * 0.0254
                        ph_mm = abs(float(sz[1])) * 0.0254
                    else:
                        pw_mm, ph_mm = 1.0, 1.0

                    rot = float(getattr(record, "rotation", 0.0) or 0.0)
                    des = str(getattr(record, "designator", "") or "")
                    hole_sz_mil = float(getattr(record, "hole_size", 0.0) or 0.0)
                    hole_dia_mm = hole_sz_mil * 0.0254
                    is_thru = hole_dia_mm > 0.05

                    pads.append(
                        Pad3D(
                            x=round(lx_mm, 4),
                            y=round(ly_mm, 4),
                            width=round(pw_mm, 4),
                            height=round(ph_mm, 4),
                            rotation=rot,
                            designator=des,
                            is_thru_hole=is_thru,
                            hole_diameter=round(hole_dia_mm, 4),
                        )
                    )
        except Exception as exc:
            logger.debug(f"Error extracting pads for {part_name}: {exc}")
        return pads

    def _extract_all_bodies(self, ole: olefile.OleFileIO, part_name: str) -> list[Body3DInfo]:
        """
        Extract all 3D body definitions with exact 2D placement, planar rotation,
        Euler 3D rotation, and standoff heights from the footprint's Data stream.
        """
        # 1. Map MODELID to Library/Models/<index> stream
        model_id_to_stream: dict[str, str] = {}
        if ole.exists(["Library", "Models", "Data"]):
            try:
                m_data = ole.openstream(["Library", "Models", "Data"]).read().decode("latin1", errors="ignore")
                for i, m in enumerate(re.finditer(r"\|ID=([^|]+)", m_data)):
                    model_id_to_stream[m.group(1).strip().upper()] = f"Library/Models/{i}"
            except Exception as exc:
                logger.debug(f"Error reading Library/Models/Data: {exc}")

        # 2. Locate the footprint's Data stream
        target_stream = None
        if ole.exists([part_name, "Data"]):
            target_stream = [part_name, "Data"]
        else:
            p_clean = part_name.strip().lower()
            for s in ole.listdir():
                if len(s) == 2 and s[1] == "Data" and s[0] not in ("Library", "FileVersionInfo", "FileHeader"):
                    if s[0].strip().lower() == p_clean:
                        target_stream = s
                        break
            if not target_stream:
                for s in ole.listdir():
                    if len(s) == 2 and s[1] == "Data" and s[0] not in ("Library", "FileVersionInfo", "FileHeader"):
                        target_stream = s
                        break

        if not target_stream:
            return []

        # 3. Parse individual component body records
        try:
            data = ole.openstream(target_stream).read()
        except Exception as exc:
            logger.debug(f"Failed reading target stream {target_stream}: {exc}")
            return []

        idx = 0
        bodies: list[Body3DInfo] = []
        while idx < len(data) - 4:
            p = data.find(b"|", idx)
            if p == -1:
                break
            end = data.find(b"\x00", p)
            if end == -1:
                end = len(data)
            chunk = data[p:end].decode("latin1", errors="ignore")
            if "MODELID" in chunk:
                m_id = re.search(r"MODELID=([^|]+)", chunk)
                model_id = m_id.group(1).strip() if m_id else ""
                m_name = re.search(r"MODEL\.NAME=([^|]+)", chunk)
                name = m_name.group(1).strip() if m_name else ""
                m_2dx = re.search(r"MODEL\.2D\.X=([^\s|]+)", chunk)
                m_2dy = re.search(r"MODEL\.2D\.Y=([^\s|]+)", chunk)
                m_2dr = re.search(r"MODEL\.2D\.ROTATION=([^\s|]+)", chunk)
                m_rx = re.search(r"MODEL\.3D\.ROTX=([^\s|]+)", chunk)
                m_ry = re.search(r"MODEL\.3D\.ROTY=([^\s|]+)", chunk)
                m_rz = re.search(r"MODEL\.3D\.ROTZ=([^\s|]+)", chunk)
                m_dz = re.search(r"MODEL\.3D\.DZ=([^\s|]+)", chunk)
                m_st = re.search(r"STANDOFFHEIGHT=([^\s|]+)", chunk)
                m_h = re.search(r"OVERALLHEIGHT=([^\s|]+)", chunk)
                m_c = re.search(r"BODYCOLOR3D=([^\s|]+)", chunk)

                stream_name = model_id_to_stream.get(model_id.upper())
                if not stream_name:
                    for s in ole.listdir():
                        if len(s) == 3 and s[0] == "Library" and s[1] == "Models" and s[2].isdigit():
                            stream_name = "/".join(s)
                            break

                col = None
                if m_c:
                    try:
                        c_int = int(m_c.group(1))
                        b = (c_int >> 16) & 0xFF
                        g = (c_int >> 8) & 0xFF
                        r = c_int & 0xFF
                        col = (r, g, b)
                    except Exception:
                        pass

                bodies.append(
                    Body3DInfo(
                        model_id=model_id,
                        name=name,
                        stream_name=stream_name or "Library/Models/0",
                        x_2d=_parse_val_with_unit(m_2dx.group(1)) if m_2dx else 0.0,
                        y_2d=_parse_val_with_unit(m_2dy.group(1)) if m_2dy else 0.0,
                        rot_2d=float(m_2dr.group(1)) if m_2dr else 0.0,
                        rot_x=float(m_rx.group(1)) if m_rx else 0.0,
                        rot_y=float(m_ry.group(1)) if m_ry else 0.0,
                        rot_z=float(m_rz.group(1)) if m_rz else 0.0,
                        dz=_parse_val_with_unit(m_dz.group(1)) if m_dz else 0.0,
                        standoff=_parse_val_with_unit(m_st.group(1)) if m_st else 0.0,
                        overall_height=_parse_val_with_unit(m_h.group(1)) if m_h else 0.0,
                        body_color=col,
                    )
                )
            idx = end + 1

        return bodies

    def _parse_step_polygons(
        self, step_text: str
    ) -> tuple[float, list[tuple[list[tuple[float, float, float]], tuple[int, int, int] | None]]]:
        """Parse STEP AP214 text entities, assembly placements, and native CAD face colors."""
        # 1. Detect unit scale
        unit_scale = 1.0
        if re.search(r"CONVERSION_BASED_UNIT\s*\(\s*'(?:INCH|inch)'", step_text, re.IGNORECASE) or \
           re.search(r"LENGTH_MEASURE\s*\(\s*25\.4", step_text):
            unit_scale = 25.4
        elif re.search(r"SI_UNIT\s*\(\s*\$\s*,\s*\.METRE\.\s*\)", step_text) and not re.search(r"\.MILLI\.", step_text):
            unit_scale = 1000.0

        # 2. Cartesian Points (pre-scaled to mm)
        re_cp = re.compile(r"#(\d+)\s*=\s*CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*([eE0-9\.\-\+,\s]+)\)\s*\)")
        points: dict[int, tuple[float, float, float]] = {}
        for m in re_cp.finditer(step_text):
            coords = [float(x.strip()) * unit_scale for x in m.group(2).split(",") if x.strip()]
            if len(coords) == 3:
                points[int(m.group(1))] = (coords[0], coords[1], coords[2])

        # 3. Directions
        re_dir = re.compile(r"#(\d+)\s*=\s*DIRECTION\s*\(\s*'[^']*'\s*,\s*\(\s*([eE0-9\.\-\+,\s]+)\)\s*\)")
        dirs: dict[int, tuple[float, float, float]] = {}
        for m in re_dir.finditer(step_text):
            coords = [float(x.strip()) for x in m.group(2).split(",") if x.strip()]
            if len(coords) == 3:
                dirs[int(m.group(1))] = (coords[0], coords[1], coords[2])

        # 4. Axes
        re_ax = re.compile(r"#(\d+)\s*=\s*AXIS2_PLACEMENT_3D\s*\(\s*'[^']*'\s*,\s*#(\d+)(?:\s*,\s*#(\d+)\s*,\s*#(\d+))?\s*\)")
        axes: dict[int, tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]] = {}
        for m in re_ax.finditer(step_text):
            aid = int(m.group(1))
            p_id = int(m.group(2))
            z_id = int(m.group(3)) if m.group(3) else None
            x_id = int(m.group(4)) if m.group(4) else None
            orig = points.get(p_id, (0.0, 0.0, 0.0))
            z = dirs.get(z_id, (0.0, 0.0, 1.0)) if z_id else (0.0, 0.0, 1.0)
            x = dirs.get(x_id, (1.0, 0.0, 0.0)) if x_id else (1.0, 0.0, 0.0)

            def norm(v: tuple[float, float, float]) -> tuple[float, float, float]:
                l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
                return (v[0] / l, v[1] / l, v[2] / l) if l > 1e-6 else (0.0, 0.0, 0.0)

            zn = norm(z)
            xn = norm(x)
            yn = norm((
                zn[1] * xn[2] - zn[2] * xn[1],
                zn[2] * xn[0] - zn[0] * xn[2],
                zn[0] * xn[1] - zn[1] * xn[0],
            ))
            axes[aid] = (orig, xn, yn, zn)

        # 5. Transformations
        re_trans = re.compile(r"#(\d+)\s*=\s*ITEM_DEFINED_TRANSFORMATION\s*\(\s*[^,]*,\s*[^,]*,\s*#(\d+)\s*,\s*#(\d+)\s*\)")
        trans_map = {int(m.group(1)): (int(m.group(2)), int(m.group(3))) for m in re_trans.finditer(step_text)}

        # 6. Representation relationships
        rep_edges: list[tuple[int, int, int | None]] = []
        for m in re.finditer(r"#(\d+)\s*=\s*\(([\s\S]*?)\)\s*;", step_text):
            content = m.group(2)
            m_rr = re.search(r"REPRESENTATION_RELATIONSHIP\s*\(\s*[^,]*,\s*[^,]*,\s*#(\d+)\s*,\s*#(\d+)\s*\)", content)
            m_trans = re.search(r"REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION\s*\(\s*#(\d+)\s*\)", content)
            if m_rr:
                rep_edges.append((int(m_rr.group(1)), int(m_rr.group(2)), int(m_trans.group(1)) if m_trans else None))

        equiv_reps: dict[int, set[int]] = {}
        for m in re.finditer(r"#(\d+)\s*=\s*SHAPE_REPRESENTATION_RELATIONSHIP\s*\(\s*'[^']*'\s*,\s*'[^']*'\s*,\s*#(\d+)\s*,\s*#(\d+)\s*\)", step_text):
            r1, r2 = int(m.group(2)), int(m.group(3))
            equiv_reps.setdefault(r1, set()).add(r2)
            equiv_reps.setdefault(r2, set()).add(r1)

        # 7. Geometry entities
        vertex_points = {int(m.group(1)): int(m.group(2)) for m in re.finditer(r"#(\d+)\s*=\s*VERTEX_POINT\s*\(\s*'[^']*'\s*,\s*#(\d+)\s*\)", step_text)}
        edge_curves = {int(m.group(1)): (int(m.group(2)), int(m.group(3))) for m in re.finditer(r"#(\d+)\s*=\s*EDGE_CURVE\s*\(\s*'[^']*'\s*,\s*#(\d+)\s*,\s*#(\d+)", step_text)}
        oriented_edges = {int(m.group(1)): (int(m.group(2)), m.group(3) == ".T.") for m in re.finditer(r"#(\d+)\s*=\s*ORIENTED_EDGE\s*\(\s*'[^']*'\s*,\s*\*,\s*\*,\s*#(\d+)\s*,\s*(\.[TF]\.)\s*\)", step_text)}
        edge_loops = {
            int(m.group(1)): [int(x.replace("#", "").strip()) for x in m.group(2).split(",") if x.strip()]
            for m in re.finditer(r"#(\d+)\s*=\s*EDGE_LOOP\s*\(\s*'[^']*'\s*,\s*\(([\s#\d,]+)\)\s*\)", step_text)
        }

        re_fob = re.compile(r"#(\d+)\s*=\s*FACE_OUTER_BOUND\s*\(\s*'[^']*'\s*,\s*#(\d+)")
        face_outer_bounds = {int(m.group(1)): int(m.group(2)) for m in re_fob.finditer(step_text)}

        re_fb = re.compile(r"#(\d+)\s*=\s*FACE_(?:OUTER_)?BOUND\s*\(\s*'[^']*'\s*,\s*#(\d+)")
        all_face_bounds = {int(m.group(1)): int(m.group(2)) for m in re_fb.finditer(step_text)}

        re_af = re.compile(r"#(\d+)\s*=\s*ADVANCED_FACE\s*\(\s*'[^']*'\s*,\s*\(([\s#\d,]+)\)")
        advanced_faces = {
            int(m.group(1)): [int(x.replace("#", "").strip()) for x in m.group(2).split(",") if x.strip()]
            for m in re_af.finditer(step_text)
        }

        shell_to_faces: dict[int, list[int]] = {}
        for m in re.finditer(r"#(\d+)\s*=\s*(?:CLOSED_SHELL|OPEN_SHELL)\s*\(\s*'[^']*'\s*,\s*\(([\s#\d,]+)\)", step_text):
            sid = int(m.group(1))
            fids = [int(x.replace("#", "").strip()) for x in m.group(2).split(",") if x.strip()]
            shell_to_faces[sid] = fids

        face_polygons: dict[int, list[tuple[float, float, float]]] = {}
        for fid, b_ids in advanced_faces.items():
            # Strictly prefer FACE_OUTER_BOUND over inner holes (FACE_BOUND)
            outer_bid = None
            for bid in b_ids:
                if bid in face_outer_bounds:
                    outer_bid = bid
                    break
            if outer_bid is None and b_ids:
                outer_bid = b_ids[0]

            if not outer_bid:
                continue

            lid = all_face_bounds.get(outer_bid)
            if not lid or lid not in edge_loops:
                continue

            pts: list[tuple[float, float, float]] = []
            for oe in edge_loops[lid]:
                if oe not in oriented_edges:
                    continue
                ec, forward = oriented_edges[oe]
                if ec not in edge_curves:
                    continue
                v1, v2 = edge_curves[ec]
                v_sel = v1 if forward else v2
                pt_id = vertex_points.get(v_sel)
                if pt_id and pt_id in points:
                    pts.append(points[pt_id])

            if len(pts) >= 3:
                face_polygons[fid] = pts

        # 8. Representations to items/shells/faces
        rep_to_faces: dict[int, list[int]] = {}
        for m in re.finditer(r"#(\d+)\s*=\s*(?:[A-Z0-9_]*SHAPE_REPRESENTATION)\s*\(\s*'[^']*'\s*,\s*\(([^)]+)\)", step_text):
            rid = int(m.group(1))
            items = [int(x) for x in re.findall(r"#(\d+)", m.group(2))]
            rep_fids: list[int] = []
            for itm in items:
                if itm in advanced_faces:
                    rep_fids.append(itm)
                if itm in shell_to_faces:
                    rep_fids.extend(shell_to_faces[itm])
                m_msb = re.search(rf"#{itm}\s*=\s*MANIFOLD_SOLID_BREP\s*\(\s*'[^']*'\s*,\s*#(\d+)\s*\)", step_text)
                if m_msb:
                    cs_id = int(m_msb.group(1))
                    if cs_id in shell_to_faces:
                        rep_fids.extend(shell_to_faces[cs_id])
                m_sbm = re.search(rf"#{itm}\s*=\s*SHELL_BASED_SURFACE_MODEL\s*\(\s*'[^']*'\s*,\s*\(([^)]+)\)\s*\)", step_text)
                if m_sbm:
                    for cs_id in [int(x) for x in re.findall(r"#(\d+)", m_sbm.group(1))]:
                        if cs_id in shell_to_faces:
                            rep_fids.extend(shell_to_faces[cs_id])
            if rep_fids:
                rep_to_faces[rid] = list(set(rep_fids))

        for r1, related in equiv_reps.items():
            for r2 in related:
                if r2 in rep_to_faces:
                    rep_to_faces.setdefault(r1, []).extend(rep_to_faces[r2])
                    rep_to_faces[r1] = list(set(rep_to_faces[r1]))

        # 9. Colors extraction from STYLED_ITEM and COLOUR_RGB
        entities: dict[int, tuple[str, str]] = {}
        for m in re.finditer(r"#(\d+)\s*=\s*([A-Z0-9_]+)\s*\(([\s\S]*?)\)\s*;", step_text):
            entities[int(m.group(1))] = (m.group(2), m.group(3))

        def get_color(ent_id: int) -> tuple[int, int, int] | None:
            visited = set()
            stack = [ent_id]
            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                if cur not in entities:
                    continue
                etype, args = entities[cur]
                if etype == "COLOUR_RGB":
                    parts = [p.strip() for p in args.split(",")]
                    if len(parts) >= 4:
                        try:
                            r, g, b = float(parts[1]), float(parts[2]), float(parts[3].rstrip(")"))
                            return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))
                        except Exception:
                            pass
                else:
                    refs = [int(x) for x in re.findall(r"#(\d+)", args)]
                    stack.extend(refs)
            return None

        styled_items: dict[int, tuple[int, int, int]] = {}
        for m in re.finditer(r"#(\d+)\s*=\s*STYLED_ITEM\s*\(\s*[^,]*,\s*\(([\s\S]*?)\)\s*,\s*#(\d+)\s*\)", step_text):
            style_ids = [int(x) for x in re.findall(r"#(\d+)", m.group(2))]
            target_id = int(m.group(3))
            for sid in style_ids:
                c = get_color(sid)
                if c:
                    styled_items[target_id] = c
                    break

        face_colors: dict[int, tuple[int, int, int]] = {}
        for fid in face_polygons:
            if fid in styled_items:
                face_colors[fid] = styled_items[fid]
            else:
                for sid, fids in shell_to_faces.items():
                    if fid in fids and sid in styled_items:
                        face_colors[fid] = styled_items[sid]
                        break

        for m in re.finditer(r"#(\d+)\s*=\s*MANIFOLD_SOLID_BREP\s*\(\s*'[^']*'\s*,\s*#(\d+)\s*\)", step_text):
            bid = int(m.group(1))
            sid = int(m.group(2))
            if bid in styled_items and sid in shell_to_faces:
                for fid in shell_to_faces[sid]:
                    if fid not in face_colors:
                        face_colors[fid] = styled_items[bid]

        def apply_transform(pt: tuple[float, float, float], trans_id: int) -> tuple[float, float, float]:
            if trans_id not in trans_map:
                return pt
            af_id, at_id = trans_map[trans_id]
            if af_id not in axes or at_id not in axes:
                return pt
            orig_f, xf, yf, zf = axes[af_id]
            orig_t, xt, yt, zt = axes[at_id]
            dx = pt[0] - orig_f[0]
            dy = pt[1] - orig_f[1]
            dz = pt[2] - orig_f[2]
            u = dx * xf[0] + dy * xf[1] + dz * xf[2]
            v = dx * yf[0] + dy * yf[1] + dz * yf[2]
            w = dx * zf[0] + dy * zf[1] + dz * zf[2]
            return (
                orig_t[0] + u * xt[0] + v * yt[0] + w * zt[0],
                orig_t[1] + u * xt[1] + v * yt[1] + w * zt[1],
                orig_t[2] + u * xt[2] + v * yt[2] + w * zt[2],
            )

        # If no assembly relationships, return un-instanced polygons
        if not rep_edges:
            single_polys: list[tuple[list[tuple[float, float, float]], tuple[int, int, int] | None]] = []
            for fid, pts in face_polygons.items():
                single_polys.append((pts, face_colors.get(fid)))
            return 1.0, single_polys

        # Find assembly root representation
        src_set = set(e[0] for e in rep_edges)
        dst_set = set(e[1] for e in rep_edges)
        roots = dst_set - src_set
        if not roots:
            roots = {rep_edges[-1][1]}
        root = list(roots)[0]

        graph: dict[int, list[tuple[int, int | None]]] = {}
        for src, dst, tid in rep_edges:
            graph.setdefault(src, []).append((dst, tid))

        def dfs(cur: int, path_trans: list[int]) -> list[tuple[int, list[int]]]:
            if cur == root:
                return [(cur, path_trans)]
            if cur not in graph:
                return []
            res = []
            for nxt, tid in graph[cur]:
                t_list = path_trans + ([tid] if tid is not None else [])
                res.extend(dfs(nxt, t_list))
            return res

        all_instances: list[tuple[int, list[int], list[int]]] = []
        for r_start, fids in rep_to_faces.items():
            paths = dfs(r_start, [])
            for _, t_list in paths:
                all_instances.append((r_start, fids, t_list))

        assembled_polys: list[tuple[list[tuple[float, float, float]], tuple[int, int, int] | None]] = []
        for r_start, fids, t_list in all_instances:
            for fid in fids:
                if fid not in face_polygons:
                    continue
                pts = face_polygons[fid]
                for tid in t_list:
                    pts = [apply_transform(p, tid) for p in pts]
                assembled_polys.append((pts, face_colors.get(fid)))

        return 1.0, assembled_polys

    def _build_model_from_bodies(
        self,
        part_name: str,
        bodies: list[Body3DInfo],
        step_cache: dict[str, tuple[float, list[tuple[list[tuple[float, float, float]], tuple[int, int, int] | None]]]],
        pads: list[Pad3D],
    ) -> Footprint3DModel:
        """Transforms all 3D bodies into the footprint coordinate frame and constructs Footprint3DModel."""
        final_polygons: list[Polygon3D] = []
        all_pts: list[tuple[float, float, float]] = []

        primary_body = bodies[0]

        for body in bodies:
            if body.stream_name not in step_cache:
                continue
            unit_sc, raw_polys_with_colors = step_cache[body.stream_name]

            # Transform each polygon of this body
            for poly_pts, poly_col in raw_polys_with_colors:
                t_pts = [
                    _transform_point(
                        pt,
                        unit_sc,
                        body.rot_x,
                        body.rot_y,
                        body.rot_z,
                        body.rot_2d,
                        body.x_2d,
                        body.y_2d,
                        body.dz,
                    )
                    for pt in poly_pts
                ]
                all_pts.extend(t_pts)

                normal, area = _calc_polygon_normal_and_area(t_pts)
                cx = sum(p[0] for p in t_pts) / len(t_pts)
                cy = sum(p[1] for p in t_pts) / len(t_pts)
                cz = sum(p[2] for p in t_pts) / len(t_pts)

                # Color assignment: priority is native STEP CAD color, then Altium body color, then package default
                if poly_col is not None:
                    color = poly_col
                elif body.body_color is not None:
                    base_c = body.body_color
                    color = (min(255, int(base_c[0] * 1.05)), min(255, int(base_c[1] * 1.05)), min(255, int(base_c[2] * 1.05)))
                elif "CAP" in part_name.upper():
                    color = (185, 155, 115)  # Ceramic tan body
                elif "RES" in part_name.upper():
                    color = (40, 42, 45)     # Black resistor body
                elif "HEADER" in part_name.upper() or "PIN" in part_name.upper():
                    color = (210, 175, 75)   # Gold header pin
                else:
                    color = (52, 55, 60)     # Dark epoxy mold

                final_polygons.append(
                    Polygon3D(
                        points=t_pts,
                        normal=normal,
                        color=color,
                        center=(cx, cy, cz),
                        area=area,
                    )
                )

        if not all_pts:
            return self._generate_fallback_model(part_name, pads)

        min_x = min(p[0] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_y = max(p[1] for p in all_pts)
        min_z = min(p[2] for p in all_pts)
        max_z = max(p[2] for p in all_pts)

        len_x = round(max_x - min_x, 3)
        len_y = round(max_y - min_y, 3)
        len_z = round(max_z - min_z, 3)

        # Refine capacitor/resistor terminal highlights based on body bounds
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        is_x_major = len_x >= len_y
        for poly in final_polygons:
            if "CAP" in part_name.upper() or "RES" in part_name.upper():
                cx, cy, _ = poly.center
                dist = abs(cx - center_x) if is_x_major else abs(cy - center_y)
                half_span = (len_x if is_x_major else len_y) * 0.35
                if dist > half_span:
                    poly.color = (195, 195, 200)  # Silver/tin terminal

        # Standoff above PCB surface
        standoff_mm = primary_body.standoff if primary_body.standoff != 0.0 else max(0.0, min_z)

        return Footprint3DModel(
            name=part_name,
            length_mm=len_x,
            width_mm=len_y,
            height_mm=len_z,
            standoff_mm=round(standoff_mm, 3),
            bbox_min=(min_x, min_y, min_z),
            bbox_max=(max_x, max_y, max_z),
            polygons=final_polygons,
            pads=pads,
            has_3d_model=True,
            source_step_name=primary_body.name,
        )

    def _generate_fallback_model(self, part_name: str, pads: list[Pad3D]) -> Footprint3DModel:
        """Synthesize a clean 3D component model centered on pads when no embedded STEP model is present."""
        if pads:
            xs = [p.x for p in pads]
            ys = [p.y for p in pads]
            pad_min_x, pad_max_x = min(xs), max(xs)
            pad_min_y, pad_max_y = min(ys), max(ys)
            pad_cx = (pad_min_x + pad_max_x) / 2.0
            pad_cy = (pad_min_y + pad_max_y) / 2.0
            w_pads = max(p.width for p in pads)
            h_pads = max(p.height for p in pads)
            len_x = max(0.8, (pad_max_x - pad_min_x) + w_pads * 0.6)
            len_y = max(0.6, (pad_max_y - pad_min_y) + h_pads * 0.6)
        else:
            pad_cx = 0.0
            pad_cy = 0.0
            len_x = 2.0
            len_y = 1.25

        len_z = max(0.4, min(len_x, len_y) * 0.6)
        hx = len_x / 2.0
        hy = len_y / 2.0
        hz = len_z
        standoff = 0.0

        v0 = (pad_cx - hx, pad_cy - hy, standoff)
        v1 = (pad_cx + hx, pad_cy - hy, standoff)
        v2 = (pad_cx + hx, pad_cy + hy, standoff)
        v3 = (pad_cx - hx, pad_cy + hy, standoff)
        v4 = (pad_cx - hx, pad_cy - hy, standoff + hz)
        v5 = (pad_cx + hx, pad_cy - hy, standoff + hz)
        v6 = (pad_cx + hx, pad_cy + hy, standoff + hz)
        v7 = (pad_cx - hx, pad_cy + hy, standoff + hz)

        box_faces = [
            ([v4, v5, v6, v7], (0.0, 0.0, 1.0), (55, 60, 65)),
            ([v0, v3, v2, v1], (0.0, 0.0, -1.0), (45, 48, 52)),
            ([v0, v1, v5, v4], (0.0, -1.0, 0.0), (65, 70, 75)),
            ([v2, v3, v7, v6], (0.0, 1.0, 0.0), (60, 65, 70)),
            ([v3, v0, v4, v7], (-1.0, 0.0, 0.0), (70, 75, 80)),
            ([v1, v2, v6, v5], (1.0, 0.0, 0.0), (70, 75, 80)),
        ]

        polygons = [
            Polygon3D(
                points=pts,
                normal=norm,
                color=col,
                center=(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), sum(p[2] for p in pts) / len(pts)),
            )
            for pts, norm, col in box_faces
        ]

        return Footprint3DModel(
            name=part_name,
            length_mm=round(len_x, 3),
            width_mm=round(len_y, 3),
            height_mm=round(len_z, 3),
            standoff_mm=0.0,
            bbox_min=(pad_cx - hx, pad_cy - hy, 0.0),
            bbox_max=(pad_cx + hx, pad_cy + hy, len_z),
            polygons=polygons,
            pads=pads,
            has_3d_model=False,
        )
