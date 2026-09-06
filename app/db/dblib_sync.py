# -*- coding: utf-8 -*-
from __future__ import annotations
import configparser
import re
from pathlib import Path
from typing import Any
from ..config import DBLIB_PATH, DB_PATH

class DbLibSync:
    """Synchronizes tables and field mappings in Altium DbLib file."""

    def __init__(self, dblib_path: str | Path = DBLIB_PATH) -> None:
        self.dblib_path = Path(dblib_path)

    def get_registered_tables(self) -> list[str]:
        """Return list of table names registered in the .DbLib file."""
        if not self.dblib_path.exists():
            return []
        tables = []
        content = self.dblib_path.read_text(encoding="utf-8", errors="ignore")
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("TableName="):
                val = line.split("=", 1)[1].strip()
                if val and val not in tables:
                    tables.append(val)
        return tables

    def sync_table_to_dblib(self, table_name: str, columns: list[str]) -> bool:
        """
        Add a table and its field mappings to the .DbLib file if not already present.
        """
        if not self.dblib_path.exists():
            return False

        registered = self.get_registered_tables()
        if table_name in registered:
            return True  # Already registered

        content = self.dblib_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()

        # Find the highest TableN and FieldMapN indices
        highest_table_idx = 0
        highest_field_idx = 0
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("[Table") and line_str.endswith("]"):
                try:
                    idx = int(line_str[6:-1])
                    highest_table_idx = max(highest_table_idx, idx)
                except ValueError:
                    pass
            elif line_str.startswith("[FieldMap") and line_str.endswith("]"):
                try:
                    idx = int(line_str[9:-1])
                    highest_field_idx = max(highest_field_idx, idx)
                except ValueError:
                    pass

        new_table_idx = highest_table_idx + 1
        new_lines = []
        new_lines.append(f"[Table{new_table_idx}]")
        new_lines.append("SchemaName=")
        new_lines.append(f"TableName={table_name}")
        new_lines.append("Enabled=True")
        new_lines.append("UserWhere=0")
        new_lines.append("UserWhereText=")

        # Standard field mappings
        # FieldType: 0 for Part Number / Key, 1 for Parameters
        standard_fields = [
            ("Description", 1),
            ("Part Number", 0),
            ("Library Ref", 1),
            ("Library Path", 1),
            ("Footprint Ref", 1),
            ("Footprint Path", 1),
            ("Footprint Ref 2", 1),
            ("Footprint Path 2", 1),
            ("Footprint Ref 3", 1),
            ("Footprint Path 3", 1),
            ("Location", 1),
            ("Stock", 1),
            ("Value", 1),
            ("Package", 1),
            ("Tolerance", 1),
            ("Power", 1),
            ("Manufacturer", 1),
            ("Manufacturer Part Number", 1),
        ]

        curr_field_idx = highest_field_idx
        for field_name, ftype in standard_fields:
            if field_name in columns or not columns:
                curr_field_idx += 1
                new_lines.append(f"[FieldMap{curr_field_idx}]")
                opt = (
                    f"Options=FieldName={table_name}.{field_name}|"
                    f"TableNameOnly={table_name}|"
                    f"FieldNameOnly={field_name}|"
                    f"FieldType={ftype}|"
                    f"ParameterName=[{field_name}]|"
                    f"VisibleOnAdd=False|AddMode=0|RemoveMode=0|UpdateMode=0"
                )
                new_lines.append(opt)

        # Append to the file
        full_content = content.rstrip() + "\n" + "\n".join(new_lines) + "\n"
        self.dblib_path.write_text(full_content, encoding="utf-8")
        return True

    def rename_table_in_dblib(self, old_name: str, new_name: str) -> bool:
        """Rename an existing table in .DbLib file."""
        if not self.dblib_path.exists():
            return False

        content = self.dblib_path.read_text(encoding="utf-8", errors="ignore")
        # Replace TableName=old_name
        content = re.sub(rf"^TableName={re.escape(old_name)}$", f"TableName={new_name}", content, flags=re.MULTILINE)
        # Replace options
        content = content.replace(f"FieldName={old_name}.", f"FieldName={new_name}.")
        content = content.replace(f"TableNameOnly={old_name}|", f"TableNameOnly={new_name}|")
        self.dblib_path.write_text(content, encoding="utf-8")
        return True

    def remove_table_from_dblib(self, table_name: str) -> bool:
        """Remove a table and its field maps from .DbLib file."""
        if not self.dblib_path.exists():
            return False

        content = self.dblib_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()

        cleaned_lines = []
        skip_block = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                skip_block = False

            if stripped == f"TableName={table_name}" or f"TableNameOnly={table_name}" in stripped:
                # If this block is for the table being removed, skip recent section header too
                if cleaned_lines and cleaned_lines[-1].strip().startswith("["):
                    cleaned_lines.pop()
                skip_block = True
                continue

            if not skip_block:
                cleaned_lines.append(line)

        self.dblib_path.write_text("\n".join(cleaned_lines) + "\n", encoding="utf-8")
        return True

