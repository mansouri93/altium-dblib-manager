# -*- coding: utf-8 -*-
import unittest
from pathlib import Path
import math
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

    def test_inductor_step_circles_and_backface_culling(self):
        """Verify STEP circle recovery, strict coplanar grouping, and back-face culling for WE-ACHC inductor."""
        pcblib = Path(r"altium-library-master\footprints\Power Inductors\PCB - POWER INDUCTORS - WURTH WE-ACHC 7449150046.PcbLib")
        if not pcblib.exists():
            self.skipTest("Wurth WE-ACHC PCBLIB not found")

        model = self.parser.get_model(pcblib, "WURTH WE-ACHC 7449150046")
        self.assertIsNotNone(model)
        self.assertTrue(model.has_3d_model)
        self.assertGreaterEqual(len(model.polygons), 98)

        # 1. Verify closed circle recovery for the white top sticker disc (Face #365)
        white_discs = [
            p for p in model.polygons
            if len(p.points) == 24 and p.area > 50.0 and p.color in ((255, 255, 255), (245, 245, 245), (240, 240, 240))
        ]
        self.assertGreaterEqual(len(white_discs), 1, "White circular sticker disc was not recovered")
        self.assertAlmostEqual(white_discs[0].center[2], 5.05, delta=0.1)

        # 2. Verify coplanar grouping strictly isolates opposing normals
        viewer = Footprint3DViewer()
        viewer.resize(600, 400)
        viewer.set_model(model)
        for g in viewer._planar_groups:
            if len(g) > 1:
                rep_n = g[0].normal
                for poly in g[1:]:
                    dot_n = poly.normal[0] * rep_n[0] + poly.normal[1] * rep_n[1] + poly.normal[2] * rep_n[2]
                    self.assertGreater(dot_n, 0.99, "Opposing normals must never be grouped together")

        # 3. Verify QPainter rendering succeeds without errors
        from PySide6.QtGui import QImage
        img = QImage(600, 400, QImage.Format.Format_ARGB32)
        img.fill(0)
        viewer.render(img)
        self.assertFalse(img.isNull())

    def test_shielded_inductor_cylinder_reconstruction(self):
        """Verify CYLINDRICAL_SURFACE quad panel decomposition for TDK SLF10165 drum core."""
        pcblib = Path(r"altium-library-master\footprints\Power Inductors\PCB - POWER INDUCTORS - TDK SLF10165.PCBLIB")
        if not pcblib.exists():
            self.skipTest("TDK SLF10165 PCBLIB not found")

        model = self.parser.get_model(pcblib, "TDK SLF10165")
        self.assertIsNotNone(model)
        self.assertTrue(model.has_3d_model)

        # Polygon count must reflect reconstructed cylinder panels (> 250, previously only 83)
        self.assertGreater(len(model.polygons), 250)

        # Real-world dimensions: 10.10mm x 10.10mm x 6.53mm
        self.assertAlmostEqual(model.length_mm, 10.10, delta=0.1)
        self.assertAlmostEqual(model.width_mm, 10.10, delta=0.1)
        self.assertAlmostEqual(model.height_mm, 6.53, delta=0.1)

        # Verify cylinder panels connecting base (Z <= 1.7mm) to top (Z >= 6.1mm)
        cylinder_panels = [
            p for p in model.polygons
            if len(p.points) == 4
            and min(pt[2] for pt in p.points) <= 1.7
            and max(pt[2] for pt in p.points) >= 6.1
        ]
        self.assertEqual(len(cylinder_panels), 24, "Main ferrite drum cylinder must produce 24 quad panels")

        # Verify outward radial normals of cylinder panels (Z component near 0, horizontal magnitude near 1)
        for panel in cylinder_panels:
            nx, ny, nz = panel.normal
            self.assertAlmostEqual(nz, 0.0, delta=0.01)
            h_mag = math.sqrt(nx * nx + ny * ny)
            self.assertAlmostEqual(h_mag, 1.0, delta=0.01)

        # Verify top blue cap sits flush above the cylinder
        blue_top_discs = [
            p for p in model.polygons
            if p.color[2] > 150 and p.color[0] < 50 and min(pt[2] for pt in p.points) >= 6.2
        ]
        self.assertGreaterEqual(len(blue_top_discs), 1, "Top blue cap disc must be present above cylinder")

        # Verify rendering succeeds
        from PySide6.QtGui import QImage
        viewer = Footprint3DViewer()
        viewer.resize(800, 600)
        viewer.set_model(model)
        img = QImage(800, 600, QImage.Format.Format_ARGB32)
        img.fill(0)
        viewer.render(img)
        self.assertFalse(img.isNull())

    def test_toroidal_surface_power_inductor_reconstruction(self):
        """Verify TOROIDAL_SURFACE extraction and parametric quad meshing for power inductors."""
        nr1005_pcblib = Path(r"altium-library-master\footprints\Power Inductors\PCB - POWER INDUCTORS - TAIYO YUDEN NR1005.PcbLib")
        if not nr1005_pcblib.exists():
            self.skipTest("Taiyo Yuden NR1005 PCBLIB not found")

        model = self.parser.get_model(nr1005_pcblib, "TAIYO YUDEN NR1005")
        self.assertIsNotNone(model)
        self.assertTrue(model.has_3d_model)

        # Real-world dimensions: 9.80mm x 8.01mm x 5.0mm
        self.assertAlmostEqual(model.length_mm, 9.80, delta=0.15)
        self.assertAlmostEqual(model.width_mm, 8.01, delta=0.15)
        self.assertAlmostEqual(model.height_mm, 5.00, delta=0.15)

        # Verify solid toroidal spool body (192 quad panels: 24 radial segments x 8 vertical slices)
        spool_panels = [
            p for p in model.polygons
            if len(p.points) == 4
            and min(pt[2] for pt in p.points) >= 0.99
            and max(pt[2] for pt in p.points) <= 4.21
            and max(math.sqrt(pt[0]**2 + pt[1]**2) for pt in p.points) < 4.0
        ]
        self.assertEqual(len(spool_panels), 192, "Toroidal winding spool must produce 192 quad panels connecting top and bottom flanges")

        # Verify waist radius at center Z=2.6mm is ~3.42mm (R_maj 6.525 - r_min 3.101 = 3.424mm)
        center_pts = [
            pt for p in spool_panels for pt in p.points
            if abs(pt[2] - 2.6) < 0.1
        ]
        self.assertGreater(len(center_pts), 0)
        for pt in center_pts:
            r = math.sqrt(pt[0]**2 + pt[1]**2)
            self.assertAlmostEqual(r, 3.424, delta=0.05)

        # Verify Bourns SRN4018 toroidal spool reconstruction
        srn4018_pcblib = Path(r"altium-library-master\footprints\Power Inductors\PCB - POWER INDUCTORS - BOURNS SRN4018.PcbLib")
        if srn4018_pcblib.exists():
            srn_model = self.parser.get_model(srn4018_pcblib, "BOURNS SRN4018")
            self.assertTrue(srn_model.has_3d_model)
            self.assertAlmostEqual(srn_model.length_mm, 4.10, delta=0.1)
            self.assertAlmostEqual(srn_model.width_mm, 4.10, delta=0.1)
            self.assertAlmostEqual(srn_model.height_mm, 1.80, delta=0.1)
            self.assertGreaterEqual(len(srn_model.polygons), 300)

        # Verify off-screen rendering
        from PySide6.QtGui import QImage
        viewer = Footprint3DViewer()
        viewer.resize(800, 600)
        viewer.set_model(model)
        img = QImage(800, 600, QImage.Format.Format_ARGB32)
        img.fill(0)
        viewer.render(img)
        self.assertFalse(img.isNull())


if __name__ == "__main__":
    unittest.main()

