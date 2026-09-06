# -*- coding: utf-8 -*-
import unittest
from PySide6.QtWidgets import QApplication
from app.ui.table_schema_dialog import FieldEditDialog

app = QApplication.instance() or QApplication([])

class FieldEditDialogTest(unittest.TestCase):
    def test_dialog_chips_and_combo(self):
        fields = ["ID", "Location", "Stock", "IPN", "Value", "Voltage", "Dielectric", "Package"]
        dlg = FieldEditDialog(existing_names=fields, is_part_number=True)

        # 1. Verify combo has all fields except ID
        combo_items = [dlg.cb_insert_field.itemText(i) for i in range(dlg.cb_insert_field.count())]
        self.assertIn("Package", combo_items)
        self.assertIn("Value", combo_items)
        self.assertIn("Voltage", combo_items)
        self.assertNotIn("ID", combo_items)

        # 2. Switch to calculated
        idx = dlg.cb_type.findData("calculated")
        dlg.cb_type.setCurrentIndex(idx)
        self.assertFalse(dlg.grp_calc.isHidden())

        # 3. Test insert tag
        dlg._insert_tag("Package")
        self.assertIn("[Package]", dlg.txt_expr.text())

        dlg._insert_tag("Value")
        self.assertEqual(dlg.txt_expr.text(), "[Package] & [Value]")

    def test_dialog_validation_detects_typos(self):
        fields = ["ID", "Location", "Stock", "IPN", "Value", "Voltage", "Dielectric", "Package"]
        field_data = {"name": "Part Number", "type": "short_text", "expression": ""}
        dlg = FieldEditDialog(existing_names=fields, field_data=field_data, is_part_number=True)

        idx = dlg.cb_type.findData("calculated")
        dlg.cb_type.setCurrentIndex(idx)

        # Set typo [Packege]
        dlg.txt_expr.setText("'C-' & [Packege] & '-' & [Value]")

        # Validate should detect [Packege] and not accept
        # Mock QMessageBox to verify warning
        from unittest.mock import patch
        with patch("app.ui.table_schema_dialog.QMessageBox.warning") as mock_warn:
            dlg._validate_and_accept()
            mock_warn.assert_called_once()
            args = mock_warn.call_args[0]
            self.assertIn("Invalid Formula Field", args[1])
            self.assertIn("Did you mean '[Package]'?", args[2])

if __name__ == "__main__":
    unittest.main()
