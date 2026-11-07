# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.access_manager import AccessDBManager

class TestCalculatedColumnSafety(unittest.TestCase):
    """Unit tests for calculated column safety, dependency auto-update, and protection."""

    @classmethod
    def setUpClass(cls):
        cls.mgr = AccessDBManager()

    def test_delete_column_prevented_when_referenced_in_formula(self):
        # In LED table, Part Number references [Value] and [Package]
        # Deleting Value must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            self.mgr.delete_column("LED", "Value")
        self.assertIn("used in the calculated formula", str(ctx.exception))

        # Deleting Package must also raise ValueError
        with self.assertRaises(ValueError) as ctx:
            self.mgr.delete_column("LED", "Package")
        self.assertIn("used in the calculated formula", str(ctx.exception))

    def test_rename_column_auto_updates_dependent_formulas(self):
        # Create a temporary table to test column rename and formula update end-to-end
        test_tbl = "Test_Formula_Safety_Table"
        existing = self.mgr.list_tables()
        if test_tbl in existing:
            self.mgr.drop_table(test_tbl)

        try:
            fields = [
                {"name": "ID", "type": "autonumber", "expression": ""},
                {"name": "ItemColor", "type": "short_text", "expression": ""},
                {"name": "ItemSize", "type": "short_text", "expression": ""},
                {"name": "Part Number", "type": "calculated", "expression": "'TST-' & [ItemColor] & '-' & [ItemSize]"},
            ]
            self.mgr.create_category_table(test_tbl, custom_fields=fields)

            # Insert a record
            self.mgr.insert_record(test_tbl, {"ItemColor": "Red", "ItemSize": "0603"})
            recs = self.mgr.fetch_records(test_tbl)
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["Part Number"], "TST-Red-0603")

            # Rename ItemColor -> ColorName
            # edit_column should automatically update Part Number's formula
            self.mgr.edit_column(test_tbl, "ItemColor", "ColorName", "short_text")

            # Verify schema expression was updated
            schema = {f["name"]: f for f in self.mgr.get_table_schema(test_tbl)}
            self.assertIn("ColorName", schema)
            self.assertNotIn("ItemColor", schema)
            self.assertIn("[ColorName]", schema["Part Number"]["expression"])

            # Verify records can be fetched without (-5617) error
            recs = self.mgr.fetch_records(test_tbl)
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["Part Number"], "TST-Red-0603")
            self.assertEqual(recs[0]["ColorName"], "Red")

        finally:
            if test_tbl in self.mgr.list_tables():
                self.mgr.drop_table(test_tbl)

    def test_led_table_loads_successfully(self):
        # Verify the LED table in the actual database is healthy and opens cleanly
        records = self.mgr.fetch_records("LED")
        self.assertGreater(len(records), 0)
        # Check first record has Part Number populated
        first = records[0]
        self.assertTrue(bool(first.get("Part Number")))
        self.assertTrue(bool(first.get("Value")))

if __name__ == "__main__":
    unittest.main()
