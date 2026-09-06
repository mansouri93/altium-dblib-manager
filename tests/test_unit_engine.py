# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.altium.unit_engine import EngineeringValueParser, STANDARD_UNITS, PREFIX_MAP

class TestEngineeringUnitEngine(unittest.TestCase):
    def test_standard_parsing(self):
        # 10kΩ
        r = EngineeringValueParser.parse("10kΩ", default_unit="Ω")
        self.assertTrue(r["valid"])
        self.assertEqual(r["magnitude"], 10)
        self.assertEqual(r["prefix"], "k")
        self.assertEqual(r["unit"], "Ω")
        self.assertEqual(r["formatted"], "10kΩ")

        # 4.7µF
        r = EngineeringValueParser.parse("4.7µF", default_unit="F")
        self.assertTrue(r["valid"])
        self.assertEqual(r["magnitude"], 4.7)
        self.assertEqual(r["prefix"], "µ")
        self.assertEqual(r["unit"], "F")
        self.assertEqual(r["formatted"], "4.7µF")

    def test_shorthand_notation(self):
        # 4k7 -> 4.7kΩ
        r = EngineeringValueParser.parse("4k7", default_unit="Ω")
        self.assertTrue(r["valid"])
        self.assertEqual(r["magnitude"], 4.7)
        self.assertEqual(r["prefix"], "k")
        self.assertEqual(r["unit"], "Ω")
        self.assertEqual(r["formatted"], "4.7kΩ")

        # 2R2 -> 2.2Ω
        r = EngineeringValueParser.parse("2R2", default_unit="Ω")
        self.assertTrue(r["valid"])
        self.assertEqual(r["magnitude"], 2.2)
        self.assertEqual(r["prefix"], "")
        self.assertEqual(r["unit"], "Ω")
        self.assertEqual(r["formatted"], "2.2Ω")

        # 1n5 -> 1.5nF
        r = EngineeringValueParser.parse("1n5", default_unit="F")
        self.assertTrue(r["valid"])
        self.assertEqual(r["magnitude"], 1.5)
        self.assertEqual(r["prefix"], "n")
        self.assertEqual(r["unit"], "F")
        self.assertEqual(r["formatted"], "1.5nF")

    def test_normalization(self):
        # u to µ
        r = EngineeringValueParser.parse("100uF", default_unit="F")
        self.assertTrue(r["valid"])
        self.assertEqual(r["prefix"], "µ")
        self.assertEqual(r["formatted"], "100µF")

        # ohm to Ω
        r = EngineeringValueParser.parse("220 ohm", default_unit="Ω")
        self.assertTrue(r["valid"])
        self.assertEqual(r["unit"], "Ω")
        self.assertEqual(r["formatted"], "220Ω")

        # fraction
        r = EngineeringValueParser.parse("1/4 W", default_unit="W")
        self.assertTrue(r["valid"])
        self.assertEqual(r["magnitude"], "1/4")
        self.assertEqual(r["formatted"], "1/4 W")

        # percent
        r = EngineeringValueParser.parse("1%", default_unit="%")
        self.assertTrue(r["valid"])
        self.assertEqual(r["magnitude"], 1)
        self.assertEqual(r["formatted"], "1%")

    def test_validation(self):
        # Valid Resistor Value
        ok, fmt, err = EngineeringValueParser.validate("10kΩ", table_name="Resistor", col_name="Value")
        self.assertTrue(ok)
        self.assertEqual(fmt, "10kΩ")
        self.assertEqual(err, "")

        # Auto-appends default unit Ω if missing
        ok, fmt, err = EngineeringValueParser.validate("4k7", table_name="Resistor", col_name="Value")
        self.assertTrue(ok)
        self.assertEqual(fmt, "4.7kΩ")

        # Disallowed unit in Resistor Value (e.g. Farad)
        ok, fmt, err = EngineeringValueParser.validate("10uF", table_name="Resistor", col_name="Value")
        self.assertFalse(ok)
        self.assertIn("not allowed", err)

        # Invalid junk string
        ok, fmt, err = EngineeringValueParser.validate("invalid_text", table_name="Resistor", col_name="Value")
        self.assertFalse(ok)

if __name__ == "__main__":
    unittest.main()
