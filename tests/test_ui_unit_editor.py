# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from app.config import DB_PATH
from app.db.access_manager import AccessDBManager
from app.ui.main_window import MainWindow
from app.ui.value_editor import EngineeringValueEditor
from app.altium.unit_engine import EngineeringValueParser

class TestUIUnitEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        self.main_win = MainWindow()

    def tearDown(self):
        self.main_win.close()

    def test_value_editor_opens_for_value_column(self):
        # Select Resistor category
        self.main_win.table_model.load_table("Resistor")
        row_count = self.main_win.table_model.rowCount()
        self.assertGreater(row_count, 0)

        # Find column index for "Value"
        col_idx = self.main_win.table_model.columns.index("Value")
        src_idx = self.main_win.table_model.index(0, col_idx)
        proxy_idx = self.main_win.proxy_model.mapFromSource(src_idx)

        # Trigger edit on Value cell
        self.main_win.table_view.edit(proxy_idx)
        editor = self.main_win.table_view.findChild(EngineeringValueEditor)
        self.assertIsNotNone(editor, "EngineeringValueEditor should be spawned for Value column")

        # Check default configuration
        self.assertEqual(editor.default_unit, "Ω")
        self.assertIn("Ω", editor.allowed_units)

        # Simulate typing 4k7 in editor
        editor.txt_magnitude.setText("4k7")
        self.assertEqual(editor.get_value(), "4.7kΩ")
        is_ok, err = editor.is_valid()
        self.assertTrue(is_ok)

        # Simulate typing invalid unit
        editor.txt_magnitude.setText("100nF")
        is_ok, err = editor.is_valid()
        self.assertFalse(is_ok, "100nF should be invalid for Resistor Value")

if __name__ == "__main__":
    unittest.main()
