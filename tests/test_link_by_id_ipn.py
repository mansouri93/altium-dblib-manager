# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import shutil

from app.inventree.client import ComponentLinkManager


class TestLinkByIdAndIpn(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.lm = ComponentLinkManager(cache_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_link_persistence_and_lookups(self):
        # Link table 'Resistor' row 42 to InvenTree PK 317 (IPN: R-0603-100K)
        self.lm.set_link(
            "Resistor",
            42,
            {"pk": 317, "IPN": "R-0603-100K", "name": "Resistor 100 kOhm 0603 1%"},
        )

        link = self.lm.get_link("Resistor", 42)
        self.assertIsNotNone(link)
        self.assertEqual(link["inventree_pk"], 317)
        self.assertEqual(link["inventree_ipn"], "R-0603-100K")
        self.assertFalse(link["unlinked"])

        # Reverse lookups by InvenTree unique PK and IPN
        self.assertEqual(self.lm.find_by_inventree_pk("Resistor", 317), 42)
        self.assertEqual(self.lm.find_by_inventree_ipn("Resistor", "r-0603-100k"), 42)
        self.assertIsNone(self.lm.find_by_inventree_pk("Resistor", 999))
        self.assertIsNone(self.lm.find_by_inventree_ipn("Resistor", "unknown-ipn"))

        # Different table isolation
        self.assertIsNone(self.lm.get_link("Capacitor", 42))
        self.assertIsNone(self.lm.find_by_inventree_pk("Capacitor", 317))

        # Unlink component
        self.lm.remove_link("Resistor", 42)
        self.assertTrue(self.lm.is_explicitly_unlinked("Resistor", 42))
        self.assertIsNone(self.lm.find_by_inventree_pk("Resistor", 317))

    def test_sync_selected_uses_link_manager_not_part_number(self):
        from PySide6.QtWidgets import QApplication
        from app.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])

        win = MainWindow.__new__(MainWindow)
        win.link_manager = self.lm
        win.inventree_client = MagicMock()
        win.table_model = MagicMock()
        win.table_model.current_table = "Resistor"
        win.table_model.columns = ["ID", "Part Number", "Stock", "Location", "IPN"]
        win._get_current_source_row = MagicMock(return_value=0)
        win._on_table_row_selected = MagicMock()
        win.statusBar = MagicMock(return_value=MagicMock())
        win._apply_field_mappings = MagicMock(return_value={"Stock": 100, "Location": "R1"})

        # Record has a volatile Part Number formula but NO link yet
        rec_unlinked = {
            "ID": 12,
            "Part Number": "R-0603-100kOhm-1%",
            "Stock": "",
            "Location": "",
            "IPN": "",
        }
        win.table_model.get_record.return_value = rec_unlinked

        with patch("PySide6.QtWidgets.QMessageBox.question", return_value=0) as mock_q:
            win._on_sync_selected_inventree()
            # Must NOT call find_part_by_ipn with Part Number string!
            win.inventree_client.find_part_by_ipn.assert_not_called()
            # Must ask user to link
            mock_q.assert_called_once()

        # Now link row 12 in link_manager
        self.lm.set_link("Resistor", 12, {"pk": 317, "IPN": "R-0603-100K", "name": "Resistor 100k"})
        win.inventree_client.reset_mock()
        win.inventree_client.get_part_sync_data.return_value = {"total_in_stock": 100, "location_name": "R1"}

        win._on_sync_selected_inventree()
        # Must sync directly using PK 317 without any string search
        win.inventree_client.find_part_by_ipn.assert_not_called()
        win.inventree_client.get_part_sync_data.assert_called_once()
        self.assertEqual(win.inventree_client.get_part_sync_data.call_args[0][0], 317)


if __name__ == "__main__":
    unittest.main()
