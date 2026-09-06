# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any
import pyaltiumlib
import svgwrite
from ..config import to_absolute_path

logger = logging.getLogger(__name__)

def get_placeholder_svg(message: str, width: int = 400, height: int = 400) -> str:
    """Generate a clean placeholder SVG when preview cannot be rendered."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#1e1e24" rx="8"/>
  <text x="50%" y="50%" fill="#888899" font-family="Segoe UI, sans-serif" font-size="14" text-anchor="middle" dominant-baseline="middle">
    {message}
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

    def render_svg(self, file_path: str | Path, part_name: str, width: int = 400, height: int = 400) -> str:
        """Render a component or footprint to an SVG string."""
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

            dwg = svgwrite.Drawing(size=(width, height))
            part.draw_svg(dwg, width, height)
            svg_str = dwg.tostring()

            # Fix SVG background if none is present for dark mode styling
            if not svg_str or len(svg_str) < 20:
                return get_placeholder_svg("Empty preview", width, height)

            return svg_str
        except Exception as exc:
            logger.error(f"Error rendering SVG for {part_name} in {file_path}: {exc}")
            return get_placeholder_svg(f"Render error: {exc}", width, height)
