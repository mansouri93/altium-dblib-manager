# -*- coding: utf-8 -*-
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from app.inventree.client import ComponentLinkManager, TableCategoryManager


class TestTableWarehouseCategories(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_table_category_manager_crud(self) -> None:
        manager = TableCategoryManager(cache_dir=self.cache_dir)

        # Unconfigured table should return empty list
        self.assertEqual(manager.get_table_categories("Resistors"), [])

        # Configure categories
        manager.set_table_categories("Resistors", [12, 15, 12])
        self.assertEqual(manager.get_table_categories("Resistors"), [12, 15])

        # Persistence check
        manager2 = TableCategoryManager(cache_dir=self.cache_dir)
        self.assertEqual(manager2.get_table_categories("Resistors"), [12, 15])

        # Rename table
        manager2.rename_table("Resistors", "SMD_Resistors")
        self.assertEqual(manager2.get_table_categories("Resistors"), [])
        self.assertEqual(manager2.get_table_categories("SMD_Resistors"), [12, 15])

        # Remove table
        manager2.remove_table("SMD_Resistors")
        self.assertEqual(manager2.get_table_categories("SMD_Resistors"), [])

    def test_single_link_constraint_enforcement(self) -> None:
        link_manager = ComponentLinkManager(cache_dir=self.cache_dir)

        part_a = {"pk": 101, "IPN": "RES-0603-10K", "name": "Resistor 10k 0603"}

        # Link to TableA row 1
        link_manager.set_link("TableA", 1, part_a)
        link1 = link_manager.get_link("TableA", 1)
        self.assertIsNotNone(link1)
        self.assertFalse(link1["unlinked"])
        self.assertEqual(link1["inventree_pk"], 101)

        # Link same warehouse part to TableB row 2
        link_manager.set_link("TableB", 2, part_a)

        # TableB row 2 should now be linked
        link2 = link_manager.get_link("TableB", 2)
        self.assertIsNotNone(link2)
        self.assertFalse(link2["unlinked"])
        self.assertEqual(link2["inventree_pk"], 101)

        # TableA row 1 should be automatically unlinked to enforce single-link constraint
        link1_after = link_manager.get_link("TableA", 1)
        self.assertTrue(link1_after["unlinked"])

        # Cross table lookup check
        all_linked = link_manager.get_all_linked_parts_across_tables()
        self.assertIn(101, all_linked)
        tbl, row_id, _ = all_linked[101]
        self.assertEqual(tbl, "TableB")
        self.assertEqual(row_id, 2)

    def test_warehouse_view_three_way_grouping(self) -> None:
        import sys
        from PySide6.QtWidgets import QApplication
        from unittest.mock import MagicMock
        from app.ui.warehouse_view import WarehouseLinkWidget

        if not QApplication.instance():
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()

        mock_client = MagicMock()
        link_manager = ComponentLinkManager(cache_dir=self.cache_dir)
        cat_manager = TableCategoryManager(cache_dir=self.cache_dir)

        # Setup links:
        # Part 201 is linked to CurrentTable (Row 10)
        # Part 202 is linked to OtherTable (Row 5)
        # Part 203 is unlinked
        part_201 = {"pk": 201, "IPN": "CAP-0603-100NF", "name": "Capacitor 100nF"}
        part_202 = {"pk": 202, "IPN": "CAP-0805-10UF", "name": "Capacitor 10uF"}
        part_203 = {"pk": 203, "IPN": "CAP-1206-47UF", "name": "Capacitor 47uF"}

        link_manager.set_link("CurrentTable", 10, part_201)
        link_manager.set_link("OtherTable", 5, part_202)

        cat_manager.set_table_categories("CurrentTable", [50])

        widget = WarehouseLinkWidget(
            inventree_client=mock_client,
            link_manager=link_manager,
            category_manager=cat_manager,
        )

        # Cached warehouse parts has all 3 parts
        widget.cached_warehouse_parts = [part_201, part_202, part_203]

        # Current Altium records has 2 components: ID=10 (linked to 201) and ID=11 (unmatched)
        altium_records = [
            {"ID": 10, "Part Number": "C0603-100NF", "IPN": "CAP-0603-100NF"},
            {"ID": 11, "Part Number": "C0603-1PF", "IPN": ""},
        ]

        widget.current_altium_table = "CurrentTable"
        widget.altium_records = altium_records
        widget._build_table_rows()

        rows = widget.table_model.rows

        # Row 0: Aligned with Altium row 0 (ID 10) -> LINKED
        self.assertEqual(rows[0]["status"], "LINKED")
        self.assertEqual(rows[0]["inventree_part"]["pk"], 201)

        # Row 1: Aligned with Altium row 1 (ID 11) -> UNMATCHED_ALTIUM
        self.assertEqual(rows[1]["status"], "UNMATCHED_ALTIUM")

        # Row 2: Separator for unlinked parts
        self.assertTrue(rows[2].get("is_separator"))
        self.assertIn("Unlinked Warehouse Parts", rows[2]["title"])

        # Row 3: Part 203 -> UNLINKED_WAREHOUSE
        self.assertEqual(rows[3]["status"], "UNLINKED_WAREHOUSE")
        self.assertEqual(rows[3]["inventree_part"]["pk"], 203)

        # Row 4: Separator for already linked to other tables
        self.assertTrue(rows[4].get("is_separator"))
        self.assertIn("Already Linked to Other Tables", rows[4]["title"])

        # Row 5: Part 202 -> LINKED_OTHER
        self.assertEqual(rows[5]["status"], "LINKED_OTHER")
        self.assertEqual(rows[5]["inventree_part"]["pk"], 202)
        self.assertEqual(rows[5]["other_table"], "OtherTable")
        self.assertEqual(rows[5]["other_row_id"], 5)

        # Check action widget on Row 3 (UNLINKED_WAREHOUSE): should contain "Add" and "Link to" buttons
        from PySide6.QtWidgets import QPushButton
        action_idx = widget.table_model.index(3, 5)
        container = widget.table_view.indexWidget(action_idx)
        self.assertIsNotNone(container)
        btns = container.findChildren(QPushButton)
        self.assertEqual(len(btns), 2)
        btn_texts = [b.text().strip() for b in btns]
        self.assertIn("Add", btn_texts)
        self.assertIn("Link to", btn_texts)

        # Clicking "Link to" must emit link_warehouse_to_altium_requested
        emitted = []
        widget.link_warehouse_to_altium_requested.connect(lambda p: emitted.append(p))
        btn_link = next(b for b in btns if "Link to" in b.text())
        btn_link.click()
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["pk"], 203)

        widget.deleteLater()

    def test_category_filter_dialog_tree_cascading(self) -> None:
        import sys
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from app.ui.warehouse_view import CategoryFilterDialog

        if not QApplication.instance():
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()

        all_cats = [
            {"pk": 1, "name": "Root A", "parent": None, "part_count": 10},
            {"pk": 2, "name": "Child A1", "parent": 1, "part_count": 4},
            {"pk": 3, "name": "Child A2", "parent": 1, "part_count": 6},
            {"pk": 4, "name": "Grandchild A1-1", "parent": 2, "part_count": 4},
            {"pk": 5, "name": "Root B", "parent": None, "part_count": 2},
        ]

        # Case 1: Initial selection with parent ID expands to all descendants
        dlg = CategoryFilterDialog(all_cats, initial_selected_ids={1})
        self.assertEqual(dlg.get_selected_ids(), {1, 2, 3, 4})
        root_item = dlg.tree.topLevelItem(0)
        self.assertEqual(root_item.checkState(0), Qt.CheckState.Checked)
        child_a1 = root_item.child(0)
        child_a2 = root_item.child(1)
        grandchild = child_a1.child(0)
        self.assertEqual(child_a1.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(child_a2.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(grandchild.checkState(0), Qt.CheckState.Checked)

        # Case 2: Unchecking Child A2 updates parent to PartiallyChecked and removes 3 & 1
        child_a2.setCheckState(0, Qt.CheckState.Unchecked)
        dlg._on_item_changed(child_a2, 0)
        self.assertEqual(root_item.checkState(0), Qt.CheckState.PartiallyChecked)
        self.assertEqual(dlg.get_selected_ids(), {2, 4})

        # Case 3: Re-checking Child A2 restores Checked state to parent
        child_a2.setCheckState(0, Qt.CheckState.Checked)
        dlg._on_item_changed(child_a2, 0)
        self.assertEqual(root_item.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(dlg.get_selected_ids(), {1, 2, 3, 4})

        # Case 4: Unchecking Root A unchecks all descendants
        root_item.setCheckState(0, Qt.CheckState.Unchecked)
        dlg._on_item_changed(root_item, 0)
        self.assertEqual(root_item.checkState(0), Qt.CheckState.Unchecked)
        self.assertEqual(child_a1.checkState(0), Qt.CheckState.Unchecked)
        self.assertEqual(child_a2.checkState(0), Qt.CheckState.Unchecked)
        self.assertEqual(grandchild.checkState(0), Qt.CheckState.Unchecked)
        self.assertEqual(dlg.get_selected_ids(), set())

        # Case 5: Checking Root A checks all descendants
        root_item.setCheckState(0, Qt.CheckState.Checked)
        dlg._on_item_changed(root_item, 0)
        self.assertEqual(root_item.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(child_a1.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(child_a2.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(grandchild.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(dlg.get_selected_ids(), {1, 2, 3, 4})

        dlg.deleteLater()

    def test_warehouse_view_force_reload(self) -> None:
        import sys
        from PySide6.QtWidgets import QApplication
        from unittest.mock import MagicMock
        from app.ui.warehouse_view import WarehouseLinkWidget

        if not QApplication.instance():
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()

        mock_client = MagicMock()
        mock_client.get_all_categories.return_value = [{"pk": 10, "name": "Resistors"}]
        mock_client.get_parts_by_categories.return_value = [{"pk": 999, "IPN": "RES-1"}]

        link_manager = ComponentLinkManager(cache_dir=self.cache_dir)
        cat_manager = TableCategoryManager(cache_dir=self.cache_dir)
        cat_manager.set_table_categories("MyTable", [10])

        widget = WarehouseLinkWidget(
            inventree_client=mock_client,
            link_manager=link_manager,
            category_manager=cat_manager,
        )

        widget.current_altium_table = "MyTable"
        widget.selected_category_ids = set()

        # Without force_reload, same table name does not reload inventory
        widget.set_altium_context("MyTable", [], force_reload=False)
        self.assertEqual(widget.selected_category_ids, set())

        # With force_reload=True, inventory and categories are reloaded
        widget.set_altium_context("MyTable", [], force_reload=True)
        self.assertEqual(widget.selected_category_ids, {10})
        self.assertEqual(len(widget.cached_warehouse_parts), 1)

        widget.deleteLater()


if __name__ == "__main__":
    unittest.main()

