# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib
from pathlib import Path
from ..config import CACHE_DIR
from .parser import AltiumParser

class PreviewCache:
    """Caches generated SVGs to memory and disk for high performance."""

    def __init__(self, parser: AltiumParser | None = None) -> None:
        self.parser = parser or AltiumParser()
        self.cache_dir = CACHE_DIR / "previews"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[str, str] = {}

    def _cache_key(self, file_path: str, part_name: str, width: int, height: int) -> str:
        raw = f"{file_path}::{part_name}::{width}x{height}"
        return hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()

    def get_svg(self, file_path: str, part_name: str, width: int = 400, height: int = 400) -> str:
        if not file_path or not part_name:
            return ""

        key = self._cache_key(file_path, part_name, width, height)

        # Check memory cache
        if key in self._memory_cache:
            return self._memory_cache[key]

        # Check disk cache
        disk_file = self.cache_dir / f"{key}.svg"
        if disk_file.exists():
            try:
                svg_data = disk_file.read_text(encoding="utf-8")
                self._memory_cache[key] = svg_data
                return svg_data
            except Exception:
                pass

        # Generate fresh SVG
        svg_data = self.parser.render_svg(file_path, part_name, width, height)

        # Store in caches
        self._memory_cache[key] = svg_data
        try:
            disk_file.write_text(svg_data, encoding="utf-8")
        except Exception:
            pass

        return svg_data
