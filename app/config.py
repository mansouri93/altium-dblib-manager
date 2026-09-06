# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Any

# Base Paths
if getattr(sys, "frozen", False):
    # Running in a PyInstaller bundle
    BASE_DIR = Path(sys.executable).resolve().parent
    # Fallback to parent directory if DB or library is located one level up (e.g. running from dist/AltiumDbLibManager)
    if not (BASE_DIR / "database.accdb").exists() and not (BASE_DIR / "thunder-light.accdb").exists() and (BASE_DIR.parent / "database.accdb").exists():
        BASE_DIR = BASE_DIR.parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "database.accdb" if (BASE_DIR / "database.accdb").exists() else BASE_DIR / "thunder-light.accdb"
DBLIB_PATH = BASE_DIR / "library.DbLib" if (BASE_DIR / "library.DbLib").exists() else BASE_DIR / "thunder-light.DbLib"
LIBRARY_DIR = BASE_DIR / "altium-library-master"
SYMBOLS_DIR = LIBRARY_DIR / "symbols"
FOOTPRINTS_DIR = LIBRARY_DIR / "footprints"
CACHE_DIR = BASE_DIR / ".cache"

# InvenTree Paths
INVENTREE_DIR = Path(os.getenv("INVENTREE_DIR", r"D:\mansouri\Programs\Inventree"))
INVENTREE_SETTINGS = Path(os.getenv("INVENTREE_SETTINGS", str(INVENTREE_DIR / "rack-viewer" / "inventree-viewer-settings.json")))
INVENTREE_CLIENT_PATH = Path(
    os.getenv(
        "INVENTREE_CLIENT_PATH",
        str(BASE_DIR / "inventree_client.py" if (BASE_DIR / "inventree_client.py").exists() else INVENTREE_DIR / "rack-viewer" / "inventree_client.py")
    )
)

# Standard columns for Altium Category Tables (matching exact Access ordinal order)
STANDARD_COLUMNS = [
    "ID",
    "Package",
    "Value",
    "Tolerance",
    "Power",
    "Description",
    "Part Number",
    "Manufacturer",
    "Manufacturer Part Number",
    "Location",
    "Stock",
    "Library Ref",
    "Library Path",
    "Footprint Ref",
    "Footprint Path",
    "Footprint Ref 2",
    "Footprint Path 2",
    "Footprint Ref 3",
    "Footprint Path 3",
]

# System-managed Symbol and Footprint columns (read-only in table view, auto-created in schema)
SYMBOL_FOOTPRINT_COLUMNS = [
    "Library Ref",
    "Library Path",
    "Footprint Ref",
    "Footprint Path",
    "Footprint Ref 2",
    "Footprint Path 2",
    "Footprint Ref 3",
    "Footprint Path 3",
]


def to_relative_path(abs_path: str | Path | None) -> str:
    """Convert an absolute path to a relative path from BASE_DIR if possible."""
    if not abs_path:
        return ""
    try:
        p = Path(abs_path).resolve()
        return str(p.relative_to(BASE_DIR))
    except (ValueError, Exception):
        return str(abs_path)

def to_absolute_path(rel_or_abs: str | Path | None) -> Path | None:
    """Convert a relative or absolute path to a fully qualified Path."""
    if not rel_or_abs:
        return None
    p = Path(rel_or_abs)
    if p.is_absolute():
        return p
    return (BASE_DIR / p).resolve()

DEFAULT_FIELD_MAPPINGS: list[dict[str, Any]] = [
    {"enabled": True, "inventree_field": "total_in_stock", "db_column": "Stock"},
    {"enabled": True, "inventree_field": "location_name", "db_column": "Location"},
    {"enabled": False, "inventree_field": "description", "db_column": "Description"},
    {"enabled": False, "inventree_field": "link", "db_column": "ComponentLink1URL"},
    {"enabled": False, "inventree_field": "keywords", "db_column": "Keywords"},
    {"enabled": False, "inventree_field": "IPN", "db_column": "Manufacturer Part Number"},
]

def format_stock_value(val: Any, units: str | None = None, omit_pcs: bool = True) -> str:
    """
    Format stock value supporting decimals and units (e.g. 2.5m, 10m, 125).
    If val is None or empty string, returns "".
    If units is provided and not generic piece count (when omit_pcs=True), appends units.
    """
    if val is None or str(val).strip() == "":
        return ""
    try:
        f_val = float(val)
        num_str = str(int(f_val)) if f_val.is_integer() else f"{f_val:g}"
    except (ValueError, TypeError):
        num_str = str(val).strip()

    clean_unit = (units or "").strip()
    if clean_unit:
        if omit_pcs and clean_unit.lower() in ("pcs", "pc", "ea"):
            return num_str
        return f"{num_str}{clean_unit}"
    return num_str

SETTINGS_FILE = CACHE_DIR / "app_settings.json"

class AppSettingsManager:
    """Manages application-wide user configuration such as DB path, library roots, and field mappings."""

    _instance: AppSettingsManager | None = None

    def __init__(self, settings_file: Path = SETTINGS_FILE) -> None:
        self.settings_file = settings_file
        self.data: dict[str, Any] = {}
        self._load()

    @classmethod
    def get_instance(cls) -> AppSettingsManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load(self) -> None:
        if self.settings_file.exists():
            try:
                import json
                with open(self.settings_file, "r", encoding="utf-8-sig") as fp:
                    self.data = json.load(fp)
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def _save(self) -> None:
        try:
            import json
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, "w", encoding="utf-8") as fp:
                json.dump(self.data, fp, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_db_path(self) -> Path:
        val = self.data.get("db_path")
        if val:
            p = to_absolute_path(val)
            if p and p.exists():
                return p
        return DB_PATH

    def get_symbols_dir(self) -> Path:
        val = self.data.get("symbols_dir")
        if val:
            p = to_absolute_path(val)
            if p and p.exists():
                return p
        return SYMBOLS_DIR

    def get_footprints_dir(self) -> Path:
        val = self.data.get("footprints_dir")
        if val:
            p = to_absolute_path(val)
            if p and p.exists():
                return p
        return FOOTPRINTS_DIR

    def get_field_mappings(self) -> list[dict[str, Any]]:
        mappings = self.data.get("field_mappings")
        if isinstance(mappings, list) and len(mappings) > 0:
            return [dict(m) for m in mappings]
        return [dict(m) for m in DEFAULT_FIELD_MAPPINGS]

    def save_field_mappings(
        self,
        mappings: list[dict[str, Any]],
        format_units: bool = True,
        omit_pcs: bool = True,
    ) -> None:
        self.data["field_mappings"] = mappings
        self.data["stock_format_units"] = bool(format_units)
        self.data["stock_omit_pcs"] = bool(omit_pcs)
        self._save()

    def get_stock_unit_options(self) -> tuple[bool, bool]:
        """Returns (format_units, omit_pcs). Defaults to (True, True)."""
        format_units = self.data.get("stock_format_units", True)
        omit_pcs = self.data.get("stock_omit_pcs", True)
        return bool(format_units), bool(omit_pcs)

    def get_theme(self) -> str:
        """Returns the configured UI theme ID. Defaults to 'dark_modern'."""
        return str(self.data.get("theme", "dark_modern"))

    def set_theme(self, theme_id: str) -> None:
        """Saves the chosen UI theme ID."""
        self.data["theme"] = str(theme_id)
        self._save()

    def save_settings(
        self,
        db_path: str | Path | None = None,
        symbols_dir: str | Path | None = None,
        footprints_dir: str | Path | None = None,
    ) -> None:
        if db_path is not None:
            self.data["db_path"] = to_relative_path(db_path)
        if symbols_dir is not None:
            self.data["symbols_dir"] = to_relative_path(symbols_dir)
        if footprints_dir is not None:
            self.data["footprints_dir"] = to_relative_path(footprints_dir)
        self._save()

def get_db_path() -> Path:
    return AppSettingsManager.get_instance().get_db_path()

def get_symbols_dir() -> Path:
    return AppSettingsManager.get_instance().get_symbols_dir()

def get_footprints_dir() -> Path:
    return AppSettingsManager.get_instance().get_footprints_dir()

def get_current_theme() -> str:
    return AppSettingsManager.get_instance().get_theme()

def save_current_theme(theme_id: str) -> None:
    AppSettingsManager.get_instance().set_theme(theme_id)

def save_app_settings(
    db_path: str | Path | None = None,
    symbols_dir: str | Path | None = None,
    footprints_dir: str | Path | None = None,
) -> None:
    AppSettingsManager.get_instance().save_settings(db_path, symbols_dir, footprints_dir)

