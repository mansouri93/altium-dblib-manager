# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

app = QApplication.instance() or QApplication([])

from app.ui.library_browser import LibraryBrowserDialog, matches_all_keywords

class TestLibraryBrowserSearch(unittest.TestCase):
    """Unit tests for the multi-keyword order-independent search algorithm in Library Browser."""

    def test_multi_keyword_order_independent(self):
        # As requested by user:
        # Searching "0603 blue" must match both LED_0603_BLUE and LED_BLUE_0603
        query = "0603 blue"
        self.assertTrue(matches_all_keywords("LED_0603_BLUE", query))
        self.assertTrue(matches_all_keywords("LED_BLUE_0603", query))
        self.assertTrue(matches_all_keywords("LED-0603-BLUE", query))
        self.assertTrue(matches_all_keywords("LED 0603 BLUE", query))

    def test_multi_keyword_negative_matches(self):
        query = "0603 blue"
        # Missing blue
        self.assertFalse(matches_all_keywords("LED_0603_RED", query))
        self.assertFalse(matches_all_keywords("RES_0603_10K", query))
        # Missing 0603
        self.assertFalse(matches_all_keywords("LED_0805_BLUE", query))
        self.assertFalse(matches_all_keywords("CAP_1206_10UF", query))

    def test_case_insensitivity(self):
        self.assertTrue(matches_all_keywords("LED_0603_BLUE", "0603 BLUE"))
        self.assertTrue(matches_all_keywords("led_0603_blue", "0603 Blue"))
        self.assertTrue(matches_all_keywords("LED_BLUE_0603", "bLuE 0603"))

    def test_extra_whitespace_handling(self):
        self.assertTrue(matches_all_keywords("LED_0603_BLUE", "   0603    blue   "))
        self.assertTrue(matches_all_keywords("LED_0603_BLUE", "0603\tblue\n"))

    def test_empty_or_whitespace_query(self):
        self.assertTrue(matches_all_keywords("LED_0603_BLUE", ""))
        self.assertTrue(matches_all_keywords("LED_0603_BLUE", "   "))

    def test_single_keyword(self):
        self.assertTrue(matches_all_keywords("LED_0603_BLUE", "0603"))
        self.assertTrue(matches_all_keywords("LED_0603_BLUE", "blue"))
        self.assertTrue(matches_all_keywords("LED_0603_BLUE", "led"))
        self.assertFalse(matches_all_keywords("LED_0603_BLUE", "0805"))

    def test_file_path_filtering(self):
        file_target = "PCB - LED - LED 0603_1005 BLUE.PCBLIB footprints/LED"
        self.assertTrue(matches_all_keywords(file_target, "0603 blue"))
        self.assertTrue(matches_all_keywords(file_target, "led 0603"))
        self.assertTrue(matches_all_keywords(file_target, "pcblib blue"))
        self.assertFalse(matches_all_keywords(file_target, "0603 green"))

    def test_filtering_list_of_parts(self):
        parts = [
            "LED_0603_BLUE",
            "LED_BLUE_0603",
            "LED_0603_RED",
            "LED_0805_BLUE",
            "RES_0603_1K",
            "CAP_0603_100NF",
        ]
        filtered = [p for p in parts if matches_all_keywords(p, "0603 blue")]
        self.assertEqual(filtered, ["LED_0603_BLUE", "LED_BLUE_0603"])

    def test_ui_dialog_parts_filtering(self):
        """Test search filter integration inside LibraryBrowserDialog for both symbols and footprints."""
        for mode in ("SYMBOL", "FOOTPRINT"):
            dlg = LibraryBrowserDialog(mode=mode)
            dlg._all_parts_in_current_file = [
                "LED_0603_BLUE",
                "LED_BLUE_0603",
                "LED_0805_RED",
                "DIODE_SCHOTTKY",
            ]
            dlg.tabs_parts.setCurrentIndex(0)
            dlg.parts_list.clear()

            # Type text without pressing Enter -> Should not filter yet
            dlg.search_input.setText("0603 blue")
            self.assertEqual(dlg.parts_list.count(), 0)  # Not searched yet (initial was empty before text)

            # Press Enter -> Filters with 0603 blue
            dlg.search_input.returnPressed.emit()
            items = [dlg.parts_list.item(i).text() for i in range(dlg.parts_list.count())]
            self.assertEqual(items, ["LED_0603_BLUE", "LED_BLUE_0603"])
            self.assertEqual(dlg.tabs_parts.tabText(0), "In File (2)")

            # Clear filter -> Automatically resets list without needing Enter
            dlg.search_input.clear()
            self.assertEqual(dlg.parts_list.count(), 4)
            self.assertEqual(dlg.tabs_parts.tabText(0), "In File (4)")

            # Filter with non-matching keywords
            dlg.search_input.setText("0603 green")
            dlg.search_input.returnPressed.emit()
            self.assertEqual(dlg.parts_list.count(), 0)
            self.assertEqual(dlg.tabs_parts.tabText(0), "In File (0)")

    def test_ui_dialog_file_search_stack_toggle(self):
        """Test that file_search_input triggers only on Enter and resets when cleared."""
        dlg = LibraryBrowserDialog(mode="FOOTPRINT")
        # Initially on tree view (index 0)
        self.assertEqual(dlg.tree_stack.currentIndex(), 0)

        # Type search text without Enter -> Tree view stays at index 0
        dlg.file_search_input.setText("0603 blue")
        self.assertEqual(dlg.tree_stack.currentIndex(), 0)

        # Press Enter -> Switches to search results list at index 1
        dlg.file_search_input.returnPressed.emit()
        self.assertEqual(dlg.tree_stack.currentIndex(), 1)
        self.assertGreater(dlg.file_search_list.count(), 0)

        # Clear search text -> Automatically restores tree view at index 0
        dlg.file_search_input.clear()
        self.assertEqual(dlg.tree_stack.currentIndex(), 0)

    def test_compact_list_item_height(self):
        """Verify that items in file_search_list and parts_list are ultra-compact (<= 24px)."""
        dlg = LibraryBrowserDialog(mode="SYMBOL")
        dlg.show()
        # Add a sample item to parts_list
        from PySide6.QtWidgets import QListWidgetItem
        from app.ui.icons import AppIcons
        p_item = QListWidgetItem("TEST_PART_0603")
        dlg.parts_list.addItem(p_item)
        rect_parts = dlg.parts_list.visualItemRect(p_item)
        self.assertLessEqual(rect_parts.height(), 24, f"parts_list item too tall: {rect_parts.height()}px")

        # Add a sample item to file_search_list with icon
        f_item = QListWidgetItem("TEST_FILE.SchLib")
        f_item.setIcon(AppIcons.browse_symbol())
        dlg.file_search_list.addItem(f_item)
        rect_files = dlg.file_search_list.visualItemRect(f_item)
        self.assertLessEqual(rect_files.height(), 24, f"file_search_list item too tall: {rect_files.height()}px")
        dlg.close()

    def test_keyboard_navigation_updates_selection(self):
        """Verify that navigating with Up/Down arrow keys (currentItemChanged) updates selection and info."""
        dlg = LibraryBrowserDialog(mode="SYMBOL")
        dlg.parts_list.clear()
        dlg._all_parts_in_current_file = ["PART_A", "PART_B", "PART_C"]
        dlg.selected_file_path = "test/path/test.SchLib"
        dlg.tabs_parts.setCurrentIndex(0)
        from PySide6.QtWidgets import QListWidgetItem
        for p in dlg._all_parts_in_current_file:
            dlg.parts_list.addItem(QListWidgetItem(p))

        # Initially set current row to 0
        dlg.parts_list.setCurrentRow(0)
        self.assertEqual(dlg.selected_part_name, "PART_A")

        # Simulate Down Arrow navigation to row 1
        dlg.parts_list.setCurrentRow(1)
        self.assertEqual(dlg.selected_part_name, "PART_B")
        self.assertIn("PART_B", dlg.lbl_selection.text())

        # Simulate Down Arrow navigation to row 2
        dlg.parts_list.setCurrentRow(2)
        self.assertEqual(dlg.selected_part_name, "PART_C")
        self.assertIn("PART_C", dlg.lbl_selection.text())

        # Simulate Up Arrow navigation back to row 0
        dlg.parts_list.setCurrentRow(0)
        self.assertEqual(dlg.selected_part_name, "PART_A")
        self.assertIn("PART_A", dlg.lbl_selection.text())
        dlg.close()

if __name__ == "__main__":
    unittest.main()
