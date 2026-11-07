# -*- coding: utf-8 -*-
from __future__ import annotations
import html
import logging
from pathlib import Path
from typing import Any
import pyaltiumlib
import svgwrite
from ..config import to_absolute_path

logger = logging.getLogger(__name__)

def part_id_to_name(part_id: int) -> str:
    """Convert 1-based part ID to standard Altium Part letter (1 -> 'Part A', 2 -> 'Part B', ...)."""
    if part_id <= 0:
        return f"Part {part_id}"
    idx = part_id - 1
    letters = ""
    while True:
        letters = chr(ord("A") + (idx % 26)) + letters
        idx = idx // 26 - 1
        if idx < 0:
            break
    return f"Part {letters}"

def _get_record_part_id(record: Any) -> int | None:
    """Extract owner part ID from an Altium schematic record."""
    if hasattr(record, "rawdata") and hasattr(record.rawdata, "get"):
        val = record.rawdata.get("ownerpartid")
        if val is None:
            val = record.rawdata.get("OwnerPartId")
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return None

def get_placeholder_svg(message: str, width: int = 400, height: int = 400) -> str:
    """Generate a clean placeholder SVG when preview cannot be rendered."""
    escaped_msg = html.escape(str(message))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#1e1e24" rx="8"/>
  <text x="50%" y="50%" fill="#888899" font-family="Segoe UI, sans-serif" font-size="14" text-anchor="middle" dominant-baseline="middle">
    {escaped_msg}
  </text>
</svg>"""

class AltiumParser:
    """Parses Altium Schematic (.SchLib) and PCB (.PcbLib) library files."""

    def __init__(self) -> None:
        self._loaded_libs: dict[str, Any] = {}

    def get_lib(self, file_path: str | Path) -> Any | None:
        abs_path = to_absolute_path(file_path)
        if not abs_path or not abs_path.exists():
            return None
        path_str = str(abs_path)
        if path_str in self._loaded_libs:
            return self._loaded_libs[path_str]
        try:
            lib = pyaltiumlib.read(path_str)
            self._loaded_libs[path_str] = lib
            return lib
        except Exception as exc:
            logger.warning(f"Error loading Altium lib {path_str}: {exc}")
            return None

    def list_parts(self, file_path: str | Path) -> list[str]:
        """Return all part names in a library file."""
        lib = self.get_lib(file_path)
        if not lib:
            return []
        try:
            parts = lib.list_parts()
            return sorted(parts) if parts else []
        except Exception as exc:
            logger.warning(f"Error listing parts from {file_path}: {exc}")
            return []

    def get_subpart_count(self, file_path: str | Path, part_name: str) -> int:
        """Return the number of sub-parts for a schematic component."""
        abs_path = to_absolute_path(file_path)
        if not abs_path or not abs_path.exists():
            return 1

        lib = self.get_lib(abs_path)
        if not lib:
            return 1

        try:
            part = lib.get_part(part_name)
            if not part:
                return 1

            count = 1
            if hasattr(part, "PartCount"):
                try:
                    count = max(count, int(part.PartCount))
                except (ValueError, TypeError):
                    pass

            for rec in getattr(part, "Records", []):
                pid = _get_record_part_id(rec)
                if pid is not None and pid > count:
                    count = pid

            return count
        except Exception as exc:
            logger.debug(f"Error getting sub-part count for {part_name} in {file_path}: {exc}")
            return 1

    def render_svg(
        self,
        file_path: str | Path,
        part_name: str,
        width: int = 400,
        height: int = 400,
        subpart_id: int | None = None,
    ) -> str:
        """Render a component or footprint to an SVG string with optional sub-part isolation."""
        abs_path = to_absolute_path(file_path)
        if not abs_path or not abs_path.exists():
            return get_placeholder_svg("File not found", width, height)

        lib = self.get_lib(abs_path)
        if not lib:
            return get_placeholder_svg("Cannot read library file", width, height)

        try:
            part = lib.get_part(part_name)
            if not part:
                return get_placeholder_svg(f"Part '{part_name}' not found in library", width, height)

            # Sanitize negative rotation angles on records to prevent pyaltiumlib rotate(--...) syntax error
            if hasattr(part, "Records"):
                for obj in part.Records:
                    if hasattr(obj, "rotation") and isinstance(obj.rotation, (int, float)) and obj.rotation < 0:
                        obj.rotation = obj.rotation % 360.0

            # Determine whether sub-part filtering should be applied
            effective_subpart = subpart_id
            if effective_subpart is None:
                sub_count = self.get_subpart_count(abs_path, part_name)
                if sub_count > 1:
                    effective_subpart = 1

            orig_records = list(part.Records) if hasattr(part, "Records") else []
            try:
                if effective_subpart is not None and orig_records:
                    # Filter for records belonging to the target sub-part or shared records (-1, 0, None)
                    part.Records = [
                        rec for rec in orig_records
                        if _get_record_part_id(rec) in (-1, 0, None, effective_subpart)
                    ]

                if hasattr(part, "_BoundingBoxes"):
                    part._BoundingBoxes.clear()

                dwg = svgwrite.Drawing(size=(width, height))
                part.draw_svg(dwg, width, height)
                svg_str = dwg.tostring()
            finally:
                if orig_records:
                    part.Records = orig_records

            # Fix SVG background if none is present for dark mode styling
            if not svg_str or len(svg_str) < 20:
                return get_placeholder_svg("Empty preview", width, height)

            return svg_str
        except Exception as exc:
            logger.error(f"Error rendering SVG for {part_name} in {file_path}: {exc}")
            return get_placeholder_svg(f"Render error: {exc}", width, height)
