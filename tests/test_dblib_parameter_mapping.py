# -*- coding: utf-8 -*-
from __future__ import annotations
import unittest
from pathlib import Path
from app.config import DBLIB_PATH
from app.db.dblib_sync import DbLibSync


class TestDbLibParameterMapping(unittest.TestCase):
    """Verifies that Altium DbLib field mappings correctly distinguish model links from component parameters."""

    def test_current_dblib_has_no_bracketed_parameters(self) -> None:
        """Verify that library.DbLib does not have square brackets around standard parameters."""
        self.assertTrue(DBLIB_PATH.exists(), f"DbLib file not found at {DBLIB_PATH}")
        content = DBLIB_PATH.read_text(encoding="utf-8", errors="ignore")

        model_reserved_fields = {
            "Library Ref", "Library Path",
            "Footprint Ref", "Footprint Path",
            "Footprint Ref 2", "Footprint Path 2",
            "Footprint Ref 3", "Footprint Path 3",
            "Description",
        }

        cap_value_found = False
        for line in content.splitlines():
            if line.startswith("Options="):
                parts = dict(p.split("=", 1) for p in line[8:].split("|") if "=" in p)
                field_name = parts.get("FieldNameOnly", "")
                param_name = parts.get("ParameterName", "")

                if parts.get("FieldName") == "Capacitor.Value":
                    cap_value_found = True
                    self.assertEqual(param_name, "Value", "Capacitor.Value must not have brackets")
                    self.assertEqual(parts.get("VisibleOnAdd"), "True", "Capacitor.Value must be visible on add")

                if field_name not in model_reserved_fields:
                    self.assertFalse(
                        param_name.startswith("[") and param_name.endswith("]"),
                        f"Non-model parameter '{field_name}' in '{parts.get('FieldName')}' should not have brackets: {param_name}"
                    )

        self.assertTrue(cap_value_found, "Capacitor.Value field mapping must exist in library.DbLib")

    def test_sync_table_generates_correct_mappings(self) -> None:
        """Verify that sync_table_to_dblib formats model fields with brackets and component parameters without brackets."""
        test_dblib = Path("tests/data/test_temp.DbLib")
        test_dblib.parent.mkdir(parents=True, exist_ok=True)
        test_dblib.write_text("[OutputDatabaseLinkFile]\nVersion=1.1\n", encoding="utf-8")

        try:
            syncer = DbLibSync(dblib_path=test_dblib)
            cols = ["Part Number", "Value", "Voltage", "Library Ref", "Footprint Ref", "Location"]
            syncer.sync_table_to_dblib("TestCap", cols)

            content = test_dblib.read_text(encoding="utf-8")
            self.assertIn("TableName=TestCap", content)
            self.assertIn("FieldNameOnly=Value|FieldType=1|ParameterName=Value|VisibleOnAdd=True", content)
            self.assertIn("FieldNameOnly=Location|FieldType=1|ParameterName=Location|VisibleOnAdd=False", content)
            self.assertIn("FieldNameOnly=Library Ref|FieldType=1|ParameterName=[Library Ref]", content)
            self.assertIn("FieldNameOnly=Footprint Ref|FieldType=1|ParameterName=[Footprint Ref]", content)
        finally:
            if test_dblib.exists():
                test_dblib.unlink()


if __name__ == "__main__":
    unittest.main()
