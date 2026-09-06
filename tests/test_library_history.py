# -*- coding: utf-8 -*-
import sys
import unittest
import tempfile
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.altium.library_history import LibraryHistoryManager

class TestLibraryHistory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.hist_file = Path(self.temp_dir) / "test_history.json"
        self.manager = LibraryHistoryManager(history_file=self.hist_file)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_and_retrieve_entries(self):
        # Add symbols
        self.manager.add_entry("SYMBOL", "symbols/Passives/RES.SCHLIB", "Resistor")
        self.manager.add_entry("SYMBOL", "symbols/Passives/CAP.SCHLIB", "Capacitor")

        syms = self.manager.get_history("SYMBOL")
        self.assertEqual(len(syms), 2)
        # Most recent should be first (MRU)
        self.assertEqual(syms[0]["part_name"], "Capacitor")
        self.assertEqual(syms[1]["part_name"], "Resistor")

    def test_mru_deduplication(self):
        self.manager.add_entry("SYMBOL", "symbols/Passives/RES.SCHLIB", "Resistor")
        self.manager.add_entry("SYMBOL", "symbols/Passives/CAP.SCHLIB", "Capacitor")
        # Re-add Resistor -> should move to top
        self.manager.add_entry("SYMBOL", "symbols/Passives/RES.SCHLIB", "Resistor")

        syms = self.manager.get_history("SYMBOL")
        self.assertEqual(len(syms), 2)
        self.assertEqual(syms[0]["part_name"], "Resistor")
        self.assertEqual(syms[1]["part_name"], "Capacitor")

    def test_persistence_across_instances(self):
        self.manager.add_entry("FOOTPRINT", "footprints/0805.PCBLIB", "RES_0805")

        # Load from disk with fresh instance
        fresh = LibraryHistoryManager(history_file=self.hist_file)
        fps = fresh.get_history("FOOTPRINT")
        self.assertEqual(len(fps), 1)
        self.assertEqual(fps[0]["part_name"], "RES_0805")

    def test_clear_history(self):
        self.manager.add_entry("SYMBOL", "symbols/test.SCHLIB", "TestSym")
        self.manager.add_entry("FOOTPRINT", "footprints/test.PCBLIB", "TestFP")

        self.manager.clear_history("SYMBOL")
        self.assertEqual(len(self.manager.get_history("SYMBOL")), 0)
        self.assertEqual(len(self.manager.get_history("FOOTPRINT")), 1)

        self.manager.clear_history(None)
        self.assertEqual(len(self.manager.get_history("FOOTPRINT")), 0)

if __name__ == "__main__":
    unittest.main()
