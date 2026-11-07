# -*- coding: utf-8 -*-
from __future__ import annotations
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.altium.parser import AltiumParser, part_id_to_name
from app.altium.preview_cache import PreviewCache


class TestMultipartSchematic(unittest.TestCase):
    """Test suite for Altium multi-part schematic symbol parsing, isolation, and rendering."""

    @classmethod
    def setUpClass(cls):
        cls.parser = AltiumParser()
        cls.cache = PreviewCache(cls.parser)
        cls.symbols_dir = ROOT / "altium-library-master" / "symbols"

    def test_part_id_to_name(self):
        """Verify 1-based part ID conversion to Altium Part letter labels."""
        self.assertEqual(part_id_to_name(1), "Part A")
        self.assertEqual(part_id_to_name(2), "Part B")
        self.assertEqual(part_id_to_name(3), "Part C")
        self.assertEqual(part_id_to_name(4), "Part D")
        self.assertEqual(part_id_to_name(26), "Part Z")
        self.assertEqual(part_id_to_name(27), "Part AA")
        self.assertEqual(part_id_to_name(0), "Part 0")

    def test_get_subpart_count_multipart(self):
        """Verify detection of sub-part counts on multi-part components."""
        lmv324_path = self.symbols_dir / "Opamp" / "SCH - OPAMP - 3PEAK LMV324B.SCHLIB"
        if lmv324_path.exists():
            count = self.parser.get_subpart_count(lmv324_path, "3PEAK LMV324B")
            self.assertEqual(count, 4)

        lm2904_path = self.symbols_dir / "Opamp" / "SCH - OPAMP - TI LM2904DR.SCHLIB"
        if lm2904_path.exists():
            count = self.parser.get_subpart_count(lm2904_path, "TI LM2904DR")
            self.assertEqual(count, 2)

    def test_get_subpart_count_single_part(self):
        """Verify single-part components return count of 1."""
        sn74_path = self.symbols_dir / "Logic" / "SCH - LOGIC - TI SN74LVC08APW.SchLib"
        if sn74_path.exists():
            count = self.parser.get_subpart_count(sn74_path, "TI SN74LVC08APW")
            self.assertEqual(count, 1)

    def test_get_subpart_count_edge_cases(self):
        """Verify non-existent files or invalid part names safely return 1."""
        self.assertEqual(self.parser.get_subpart_count("non_existent_file.SchLib", "Unknown"), 1)
        lmv324_path = self.symbols_dir / "Opamp" / "SCH - OPAMP - 3PEAK LMV324B.SCHLIB"
        if lmv324_path.exists():
            self.assertEqual(self.parser.get_subpart_count(lmv324_path, "NonExistentPart"), 1)

    def test_render_svg_separated_parts(self):
        """Verify each sub-part renders clean, isolated SVG without overlapping other parts."""
        lmv324_path = self.symbols_dir / "Opamp" / "SCH - OPAMP - 3PEAK LMV324B.SCHLIB"
        if not lmv324_path.exists():
            self.skipTest("LMV324B library not found")

        # Render Part A (subpart 1) and Part B (subpart 2)
        svg_part_a = self.parser.render_svg(lmv324_path, "3PEAK LMV324B", width=400, height=400, subpart_id=1)
        svg_part_b = self.parser.render_svg(lmv324_path, "3PEAK LMV324B", width=400, height=400, subpart_id=2)

        self.assertTrue(svg_part_a.startswith("<svg") or "<svg" in svg_part_a)
        self.assertTrue(svg_part_b.startswith("<svg") or "<svg" in svg_part_b)
        self.assertNotIn("Render error", svg_part_a)
        self.assertNotIn("Render error", svg_part_b)

        # Part A contains V+ power pin label, Part B does not
        self.assertIn("V+", svg_part_a)
        self.assertNotIn("V+", svg_part_b)

        # Confirm Part A and Part B SVGs are distinct
        self.assertNotEqual(svg_part_a, svg_part_b)

    def test_preview_cache_with_subparts(self):
        """Verify PreviewCache isolates cache keys per sub-part."""
        lm2904_path = str(self.symbols_dir / "Opamp" / "SCH - OPAMP - TI LM2904DR.SCHLIB")
        key_a = self.cache._cache_key(lm2904_path, "TI LM2904DR", 400, 400, subpart_id=1)
        key_b = self.cache._cache_key(lm2904_path, "TI LM2904DR", 400, 400, subpart_id=2)
        key_none = self.cache._cache_key(lm2904_path, "TI LM2904DR", 400, 400, subpart_id=None)

        self.assertNotEqual(key_a, key_b)
        self.assertNotEqual(key_a, key_none)

        if Path(lm2904_path).exists():
            svg_a = self.cache.get_svg(lm2904_path, "TI LM2904DR", subpart_id=1)
            svg_b = self.cache.get_svg(lm2904_path, "TI LM2904DR", subpart_id=2)
            self.assertNotEqual(svg_a, svg_b)
            self.assertNotIn("Render error", svg_a)
            self.assertNotIn("Render error", svg_b)


if __name__ == "__main__":
    unittest.main()
