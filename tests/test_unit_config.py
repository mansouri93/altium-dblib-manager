# -*- coding: utf-8 -*-
import sys
import unittest
import tempfile
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.altium.unit_engine import (
    EngineeringValueParser,
    ColumnUnitConfigManager,
    STANDARD_UNITS,
    ALL_PREFIX_SYMBOLS,
)

class TestColumnUnitConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "test_column_units.json"
        self.manager = ColumnUnitConfigManager(config_file=self.config_path)
        self._orig_instance = ColumnUnitConfigManager._instance
        ColumnUnitConfigManager._instance = self.manager

    def tearDown(self):
        ColumnUnitConfigManager._instance = self._orig_instance
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_all_required_units_present(self):
        required = ["Ω", "V", "A", "%", "F", "Hz", "H", "W", "dB", "s", "°C"]
        for u in required:
            self.assertIn(u, STANDARD_UNITS, f"Unit '{u}' missing from STANDARD_UNITS")

    def test_new_units_parsing(self):
        # dB
        r = EngineeringValueParser.parse("20dB", default_unit="dB")
        self.assertTrue(r["valid"])
        self.assertEqual(r["formatted"], "20dB")

        # seconds and milliseconds
        r = EngineeringValueParser.parse("100ms", default_unit="s")
        self.assertTrue(r["valid"])
        self.assertEqual(r["formatted"], "100ms")

        # Celsius
        r = EngineeringValueParser.parse("85°C", default_unit="°C")
        self.assertTrue(r["valid"])
        self.assertEqual(r["formatted"], "85°C")

        # Volts
        r = EngineeringValueParser.parse("3.3V", default_unit="V")
        self.assertTrue(r["valid"])
        self.assertEqual(r["formatted"], "3.3V")

        # Amperes
        r = EngineeringValueParser.parse("500mA", default_unit="A")
        self.assertTrue(r["valid"])
        self.assertEqual(r["formatted"], "500mA")

        # Hertz
        r = EngineeringValueParser.parse("16MHz", default_unit="Hz")
        self.assertTrue(r["valid"])
        self.assertEqual(r["formatted"], "16MHz")

        # Henry
        r = EngineeringValueParser.parse("2.2uH", default_unit="H")
        self.assertTrue(r["valid"])
        self.assertEqual(r["formatted"], "2.2µH")

    def test_custom_column_configuration(self):
        cfg = {
            "default_unit": "V",
            "allowed_units": ["V"],
            "allowed_prefixes": ["k", "", "m"],
            "allow_fraction": False,
        }
        self.manager.set_config("Capacitor", "V_Rating", cfg)

        got = self.manager.get_config("Capacitor", "V_Rating")
        self.assertIsNotNone(got)
        self.assertEqual(got["default_unit"], "V")
        self.assertTrue(got["enabled"])

        parser_cfg = EngineeringValueParser.get_column_config("Capacitor", "V_Rating")
        self.assertEqual(parser_cfg, got)

        ok, fmt, err = EngineeringValueParser.validate("50V", table_name="Capacitor", col_name="V_Rating")
        self.assertTrue(ok)
        self.assertEqual(fmt, "50V")

        ok, fmt, err = EngineeringValueParser.validate("50uF", table_name="Capacitor", col_name="V_Rating")
        self.assertFalse(ok)
        self.assertIn("not allowed", err)

    def test_disable_column_unit(self):
        def_cfg = self.manager.get_config("Resistor", "Tolerance")
        self.assertIsNotNone(def_cfg)

        self.manager.disable_config("Resistor", "Tolerance")
        disabled_cfg = self.manager.get_config("Resistor", "Tolerance")
        self.assertIsNone(disabled_cfg)

        ok, fmt, err = EngineeringValueParser.validate("arbitrary text 123", table_name="Resistor", col_name="Tolerance")
        self.assertTrue(ok)
        self.assertEqual(fmt, "arbitrary text 123")

        self.manager.clear_override("Resistor", "Tolerance")
        reverted_cfg = self.manager.get_config("Resistor", "Tolerance")
        self.assertIsNotNone(reverted_cfg)

    def test_persistence_to_disk(self):
        cfg = {
            "default_unit": "Hz",
            "allowed_units": ["Hz"],
            "allowed_prefixes": ["G", "M", "k", ""],
            "allow_fraction": False,
        }
        self.manager.set_config("Oscillator", "Frequency", cfg)

        new_manager = ColumnUnitConfigManager(config_file=self.config_path)
        loaded_cfg = new_manager.get_config("Oscillator", "Frequency")
        self.assertIsNotNone(loaded_cfg)
        self.assertEqual(loaded_cfg["default_unit"], "Hz")

if __name__ == "__main__":
    unittest.main()
