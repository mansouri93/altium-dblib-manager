# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.altium.unit_engine import ColumnUnitConfigManager, EngineeringValueParser
from app.ui.unit_config_dialog import ColumnUnitConfigDialog

app = QApplication.instance()
if not app:
    app = QApplication([])

class TestUnitConfigDialog(unittest.TestCase):
    def setUp(self):
        self.manager = ColumnUnitConfigManager.get_instance()
        # Ensure clean state for test table/column
        self.test_table = "TestCategory"
        self.test_col = "Custom_Voltage"
        self.manager.clear_override(self.test_table, self.test_col)

    def tearDown(self):
        self.manager.clear_override(self.test_table, self.test_col)

    def test_dialog_initial_state_and_save(self):
        dialog = ColumnUnitConfigDialog(self.test_table, self.test_col)
        self.assertFalse(dialog.chk_enable.isChecked())
        self.assertFalse(dialog.container_widget.isEnabled())

        # Enable and configure
        dialog.chk_enable.setChecked(True)
        self.assertTrue(dialog.container_widget.isEnabled())

        # Select unit 'V'
        v_idx = -1
        for i in range(dialog.cmb_unit.count()):
            if dialog.cmb_unit.itemData(i) == "V":
                v_idx = i
                break
        self.assertGreaterEqual(v_idx, 0)
        dialog.cmb_unit.setCurrentIndex(v_idx)

        # Select standard preset
        dialog._select_preset_prefixes()

        # Save
        dialog._on_save_clicked()

        # Verify config saved in manager
        cfg = self.manager.get_config(self.test_table, self.test_col)
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg["default_unit"], "V")
        self.assertIn("k", cfg["allowed_prefixes"])
        self.assertIn("m", cfg["allowed_prefixes"])

    def test_dialog_disable_unit(self):
        # Configure Resistor Value override to disabled
        dialog = ColumnUnitConfigDialog("Resistor", "Value")
        self.assertTrue(dialog.chk_enable.isChecked())

        # Click disable
        dialog._on_disable_clicked()

        # Check config is None (disabled)
        cfg = self.manager.get_config("Resistor", "Value")
        self.assertIsNone(cfg)

        # Clear override to restore default for Resistor Value
        dialog._on_reset_clicked()
        def_cfg = self.manager.get_config("Resistor", "Value")
        self.assertIsNotNone(def_cfg)
        self.assertEqual(def_cfg["default_unit"], "Ω")

if __name__ == "__main__":
    unittest.main()
