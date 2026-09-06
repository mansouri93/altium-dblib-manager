# -*- coding: utf-8 -*-
import unittest
from pathlib import Path
import sys
from PySide6.QtWidgets import QApplication

# Ensure single QApplication instance for UI tests
app = QApplication.instance() or QApplication(sys.argv)

from app.altium.footprint_3d import Footprint3DParser, Footprint3DModel, Pad3D
from app.ui.footprint_3d_viewer import Footprint3DViewer
from app.ui.footprint_preview_widget import FootprintPreviewWidget


class TestFootprint3D(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = Footprint3DParser()
        cls.cap_pcblib = Path(r"altium-library-master\footprints\Capacitor - MLCC\PCB - CAPACITOR - MLCC - CAP 0402_1005.PCBLIB")
        cls.res_pcblib = Path(r"altium-library-master\footprints\Resistor - Chip\PCB - RESISTOR - CHIP - KOA RES RK73 RN73 0603_1608.PCBLIB")

    def test_step_model_extraction_capacitor(self):
        """Verify STEP 3D model parsing and real-world dimensions for 0402 Capacitor."""
        if not self.cap_pcblib.exists():
            self.skipTest("Capacitor 0402 PCBLIB not found")

        model = self.parser.get_model(self.cap_pcblib, "CAP 0402_1005")
        self.assertIsNotNone(model)
        self.assertTrue(model.has_3d_model)
        self.assertGreater(len(model.polygons), 20)
        self.assertGreaterEqual(len(model.pads), 2)

        # Real 0402 capacitor dimensions: ~1.00mm x ~0.52mm x ~0.52mm, Standoff 0.00mm
        self.assertAlmostEqual(model.length_mm, 1.00, delta=0.08)
        self.assertAlmostEqual(model.width_mm, 0.524, delta=0.08)
        self.assertAlmostEqual(model.height_mm, 0.524, delta=0.08)
        self.assertAlmostEqual(model.standoff_mm, 0.0, delta=0.05)

    def test_step_model_extraction_resistor(self):
        """Verify STEP 3D model parsing and real-world dimensions for 0603 Resistor."""
        if not self.res_pcblib.exists():
            self.skipTest("Resistor 0603 PCBLIB not found")

        model = self.parser.get_model(self.res_pcblib, "KOA RES RK73 RN73 0603_1608")
        self.assertIsNotNone(model)
        self.assertTrue(model.has_3d_model)
        self.assertGreater(len(model.polygons), 20)
        self.assertGreaterEqual(len(model.pads), 2)

        # 0603 (1608 metric) resistor dimensions: 1.60mm x 0.80mm x 0.45mm
        self.assertAlmostEqual(model.length_mm, 1.60, delta=0.10)
        self.assertAlmostEqual(model.width_mm, 0.80, delta=0.10)
        self.assertAlmostEqual(model.height_mm, 0.45, delta=0.10)
        self.assertAlmostEqual(model.standoff_mm, 0.0, delta=0.05)

        # Verify exact alignment between copper pad center and 3D body center
        pad_cx = sum(p.x for p in model.pads) / len(model.pads)
        pad_cy = sum(p.y for p in model.pads) / len(model.pads)
        body_cx = (model.bbox_min[0] + model.bbox_max[0]) / 2.0
        body_cy = (model.bbox_min[1] + model.bbox_max[1]) / 2.0
        self.assertAlmostEqual(pad_cx, body_cx, delta=0.05)
        self.assertAlmostEqual(pad_cy, body_cy, delta=0.05)

    def test_inch_scale_battery_holder(self):
        """Verify inch to mm conversion on STEP models with inch length units."""
        keystone_path = Path(r"altium-library-master\footprints\Battery Holder\PCB - BATTERY HOLDER - KEYSTONE 254.PCBLIB")
        if not keystone_path.exists():
            self.skipTest("Keystone 254 PCBLIB not found")

        model = self.parser.get_model(keystone_path, "KEYSTONE 254")
        self.assertIsNotNone(model)
        self.assertTrue(model.has_3d_model)
        # Keystone 254 is ~19.8mm x ~15.9mm (not 0.78in x 0.62in raw)
        self.assertGreater(model.length_mm, 15.0)
        self.assertGreater(model.width_mm, 10.0)

        # Pad and body center alignment
        pad_cx = sum(p.x for p in model.pads) / len(model.pads)
        pad_cy = sum(p.y for p in model.pads) / len(model.pads)
        body_cx = (model.bbox_min[0] + model.bbox_max[0]) / 2.0
        body_cy = (model.bbox_min[1] + model.bbox_max[1]) / 2.0
        self.assertAlmostEqual(pad_cx, body_cx, delta=0.1)
        self.assertAlmostEqual(pad_cy, body_cy, delta=0.1)

    def test_soic8_real_step_model_and_colors(self):
        """Verify Open CASCADE STEP model parsing for AD SOIC-8 S8+4 (not fallback cuboid)."""
        soic8_pcblib = Path(r"altium-library-master\footprints\Leaded - SOIC\PCB - LEADED - SOIC - AD SOIC-8 S8+4.PcbLib")
        if not soic8_pcblib.exists():
            self.skipTest("AD SOIC-8 S8+4 PCBLIB not found")

        model = self.parser.get_model(soic8_pcblib, "AD SOIC-8 S8+4")
        self.assertIsNotNone(model)
        self.assertTrue(model.has_3d_model)
        # Must have full 3D geometry (> 200 polygons), not a 6-sided fallback box
        self.assertGreater(len(model.polygons), 100)
        self.assertGreaterEqual(len(model.pads), 8)

        # Standard SOIC-8 dimensions: width across pins ~6.0mm, length ~5.0mm, height ~1.75mm
        self.assertAlmostEqual(model.length_mm, 6.00, delta=0.30)
        self.assertAlmostEqual(model.width_mm, 5.00, delta=0.30)
        self.assertAlmostEqual(model.height_mm, 1.75, delta=0.20)

        # Verify authentic colors extracted from STEP
        colors = set(p.color for p in model.polygons)
        # Should have dark epoxy body and silver pins
        self.assertTrue(any(c[0] < 80 and c[1] < 80 and c[2] < 80 for c in colors))
        self.assertTrue(any(c[0] > 180 and c[1] > 180 and c[2] > 180 for c in colors))

    def test_soic14_assembly_placement_and_pins(self):
        """Verify assembly placement transforms and pin instancing for SOIC-14."""
        soic14_pcblib = Path(r"altium-library-master\footprints\Leaded - SOIC\PCB - LEADED - SOIC - ANALOG DEV SOIC-14 R-14.PcbLib")
        if not soic14_pcblib.exists():
            self.skipTest("ANALOG DEV SOIC-14 R-14 PCBLIB not found")

        model = self.parser.get_model(soic14_pcblib, "ANALOG DEV SOIC-14 R-14")
        self.assertIsNotNone(model)
        self.assertTrue(model.has_3d_model)
        self.assertGreater(len(model.polygons), 250)
        self.assertEqual(len(model.pads), 14)

        # SOIC-14 dimensions: width across pins ~6.0mm, body length ~8.8mm, height ~1.75mm
        self.assertAlmostEqual(model.length_mm, 6.00, delta=0.30)
        self.assertAlmostEqual(model.width_mm, 8.80, delta=0.30)
        self.assertAlmostEqual(model.height_mm, 1.75, delta=0.20)

        # Verify pads and body centers align at (0, 0)
        body_cx = (model.bbox_min[0] + model.bbox_max[0]) / 2.0
        body_cy = (model.bbox_min[1] + model.bbox_max[1]) / 2.0
        self.assertAlmostEqual(body_cx, 0.0, delta=0.1)
        self.assertAlmostEqual(body_cy, 0.0, delta=0.1)

    def test_fallback_model_generation(self):
        """Verify clean 3D fallback box generation for footprints without embedded STEP models."""
        pads = [
            Pad3D(x=-1.0, y=0.0, width=0.8, height=0.6, designator="1"),
            Pad3D(x=1.0, y=0.0, width=0.8, height=0.6, designator="2"),
        ]
        model = self.parser._generate_fallback_model("GENERIC_SOIC", pads)
        self.assertFalse(model.has_3d_model)
        self.assertEqual(len(model.polygons), 6)  # 6-sided cuboid
        self.assertGreater(model.length_mm, 1.0)
        self.assertGreater(model.height_mm, 0.2)
        self.assertEqual(model.standoff_mm, 0.0)

    def test_footprint_3d_viewer_widget(self):
        """Verify Footprint3DViewer viewport widget, camera presets, and controls."""
        viewer = Footprint3DViewer()
        viewer.resize(400, 300)

        # Empty state
        viewer.show_placeholder("Select footprint")
        self.assertIsNone(viewer.model)

        # Set model
        if self.cap_pcblib.exists():
            model = self.parser.get_model(self.cap_pcblib, "CAP 0402_1005")
            viewer.set_model(model)
            self.assertIsNotNone(viewer.model)
            self.assertGreater(viewer.zoom, 0.0)

            # Test camera presets
            viewer.view_front()
            self.assertEqual(viewer.yaw, 0.0)
            self.assertEqual(viewer.pitch, 0.0)

            viewer.view_top()
            self.assertEqual(viewer.yaw, 0.0)
            self.assertEqual(viewer.pitch, 89.0)

            viewer.view_side()
            self.assertEqual(viewer.yaw, 90.0)
            self.assertEqual(viewer.pitch, 0.0)

            viewer.view_isometric()
            self.assertEqual(viewer.yaw, 45.0)
            self.assertEqual(viewer.pitch, 28.0)

            # Test dimensions toggle
            viewer.toggle_dimensions()
            self.assertFalse(viewer.show_dimensions)
            viewer.toggle_dimensions()
            self.assertTrue(viewer.show_dimensions)

    def test_footprint_preview_widget_container(self):
        """Verify FootprintPreviewWidget 2D/3D mode switcher and dual-view loading."""
        widget = FootprintPreviewWidget("Footprint Preview")
        widget.resize(500, 400)

        # Initial state
        self.assertEqual(widget.current_mode(), "2D")
        self.assertEqual(widget.stack.currentIndex(), 0)

        # Switch to 3D
        widget.set_mode("3D")
        self.assertEqual(widget.current_mode(), "3D")
        self.assertEqual(widget.stack.currentIndex(), 1)

        # Switch back to 2D
        widget.set_mode("2D")
        self.assertEqual(widget.current_mode(), "2D")
        self.assertEqual(widget.stack.currentIndex(), 0)

        # Load footprint
        if self.cap_pcblib.exists():
            widget.load_footprint(
                file_path=self.cap_pcblib,
                part_name="CAP 0402_1005",
                svg_str="<svg><rect/></svg>",
                title="CAP 0402_1005",
            )
            # Switch to 3D and verify model is populated
            widget.set_mode("3D")
            self.assertIsNotNone(widget.viewer_3d.model)
            self.assertAlmostEqual(widget.viewer_3d.model.length_mm, 1.0, delta=0.08)

        # Test placeholder
        widget.show_placeholder("No component selected")
        self.assertIsNone(widget.viewer_3d.model)


if __name__ == "__main__":
    unittest.main()
