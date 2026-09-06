# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

class LibraryHistoryManager:
    """
    Tracks and persists recently selected schematic symbols and PCB footprints.
    Saved to .cache/library_history.json.
    """
    _instance: LibraryHistoryManager | None = None

    def __init__(self, history_file: Path | None = None) -> None:
        if history_file is None:
            try:
                from ..config import CACHE_DIR
                self.history_file = CACHE_DIR / "library_history.json"
            except Exception:
                self.history_file = Path(".cache") / "library_history.json"
        else:
            self.history_file = Path(history_file)

        self._history: dict[str, list[dict[str, Any]]] = {
            "SYMBOL": [],
            "FOOTPRINT": [],
        }
        self.load()

    @classmethod
    def get_instance(cls) -> LibraryHistoryManager:
        if cls._instance is None:
            cls._instance = LibraryHistoryManager()
        return cls._instance

    def load(self) -> None:
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    if isinstance(data, dict):
                        self._history["SYMBOL"] = data.get("SYMBOL", [])
                        self._history["FOOTPRINT"] = data.get("FOOTPRINT", [])
            except Exception as exc:
                logger.warning(f"Failed to load library history from {self.history_file}: {exc}")
                self._history = {"SYMBOL": [], "FOOTPRINT": []}
        else:
            self._history = {"SYMBOL": [], "FOOTPRINT": []}

    def save(self) -> None:
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as fp:
                json.dump(self._history, fp, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.error(f"Failed to save library history to {self.history_file}: {exc}")

    def add_entry(
        self,
        mode: str,
        file_path: str,
        part_name: str,
        max_entries: int = 30,
    ) -> None:
        """Add or update an item in history (MRU - Most Recently Used order)."""
        key = mode.upper()
        if key not in self._history:
            self._history[key] = []

        clean_path = str(file_path).strip()
        clean_name = str(part_name).strip()
        if not clean_path or not clean_name:
            return

        # Normalize to relative path if possible
        try:
            from ..config import to_relative_path
            rel_path = to_relative_path(clean_path)
        except Exception:
            rel_path = clean_path

        # Remove existing occurrence if already present
        filtered = [
            item for item in self._history[key]
            if not (item.get("part_name") == clean_name and item.get("file_path") == rel_path)
        ]

        now_str = datetime.now(timezone.utc).isoformat()
        new_entry = {
            "part_name": clean_name,
            "file_path": rel_path,
            "last_used": now_str,
        }

        # Prepend to top
        filtered.insert(0, new_entry)
        self._history[key] = filtered[:max_entries]
        self.save()
        logger.debug(f"Added {key} history entry: {clean_name} ({rel_path})")

    def get_history(self, mode: str) -> list[dict[str, Any]]:
        """Return a copy of the history list for the specified mode ('SYMBOL' or 'FOOTPRINT')."""
        key = mode.upper()
        return [dict(item) for item in self._history.get(key, [])]

    def clear_history(self, mode: str | None = None) -> None:
        """Clear history for a specific mode or all modes."""
        if mode is None:
            self._history = {"SYMBOL": [], "FOOTPRINT": []}
        else:
            key = mode.upper()
            if key in self._history:
                self._history[key] = []
        self.save()
        logger.info(f"Cleared library history for mode: {mode or 'ALL'}")
