# -*- coding: utf-8 -*-
import unittest
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db.access_manager import AccessDBManager
from app.db.dblib_sync import DbLibSync
from app.altium.parser import AltiumParser
from app.altium.preview_cache import PreviewCache
from app.inventree.client import InvenTreeClient
from app.config import BASE_DIR, SYMBOLS_DIR, FOOTPRINTS_DIR

class SystemIntegrationTest(unittest.TestCase):

    def setUp(self):
        self.db = AccessDBManager()
        self.dblib = DbLibSync()
        self.parser = AltiumParser()
        self.cache = PreviewCache(self.parser)
        self.it = InvenTreeClient()

    def test_01_access_crud(self):
        test_tbl = "_test_system_tbl"
        # Ensure clean state
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(f"DROP TABLE [{test_tbl}]")
                conn.commit()
            except Exception:
                pass

        # 1. Create table
        self.assertTrue(self.db.create_category_table(test_tbl))
        tables = self.db.list_tables()
        self.assertIn(test_tbl, tables)

        # 2. Insert record
        new_id = self.db.insert_record(test_tbl, {
            "Part Number": "TEST-PART-123",
            "Description": "Test Component",
            "Value": "100k",
            "Stock": "25",
            "Location": "Rack-01",
        })
        self.assertGreater(new_id, 0)

        # 3. Fetch records
        records = self.db.fetch_records(test_tbl)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["Part Number"], "TEST-PART-123")
        self.assertEqual(records[0]["Location"], "Rack-01")

        # 4. Update cell (Stock as text)
        self.db.update_cell(test_tbl, new_id, "Stock", "50")
        records = self.db.fetch_records(test_tbl)
        self.assertEqual(records[0]["Stock"], "50")

        # 5. Batch update with unit and decimal (e.g. 2.5m)
        self.db.batch_update_stock_location(test_tbl, [(new_id, "Rack-02", "2.5m")])
        records = self.db.fetch_records(test_tbl)
        self.assertEqual(records[0]["Location"], "Rack-02")
        self.assertEqual(records[0]["Stock"], "2.5m")

        # 6. Delete record
        self.db.delete_record(test_tbl, new_id)
        records = self.db.fetch_records(test_tbl)
        self.assertEqual(len(records), 0)

        # Cleanup table
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(f"DROP TABLE [{test_tbl}]")
            conn.commit()

    def test_02_dblib_sync(self):
        registered = self.dblib.get_registered_tables()
        self.assertIn("Resistor", registered)

    def test_03_altium_preview_symbol_and_footprint(self):
        # Symbol test
        sch_path = SYMBOLS_DIR / "Passives" / "SCH - PASSIVES - RESISTOR.SCHLIB"
        self.assertTrue(sch_path.exists())
        parts = self.parser.list_parts(sch_path)
        self.assertIn("Resistor", parts)

        svg = self.cache.get_svg(str(sch_path), "Resistor")
        self.assertTrue(len(svg) > 100)
        self.assertIn("<svg", svg)

        # Footprint test
        pcb_path = FOOTPRINTS_DIR / "Resistor - Chip" / "PCB - RESISTOR - CHIP - RES 0805_2012.PCBLIB"
        self.assertTrue(pcb_path.exists())
        pcb_parts = self.parser.list_parts(pcb_path)
        self.assertIn("RES 0805_2012", pcb_parts)

        pcb_svg = self.cache.get_svg(str(pcb_path), "RES 0805_2012")
        self.assertTrue(len(pcb_svg) > 100)
        self.assertIn("<svg", pcb_svg)

    def test_04_inventree_client(self):
        ok, msg = self.it.test_connection()
        self.assertTrue(ok, f"InvenTree connection failed: {msg}")

        # Search
        results = self.it.search_parts("resistor", limit=5)
        self.assertTrue(len(results) > 0)

        # Test IPN lookup
        part = self.it.find_part_by_ipn("C-0805-100NF-50V")
        self.assertIsNotNone(part)
        stock, loc = self.it.get_stock_and_location(int(part["pk"]))
        self.assertGreaterEqual(stock, 0.0)
        self.assertTrue(len(loc) > 0)

    def test_05_warehouse_link_manager_and_normalization(self):
        from app.inventree.client import ComponentLinkManager
        from app.ui.warehouse_view import WarehouseLinkWidget

        lm = ComponentLinkManager()
        # Test explicit linking with unique test identifiers
        test_pk = 888877
        test_ipn = "TEST-UNIQUE-IPN-9999"
        lm.set_link("Resistor", 9999, {"pk": test_pk, "IPN": test_ipn, "name": "Resistor 1.5 kΩ"})
        link = lm.get_link("Resistor", 9999)
        self.assertIsNotNone(link)
        self.assertEqual(link["inventree_pk"], test_pk)
        self.assertEqual(link["inventree_ipn"], test_ipn)

        # Test lookup helpers
        self.assertEqual(lm.find_by_inventree_pk("Resistor", test_pk), 9999)
        self.assertEqual(lm.find_by_inventree_ipn("Resistor", test_ipn.lower()), 9999)
        all_links = lm.get_all_table_links("Resistor")
        self.assertIn(9999, all_links)

        # Test clear override
        lm.clear_override("Resistor", 9999)
        self.assertIsNone(lm.get_link("Resistor", 9999))
        self.assertIsNone(lm.find_by_inventree_pk("Resistor", 1234))

        # Test normalization logic
        from app.ui.warehouse_view import WarehouseLinkWidget
        dummy_widget = WarehouseLinkWidget.__new__(WarehouseLinkWidget)
        self.assertEqual(dummy_widget._normalize_pn("R-0603-1.5kΩ-1%"), "r-0603-1.5k-1%")
        self.assertEqual(dummy_widget._normalize_pn("R-0603-1R5K"), "r-0603-1.5k")
        self.assertEqual(dummy_widget._normalize_pn("R-0603-100R"), "r-0603-100")
        self.assertEqual(dummy_widget._normalize_pn("R-0805-15R4K"), "r-0805-15.4k")

    def test_06_table_spacers_and_scroll_alignment(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from app.ui.table_view import ComponentsTableModel, AltiumFilterProxyModel
        from app.ui.warehouse_view import WarehouseTableModel

        app = QApplication.instance() or QApplication([])

        # 1. Test ComponentsTableModel spacer rows
        model = ComponentsTableModel(self.db)
        model.columns = ["ID", "Part Number", "Value"]
        model.records = [
            {"ID": 1, "Part Number": "R1", "Value": "10k"},
            {"ID": 2, "Part Number": "R2", "Value": "20k"},
        ]
        self.assertEqual(model.rowCount(), 2)
        self.assertFalse(model.is_spacer_row(0))
        self.assertFalse(model.is_spacer_row(1))
        self.assertFalse(model.is_separator_row(0))

        # Add 3 spacers (1 separator + 2 spacer rows)
        model.set_spacer_count(3, "=== Separator ===")
        self.assertEqual(model.rowCount(), 5)
        self.assertFalse(model.is_spacer_row(1))
        self.assertTrue(model.is_spacer_row(2))
        self.assertTrue(model.is_separator_row(2))
        self.assertTrue(model.is_spacer_row(3))
        self.assertFalse(model.is_separator_row(3))

        # Verify header data: line numbers for real rows, empty for spacers
        self.assertEqual(model.headerData(0, Qt.Orientation.Vertical, Qt.ItemDataRole.DisplayRole), "1")
        self.assertEqual(model.headerData(1, Qt.Orientation.Vertical, Qt.ItemDataRole.DisplayRole), "2")
        self.assertEqual(model.headerData(2, Qt.Orientation.Vertical, Qt.ItemDataRole.DisplayRole), "")
        self.assertEqual(model.headerData(3, Qt.Orientation.Vertical, Qt.ItemDataRole.DisplayRole), "")

        # Verify separator content
        idx_sep = model.index(2, 0)
        self.assertEqual(model.data(idx_sep, Qt.ItemDataRole.DisplayRole), "=== Separator ===")

        # Verify spacer flags (non-selectable, non-editable)
        self.assertEqual(model.flags(idx_sep), Qt.ItemFlag.NoItemFlags)

        # 2. Test AltiumFilterProxyModel passes spacer rows through filter
        proxy = AltiumFilterProxyModel()
        proxy.setSourceModel(model)
        self.assertEqual(proxy.rowCount(), 5)

        # Filter by "R1" -> 1 real record + 3 spacers = 4 rows
        proxy.setFilterRegularExpression("R1")
        self.assertEqual(proxy.rowCount(), 4)

        # 3. Test WarehouseTableModel separator flags and header
        wh_model = WarehouseTableModel()
        wh_model.set_rows([
            {"status": "LINKED", "ipn": "R-1", "name": "Res 1"},
            {"is_separator": True, "title": "=== Unlinked ==="},
            {"status": "UNLINKED_WAREHOUSE", "ipn": "R-2", "name": "Res 2"},
        ])
        self.assertEqual(wh_model.rowCount(), 3)
        self.assertEqual(wh_model.headerData(0, Qt.Orientation.Vertical, Qt.ItemDataRole.DisplayRole), "1")
        self.assertEqual(wh_model.headerData(1, Qt.Orientation.Vertical, Qt.ItemDataRole.DisplayRole), "")
        self.assertEqual(wh_model.headerData(2, Qt.Orientation.Vertical, Qt.ItemDataRole.DisplayRole), "3")
        self.assertEqual(wh_model.flags(wh_model.index(1, 0)), Qt.ItemFlag.NoItemFlags)

    def test_07_app_settings_and_db_manager_connection(self):
        from app.config import (
            AppSettingsManager,
            DB_PATH,
            SYMBOLS_DIR,
            FOOTPRINTS_DIR,
        )
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_settings_file = Path(tmpdir) / "test_settings.json"
            mgr = AppSettingsManager(tmp_settings_file)
            self.assertEqual(mgr.get_db_path(), DB_PATH)
            self.assertEqual(mgr.get_symbols_dir(), SYMBOLS_DIR)
            self.assertEqual(mgr.get_footprints_dir(), FOOTPRINTS_DIR)

            # Test saving custom paths
            mgr.save_settings(db_path=DB_PATH)
            self.assertTrue(tmp_settings_file.exists())
            self.assertEqual(mgr.get_db_path(), DB_PATH)

        # Test AccessDBManager test_connection
        ok, msg = self.db.test_connection()
        self.assertTrue(ok, f"AccessDBManager test_connection failed: {msg}")

        # Test AccessDBManager with non-existent file
        fake_db = AccessDBManager(Path(r"C:\non_existent_path\fake.accdb"))
        fake_ok, fake_msg = fake_db.test_connection()
        self.assertFalse(fake_ok)

    def test_08_stock_unit_formatting_and_field_mappings(self):
        from app.config import format_stock_value, AppSettingsManager, DEFAULT_FIELD_MAPPINGS
        import tempfile

        # 1. Test format_stock_value
        self.assertEqual(format_stock_value(2.5, "m"), "2.5m")
        self.assertEqual(format_stock_value("2.5", "m"), "2.5m")
        self.assertEqual(format_stock_value(10.0, "m"), "10m")
        self.assertEqual(format_stock_value(0.5, "m"), "0.5m")
        self.assertEqual(format_stock_value(0, "m"), "0m")
        self.assertEqual(format_stock_value(20.0, "pcs", omit_pcs=True), "20")
        self.assertEqual(format_stock_value(20.0, "pcs", omit_pcs=False), "20pcs")
        self.assertEqual(format_stock_value(20.0, None), "20")
        self.assertEqual(format_stock_value(None, "m"), "")
        self.assertEqual(format_stock_value("", "m"), "")
        self.assertEqual(format_stock_value("125", "pcs", omit_pcs=True), "125")

        # 2. Test AppSettingsManager mappings
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_f = Path(tmpdir) / "app_settings.json"
            mgr = AppSettingsManager(tmp_f)
            mappings = mgr.get_field_mappings()
            self.assertGreaterEqual(len(mappings), 2)
            self.assertEqual(mappings[0]["db_column"], "Stock")

            # Save custom mappings
            custom_map = [
                {"enabled": True, "inventree_field": "total_in_stock", "db_column": "Stock"},
                {"enabled": True, "inventree_field": "location_name", "db_column": "Location"},
                {"enabled": True, "inventree_field": "Length", "db_column": "Comment"},
            ]
            mgr.save_field_mappings(custom_map, format_units=True, omit_pcs=True)
            self.assertTrue(tmp_f.exists())

            reloaded = AppSettingsManager(tmp_f)
            self.assertEqual(len(reloaded.get_field_mappings()), 3)
            fmt, omit = reloaded.get_stock_unit_options()
            self.assertTrue(fmt)
            self.assertTrue(omit)

    def test_09_batch_update_mapped_records_and_column_check(self):
        test_tbl = "_test_mapped_sync"
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(f"DROP TABLE [{test_tbl}]")
                conn.commit()
            except Exception:
                pass

        self.db.create_category_table(test_tbl)
        id1 = self.db.insert_record(test_tbl, {"Description": "Part 1", "Stock": "10"})
        id2 = self.db.insert_record(test_tbl, {"Description": "Part 2", "Stock": "0"})

        # Batch update multiple columns
        updates = [
            (id1, {"Stock": "2.5m", "Location": "Shelf-A", "Description": "Wire 2.5m"}),
            (id2, {"Stock": "100", "Location": "Shelf-B"}),
        ]
        updated = self.db.batch_update_mapped_records(test_tbl, updates)
        self.assertEqual(updated, 2)

        recs = self.db.fetch_records(test_tbl)
        self.assertEqual(recs[0]["Stock"], "2.5m")
        self.assertEqual(recs[0]["Location"], "Shelf-A")
        self.assertEqual(recs[0]["Description"], "Wire 2.5m")
        self.assertEqual(recs[1]["Stock"], "100")
        self.assertEqual(recs[1]["Location"], "Shelf-B")

        # Clean up
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(f"DROP TABLE [{test_tbl}]")
            conn.commit()

    def test_10_symbol_footprint_auto_columns_and_read_only(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QBrush
        from app.config import SYMBOL_FOOTPRINT_COLUMNS
        from app.ui.table_view import ComponentsTableModel

        test_tbl = "_test_fp_auto_cols"
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(f"DROP TABLE [{test_tbl}]")
                conn.commit()
            except Exception:
                pass

        # 1. Create bare table without symbol/footprint columns
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(f"CREATE TABLE [{test_tbl}] (ID COUNTER PRIMARY KEY, Description VARCHAR(255))")
            conn.commit()

        initial_cols = self.db.get_columns(test_tbl)
        self.assertEqual(initial_cols, ["ID", "Description"])

        # 2. Automatically ensure all 8 symbol and footprint columns
        added = self.db.ensure_symbol_footprint_columns(test_tbl)
        self.assertEqual(len(added), 8)
        cols_after = self.db.get_columns(test_tbl)
        for expected_col in SYMBOL_FOOTPRINT_COLUMNS:
            self.assertIn(expected_col, cols_after)

        # 3. Test multi-footprint data insertion & update (up to 3 footprints)
        rec_id = self.db.insert_record(test_tbl, {
            "Description": "Triple Footprint Resistor",
            "Library Ref": "Resistor",
            "Library Path": "Passives\\Resistor.SchLib",
            "Footprint Ref": "RES 0805",
            "Footprint Path": "Resistor\\RES_0805.PcbLib",
            "Footprint Ref 2": "RES 0603",
            "Footprint Path 2": "Resistor\\RES_0603.PcbLib",
            "Footprint Ref 3": "RES 1206",
            "Footprint Path 3": "Resistor\\RES_1206.PcbLib",
        })
        self.assertGreater(rec_id, 0)

        records = self.db.fetch_records(test_tbl)
        self.assertEqual(len(records), 1)
        r0 = records[0]
        self.assertEqual(r0["Footprint Ref"], "RES 0805")
        self.assertEqual(r0["Footprint Ref 2"], "RES 0603")
        self.assertEqual(r0["Footprint Ref 3"], "RES 1206")

        # 4. Test ComponentsTableModel read-only flags & dimmed styling
        model = ComponentsTableModel(self.db)
        model.load_table(test_tbl)

        for col_name in SYMBOL_FOOTPRINT_COLUMNS:
            c_idx = model.columns.index(col_name)
            idx = model.index(0, c_idx)
            flags = model.flags(idx)

            # ItemIsEditable MUST NOT be present
            self.assertFalse(bool(flags & Qt.ItemFlag.ItemIsEditable), f"{col_name} should not be editable")
            self.assertTrue(bool(flags & Qt.ItemFlag.ItemIsEnabled))
            self.assertTrue(bool(flags & Qt.ItemFlag.ItemIsSelectable))

            # setData must reject manual edits
            set_res = model.setData(idx, "HackedValue", Qt.ItemDataRole.EditRole)
            self.assertFalse(set_res, f"setData should reject edits on {col_name}")

            # ForegroundRole must return dimmed brush (#7e809b)
            fg_brush = model.data(idx, Qt.ItemDataRole.ForegroundRole)
            self.assertIsInstance(fg_brush, QBrush)
            self.assertEqual(fg_brush.color().name().lower(), "#7e809b")

            # ToolTipRole should explain system-managed read-only
            tooltip = model.data(idx, Qt.ItemDataRole.ToolTipRole)
            self.assertIn("Read-only", tooltip)

        # Standard editable column (Description) should allow editing
        desc_c_idx = model.columns.index("Description")
        desc_idx = model.index(0, desc_c_idx)
        desc_flags = model.flags(desc_idx)
        self.assertTrue(bool(desc_flags & Qt.ItemFlag.ItemIsEditable))

        # Clean up
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(f"DROP TABLE [{test_tbl}]")
            conn.commit()

    def test_11_smooth_scrolling_pixel_mode(self):
        from PySide6.QtWidgets import QApplication, QTableView
        from PySide6.QtGui import QStandardItemModel, QStandardItem
        from app.ui.smooth_scroll import enable_smooth_scroll, SmoothScrollFilter

        app = QApplication.instance() or QApplication([])

        tv = QTableView()
        model = QStandardItemModel(100, 20)
        for r in range(100):
            for c in range(20):
                model.setItem(r, c, QStandardItem(f"R{r}C{c}"))
        tv.setModel(model)

        # Before enable_smooth_scroll, default Qt is ScrollPerItem
        # Apply enable_smooth_scroll
        flt = enable_smooth_scroll(tv, step_v=45, step_h=60, duration_ms=100)

        # 1. Verify scroll mode is ScrollPerPixel for both axes (not cell-based)
        self.assertEqual(tv.verticalScrollMode(), QTableView.ScrollMode.ScrollPerPixel)
        self.assertEqual(tv.horizontalScrollMode(), QTableView.ScrollMode.ScrollPerPixel)

        # 2. Verify singleStep is configured properly
        self.assertEqual(tv.verticalScrollBar().singleStep(), 45)
        self.assertEqual(tv.horizontalScrollBar().singleStep(), 60)

        # 3. Verify SmoothScrollFilter is attached
        self.assertIsInstance(flt, SmoothScrollFilter)
        self.assertEqual(tv._smooth_scroll_filter, flt)

        # 4. Verify smooth animation interpolation can advance by non-cell pixel values
        tv.show()
        tv.resize(400, 300)
        app.processEvents()

        flt.v_anim.setStartValue(0)
        flt.v_anim.setEndValue(73)  # arbitrary pixel value not divisible by row height (30px)
        flt.v_anim.start()

        import time
        start = time.time()
        while time.time() - start < 0.2:
            app.processEvents()

        self.assertEqual(tv.verticalScrollBar().value(), 73)
        tv.close()

    def test_12_access_driver_detection(self):
        from app.db.access_manager import check_access_driver_installed

        installed, driver_name, download_url = check_access_driver_installed()
        self.assertIsInstance(installed, bool)
        self.assertIsInstance(driver_name, str)
        self.assertIn("microsoft.com", download_url.lower())
        self.assertTrue(installed, "Access ODBC driver should be installed on test machine")

    def test_13_create_new_database(self):
        from app.db.access_manager import AccessDBManager

        temp_db = Path("tests/data/temp_created_db.accdb")
        if temp_db.exists():
            try:
                temp_db.unlink()
            except Exception:
                pass

        try:
            created = AccessDBManager.create_new_database(temp_db)
            self.assertTrue(created)
            self.assertTrue(temp_db.exists())
            self.assertGreater(temp_db.stat().st_size, 0)

            mgr = AccessDBManager(temp_db)
            ok, msg = mgr.test_connection()
            self.assertTrue(ok, f"Failed to connect to newly created database: {msg}")

            # Verify creating a table in newly created database
            mgr.create_category_table("NewCategory", [
                {"name": "ID", "type": "autonumber"},
                {"name": "Part Number", "type": "short_text"},
                {"name": "Description", "type": "short_text"},
            ])
            tables = mgr.list_tables()
            self.assertIn("NewCategory", tables)

            # Insert record
            rid = mgr.insert_record("NewCategory", {"Part Number": "TEST-01", "Description": "Test Desc"})
            self.assertGreater(rid, 0)
            rows = mgr.fetch_records("NewCategory")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Part Number"], "TEST-01")
        finally:
            if temp_db.exists():
                try:
                    temp_db.unlink()
                except Exception:
                    pass

    def test_14_table_management_and_dblib_sync(self):
        from app.db.dblib_sync import DbLibSync

        tbl_name = "_test_manage_cat"
        renamed_tbl = "_test_manage_cat_renamed"

        # Cleanup before start
        try:
            self.db.drop_table(tbl_name)
        except Exception:
            pass
        try:
            self.db.drop_table(renamed_tbl)
        except Exception:
            pass

        dblib_sync = DbLibSync()

        # 1. Create table with custom fields
        fields = [
            {"name": "ID", "type": "autonumber"},
            {"name": "Part Number", "type": "short_text"},
            {"name": "Description", "type": "short_text"},
        ]
        self.db.create_category_table(tbl_name, fields)
        self.assertIn(tbl_name, self.db.list_tables())

        # Sync to .DbLib
        dblib_sync.sync_table_to_dblib(tbl_name, ["Part Number", "Description"])
        self.assertIn(tbl_name, dblib_sync.get_registered_tables())

        # 2. Rename table in DB and .DbLib
        self.db.rename_table(tbl_name, renamed_tbl)
        self.assertNotIn(tbl_name, self.db.list_tables())
        self.assertIn(renamed_tbl, self.db.list_tables())

        dblib_sync.rename_table_in_dblib(tbl_name, renamed_tbl)
        reg_tables = dblib_sync.get_registered_tables()
        self.assertNotIn(tbl_name, reg_tables)
        self.assertIn(renamed_tbl, reg_tables)

        # 3. Drop table in DB and .DbLib
        self.db.drop_table(renamed_tbl)
        self.assertNotIn(renamed_tbl, self.db.list_tables())

        dblib_sync.remove_table_from_dblib(renamed_tbl)
        self.assertNotIn(renamed_tbl, dblib_sync.get_registered_tables())

    def test_15_field_management_and_calculated_formula(self):
        tbl = "_test_calc_formula_tbl"
        try:
            self.db.drop_table(tbl)
        except Exception:
            pass

        # 1. Create table with Calculated Part Number formula
        fields = [
            {"name": "ID", "type": "autonumber"},
            {"name": "Part Number", "type": "calculated", "expression": '[Prefix] & "-" & [Value]'},
            {"name": "Prefix", "type": "short_text"},
            {"name": "Value", "type": "short_text"},
        ]
        self.db.create_category_table(tbl, fields)

        # Verify initial schema
        schema = self.db.get_table_schema(tbl)
        schema_dict = {f["name"]: f for f in schema}
        self.assertEqual(schema_dict["ID"]["type"], "autonumber")
        self.assertTrue(schema_dict["ID"]["is_primary_key"])
        self.assertEqual(schema_dict["Part Number"]["type"], "calculated")
        self.assertEqual(schema_dict["Part Number"]["expression"], '[Prefix] & "-" & [Value]')

        # 2. Insert record and verify Access calculates the Part Number
        rid = self.db.insert_record(tbl, {"Prefix": "RES", "Value": "100R"})
        rec = self.db.fetch_single_record(tbl, rid)
        self.assertEqual(rec["Part Number"], "RES-100R")

        # 3. Add Short Text and Long Text columns
        self.db.add_column(tbl, "Tolerance", "short_text")
        self.db.add_column(tbl, "Datasheet Path", "long_text")

        updated_schema = self.db.get_table_schema(tbl)
        updated_dict = {f["name"]: f for f in updated_schema}
        self.assertEqual(updated_dict["Tolerance"]["type"], "short_text")
        self.assertEqual(updated_dict["Datasheet Path"]["type"], "long_text")

        # 4. Mandatory protection: verify cannot delete ID or Part Number
        with self.assertRaises(ValueError):
            self.db.delete_column(tbl, "ID")
        with self.assertRaises(ValueError):
            self.db.delete_column(tbl, "Part Number")

        # 5. Edit calculated expression to include Tolerance
        self.db.edit_column(
            tbl,
            old_name="Part Number",
            new_name="Part Number",
            new_type="calculated",
            new_expression='[Prefix] & "-" & [Value] & "-" & [Tolerance]',
        )

        # Update row with tolerance
        self.db.update_cell(tbl, rid, "Tolerance", "5%")
        rec_after = self.db.fetch_single_record(tbl, rid)
        self.assertEqual(rec_after["Part Number"], "RES-100R-5%")

        # 6. Delete an optional column
        self.db.delete_column(tbl, "Datasheet Path")
        schema_final = self.db.get_table_schema(tbl)
        final_names = [f["name"] for f in schema_final]
        self.assertNotIn("Datasheet Path", final_names)

        # Clean up
        self.db.drop_table(tbl)

    def test_16_disable_widget_wheel_scroll(self):
        from PySide6.QtWidgets import QApplication, QComboBox, QSpinBox, QSlider, QScrollArea, QWidget, QVBoxLayout
        from PySide6.QtCore import Qt, QPoint, QPointF
        from PySide6.QtGui import QWheelEvent
        from app.ui.smooth_scroll import install_global_wheel_scroll_filter

        app = QApplication.instance() or QApplication([])
        flt = install_global_wheel_scroll_filter(app)
        self.assertIsNotNone(flt)

        scroll = QScrollArea()
        scroll.resize(400, 300)
        content = QWidget()
        layout = QVBoxLayout(content)

        cb_std = QComboBox()
        cb_std.addItems(["Alpha", "Beta", "Gamma", "Delta"])
        layout.addWidget(cb_std)

        cb_edit = QComboBox()
        cb_edit.setEditable(True)
        cb_edit.addItems(["First", "Second", "Third"])
        layout.addWidget(cb_edit)

        spinbox = QSpinBox()
        spinbox.setRange(0, 100)
        spinbox.setValue(25)
        layout.addWidget(spinbox)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(50)
        layout.addWidget(slider)

        # Add extra height so scroll area can scroll
        for i in range(30):
            layout.addWidget(QComboBox())

        scroll.setWidget(content)
        scroll.show()
        app.processEvents()

        evt = QWheelEvent(
            QPointF(10, 10),
            QPointF(10, 10),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )

        scroll_val_start = scroll.verticalScrollBar().value()

        # 1. Standard QComboBox
        app.sendEvent(cb_std, evt)
        self.assertEqual(cb_std.currentIndex(), 0, "Mouse wheel must NOT change combobox selection")
        self.assertGreater(scroll.verticalScrollBar().value(), scroll_val_start, "Scroll area should scroll on wheel")

        # 2. Editable QComboBox
        scroll_val_mid1 = scroll.verticalScrollBar().value()
        app.sendEvent(cb_edit, evt)
        self.assertEqual(cb_edit.currentIndex(), 0, "Mouse wheel must NOT change editable combobox selection")
        self.assertGreater(scroll.verticalScrollBar().value(), scroll_val_mid1)

        # 3. LineEdit inside Editable QComboBox
        if cb_edit.lineEdit():
            app.sendEvent(cb_edit.lineEdit(), evt)
            self.assertEqual(cb_edit.currentIndex(), 0, "Mouse wheel on LineEdit child must NOT change combobox selection")

        # 4. QSpinBox
        scroll_val_mid2 = scroll.verticalScrollBar().value()
        app.sendEvent(spinbox, evt)
        self.assertEqual(spinbox.value(), 25, "Mouse wheel must NOT change spinbox value")
        self.assertGreater(scroll.verticalScrollBar().value(), scroll_val_mid2)

        # 5. QSlider
        scroll_val_mid3 = scroll.verticalScrollBar().value()
        app.sendEvent(slider, evt)
        self.assertEqual(slider.value(), 50, "Mouse wheel must NOT change slider value")
        self.assertGreater(scroll.verticalScrollBar().value(), scroll_val_mid3)

        scroll.close()

if __name__ == "__main__":
    unittest.main()





