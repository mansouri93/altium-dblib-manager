# -*- coding: utf-8 -*-
import unittest
from app.db.access_manager import AccessDBManager

class FormulaSafetyTest(unittest.TestCase):
    def setUp(self):
        self.db = AccessDBManager()

    def test_invalid_formula_does_not_delete_column(self):
        # 1. Ensure Part Number exists as short_text
        schema = {f["name"]: f for f in self.db.get_table_schema("Capacitor")}
        if "Part Number" not in schema:
            self.db.add_column("Capacitor", "Part Number", "short_text")

        # 2. Attempt to update with a misspelled column name [Packege]
        with self.assertRaises(ValueError) as ctx:
            self.db.edit_column(
                "Capacitor",
                "Part Number",
                "Part Number",
                "calculated",
                "'C-' & [Packege] & '-' & [Value]",
            )
        
        self.assertIn("Packege", str(ctx.exception))

        # 3. Verify Part Number is still present in schema (was not deleted)
        schema_after = {f["name"]: f for f in self.db.get_table_schema("Capacitor")}
        self.assertIn("Part Number", schema_after)

    def test_valid_formula_update(self):
        # Update Part Number with valid formula
        self.db.edit_column(
            "Capacitor",
            "Part Number",
            "Part Number",
            "calculated",
            "'C-' & [Package] & '-' & [Value]",
        )
        schema = {f["name"]: f for f in self.db.get_table_schema("Capacitor")}
        self.assertEqual(schema["Part Number"]["type"], "calculated")
        self.assertIn("[Package]", schema["Part Number"]["expression"])

        # Fetch records to verify calculation works
        records = self.db.fetch_records("Capacitor")
        self.assertGreater(len(records), 0)
        first_pn = records[0].get("Part Number")
        self.assertTrue(first_pn and first_pn.startswith("C-"))

if __name__ == "__main__":
    unittest.main()
