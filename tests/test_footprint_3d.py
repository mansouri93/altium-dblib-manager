# -*- coding: utf-8 -*-
import unittest
from pathlib import Path
import math
import sys
from PySide6.QtWidgets import QApplication

# Ensure single QApplication instance for UI tests
app = QApplication.instance() or QApplication(sys.argv)

from app.altium.footprint_3d import (
    Footprint3DParser,
    Footprint3DModel,
    Pad3D,
    FootprintLine3D,
    FootprintArc3D,
)
from app.ui.footprint_3d_viewer import Footprint3DViewer, _get_pad_profile_2d, _get_annular_pad_profiles
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

        # 1. Verify closed circle recovery for the white top sticker disc
        white_discs = [
            p for p in model.polygons
            if (p.color in ((255, 255, 255), (245, 245, 245), (240, 240, 240)) or (p.color[0] > 230 and p.color[1] > 230 and p.color[2] > 230))
            and abs(p.center[2] - 5.05) < 0.1
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

        # Verify cylinder panels connecting drum core
        cylinder_panels = [
            p for p in model.polygons
            if min(pt[2] for pt in p.points) >= 1.5
            and max(pt[2] for pt in p.points) <= 6.5
            and math.sqrt(p.normal[0]**2 + p.normal[1]**2) > 0.95
        ]
        self.assertGreaterEqual(len(cylinder_panels), 24, "Main ferrite drum cylinder must produce cylinder facets")

        # Verify outward radial normals of cylinder panels (Z component near 0, horizontal magnitude near 1)
        for panel in cylinder_panels[:24]:
            nx, ny, nz = panel.normal
            self.assertAlmostEqual(nz, 0.0, delta=0.15)
            h_mag = math.sqrt(nx * nx + ny * ny)
            self.assertAlmostEqual(h_mag, 1.0, delta=0.05)

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

        # Real-world dimensions: 9.80mm x 10.00mm x 5.0mm (Taiyo Yuden NR10050 standard)
        self.assertAlmostEqual(model.length_mm, 9.80, delta=0.2)
        self.assertAlmostEqual(model.width_mm, 10.00, delta=0.2)
        self.assertAlmostEqual(model.height_mm, 5.00, delta=0.2)

        # Verify solid toroidal spool body (connecting top and bottom flanges)
        spool_panels = [
            p for p in model.polygons
            if min(pt[2] for pt in p.points) >= 0.99
            and max(pt[2] for pt in p.points) <= 4.21
            and max(math.sqrt(pt[0]**2 + pt[1]**2) for pt in p.points) < 4.0
        ]
        self.assertGreaterEqual(len(spool_panels), 50, "Toroidal winding spool must produce panels connecting top and bottom flanges")

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

    def test_wurth_we_hcf_native_alignment(self):
        """Verify native Altium PCB coordinates and STEP alignment on WURTH WE-HCF 14.5MM."""
        pcblib = Path(r"altium-library-master\footprints\Power Inductors\PCB - POWER INDUCTORS - WURTH WE-HCF 14.5MM.PcbLib")
        if not pcblib.exists():
            self.skipTest("WURTH WE-HCF PCBLIB not found")

        model = self.parser.get_model(pcblib, "WURTH WE-HCF 14.5MM")
        self.assertIsNotNone(model)
        self.assertTrue(model.has_3d_model)

        # Pad 3 is at Y = +8.5 (single pad)
        # Pads 1 and 2 are at Y = -8.5 (pair of pads)
        pad3 = next((p for p in model.pads if p.designator == "3"), None)
        self.assertIsNotNone(pad3)
        self.assertAlmostEqual(pad3.y, 8.5, delta=0.2)

        # Bottom pin contact faces (Z near 0)
        pin_faces = [
            poly for poly in model.polygons
            if poly.color[0] > 130 and poly.color[1] > 130 and poly.color[2] > 130
            and abs(poly.normal[2] - (-1.0)) < 0.1 and abs(poly.center[2]) < 0.1
        ]
        self.assertGreater(len(pin_faces), 0, "Pin contact surfaces must be present at Z=0")

        # Single pin should be at positive Y (aligned with Pad 3), pair of pins at negative Y (aligned with Pads 1 and 2)
        pos_y_pins = [p for p in pin_faces if p.center[1] > 0]
        neg_y_pins = [p for p in pin_faces if p.center[1] < 0]

        self.assertGreater(len(pos_y_pins), 0, "Single pin contact surface must land at positive Y near Pad 3")
        self.assertGreater(len(neg_y_pins), 0, "Double pin contact surfaces must land at negative Y near Pads 1 and 2")

        # Average Y of positive pin cluster must be near +8.85, negative near -8.43
        avg_pos_y = sum(p.center[1] for p in pos_y_pins) / len(pos_y_pins)
        avg_neg_y = sum(p.center[1] for p in neg_y_pins) / len(neg_y_pins)
        self.assertAlmostEqual(avg_pos_y, 8.85, delta=1.0)
        self.assertAlmostEqual(avg_neg_y, -8.43, delta=1.0)

    def test_soic8_pin1_pad1_alignment(self):
        """Verify Pin 1 dot and Pad 1 exact physical alignment on AD SOIC-8 S8+4."""
        soic8_pcblib = Path(r"altium-library-master\footprints\Leaded - SOIC\PCB - LEADED - SOIC - AD SOIC-8 S8+4.PcbLib")
        if not soic8_pcblib.exists():
            self.skipTest("AD SOIC-8 S8+4 PCBLIB not found")

        model = self.parser.get_model(soic8_pcblib, "AD SOIC-8 S8+4")
        self.assertIsNotNone(model)
        self.assertTrue(model.has_3d_model)

        pad1 = next((p for p in model.pads if p.designator == "1"), None)
        pad4 = next((p for p in model.pads if p.designator == "4"), None)
        self.assertIsNotNone(pad1)
        self.assertIsNotNone(pad4)

        # Pad 1 is at positive Y in native Altium PCB (+1.905mm)
        # Pad 4 is at negative Y (-1.905mm)
        self.assertAlmostEqual(pad1.x, -2.465, delta=0.05)
        self.assertAlmostEqual(pad1.y, 1.905, delta=0.05)
        self.assertAlmostEqual(pad4.x, -2.465, delta=0.05)
        self.assertAlmostEqual(pad4.y, -1.905, delta=0.05)

        # Pin 1 circular white dot should land at positive Y near Pad 1 (Y ~ +1.89mm)
        pin1_dots = [
            p for p in model.polygons
            if p.color == (255, 255, 255) and abs(p.center[2] - 1.65) < 0.05
        ]
        self.assertGreater(len(pin1_dots), 0, "White Pin 1 indicator dot must be present near Pad 1")
        avg_dot_y = sum(p.center[1] for p in pin1_dots) / len(pin1_dots)
        self.assertAlmostEqual(avg_dot_y, 1.89, delta=0.05)
        self.assertAlmostEqual(abs(avg_dot_y - pad1.y), 0.017, delta=0.02)

    def test_footprint_layer_graphics_and_pad_thickness(self):
        """Verify pad 0.1mm thickness downwards and layer graphics extraction."""
        soic8_pcblib = Path(r"altium-library-master\footprints\Leaded - SOIC\PCB - LEADED - SOIC - AD SOIC-8 S8+4.PcbLib")
        if not soic8_pcblib.exists():
            self.skipTest("AD SOIC-8 S8+4 PCBLIB not found")

        model = self.parser.get_model(soic8_pcblib, "AD SOIC-8 S8+4")
        self.assertIsNotNone(model)

        # 1. Pads 0.1mm thickness downwards (0.0 to -0.1mm)
        for pad in model.pads:
            self.assertEqual(pad.z_top, 0.0)
            self.assertEqual(pad.z_bottom, -0.1)

        # 2. Layer graphics presence
        self.assertGreater(len(model.lines), 10)
        self.assertGreater(len(model.arcs), 1)

        # 3. Layer color separation
        silkscreen_lines = [l for l in model.lines if l.layer_id == 33]
        mechanical_lines = [l for l in model.lines if l.layer_id in (69, 71)]
        self.assertGreater(len(silkscreen_lines), 0)
        self.assertGreater(len(mechanical_lines), 0)

        # Silkscreen should be white, Mechanical should be cyan
        self.assertTrue(all(l.color == (0.96, 0.96, 0.98) for l in silkscreen_lines))
        self.assertTrue(all(l.color == (0.31, 0.80, 0.77) for l in mechanical_lines))

    def test_pad_shape_profiles_and_winding(self):
        """Verify 2D profiles for all Altium pad shapes and ensure strict CCW winding."""
        def signed_area(pts):
            n = len(pts)
            return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))

        # 1. Round (Circle)
        pad_circ = Pad3D(x=0, y=0, width=2.0, height=2.0, shape="ROUND")
        prof_circ = _get_pad_profile_2d(pad_circ)
        self.assertGreaterEqual(len(prof_circ), 24)
        self.assertGreater(signed_area(prof_circ), 0.0)

        # 2. Round (Tall Oblong)
        pad_tall = Pad3D(x=0, y=0, width=1.5, height=3.0, shape="ROUND")
        prof_tall = _get_pad_profile_2d(pad_tall)
        self.assertGreaterEqual(len(prof_tall), 16)
        self.assertGreater(signed_area(prof_tall), 0.0)

        # 3. Round (Wide Oblong)
        pad_wide = Pad3D(x=0, y=0, width=3.0, height=1.5, shape="ROUND")
        prof_wide = _get_pad_profile_2d(pad_wide)
        self.assertGreaterEqual(len(prof_wide), 16)
        self.assertGreater(signed_area(prof_wide), 0.0)

        # 4. Rounded Rectangle
        pad_rr = Pad3D(x=0, y=0, width=2.5, height=3.5, shape="ROUNDED_RECTANGLE", corner_radius_percentage=30.0)
        prof_rr = _get_pad_profile_2d(pad_rr)
        self.assertGreaterEqual(len(prof_rr), 20)
        self.assertGreater(signed_area(prof_rr), 0.0)

        # 5. Octagonal
        pad_oct = Pad3D(x=0, y=0, width=2.0, height=2.0, shape="OCTAGONAL")
        prof_oct = _get_pad_profile_2d(pad_oct)
        self.assertEqual(len(prof_oct), 8)
        self.assertGreater(signed_area(prof_oct), 0.0)

        # 6. Rectangular
        pad_rect = Pad3D(x=0, y=0, width=1.0, height=2.0, shape="RECTANGULAR")
        prof_rect = _get_pad_profile_2d(pad_rect)
        self.assertEqual(len(prof_rect), 4)
        self.assertGreater(signed_area(prof_rect), 0.0)

    def test_switch_pad_shapes_oblong_extraction(self):
        """Verify extraction of real-world oblong/round pad shapes from SK-13D07 switch."""
        sw_pcblib = Path(r"altium-library-master\footprints\Switch\PCB - SWITCH - SK-13D07.PcbLib")
        if not sw_pcblib.exists():
            self.skipTest("SK-13D07 PCBLIB not found")

        model = self.parser.get_model(sw_pcblib, "PCBComponent_1")
        self.assertIsNotNone(model)
        self.assertGreaterEqual(len(model.pads), 5)

        # Verify pads have shape == "ROUND"
        for pad in model.pads:
            self.assertEqual(pad.shape, "ROUND")
            # Width and height are different (e.g. 1.5mm x 2.0mm or 2.5mm x 3.5mm)
            self.assertNotEqual(pad.width, pad.height)
            # Verify profile generation creates a smooth oblong polygon
            prof = _get_pad_profile_2d(pad)
            self.assertGreaterEqual(len(prof), 16)

    def test_through_hole_annular_mesh(self):
        """Verify annular outer/inner profile generation and drill hole geometry for TH pads."""
        pad = Pad3D(
            x=0.0, y=0.0, width=1.5, height=3.0,
            shape="ROUND", is_thru_hole=True, hole_diameter=0.8
        )
        outer_poly = _get_pad_profile_2d(pad)
        r_hole = pad.hole_diameter / 2.0
        loc_out, loc_in = _get_annular_pad_profiles(pad, outer_poly, r_hole, num_circle_pts=24)

        # Same number of synchronized vertices
        self.assertEqual(len(loc_out), len(loc_in))
        self.assertGreaterEqual(len(loc_out), 24)

        # Check hole radius is exactly r_hole
        for x, y in loc_in:
            dist = math.sqrt(x * x + y * y)
            self.assertAlmostEqual(dist, r_hole, delta=1e-4)

        # Check outer points are strictly outside hole circle
        for (xo, yo), (xi, yi) in zip(loc_out, loc_in):
            d_out = math.sqrt(xo * xo + yo * yo)
            d_in = math.sqrt(xi * xi + yi * yi)
            self.assertGreater(d_out, d_in)

    def test_bottom_layers_and_viewer_bottom(self):
        """Verify layer 32 (Bottom Layer) and layer 34 (Bottom Overlay) sit at z = -1.002 mm, and view_bottom preset."""
        line_top = FootprintLine3D(x1=0, y1=0, x2=1, y2=1, layer_id=33, z=0.002)
        line_bot = FootprintLine3D(x1=0, y1=0, x2=1, y2=1, layer_id=32, z=-1.002, color=(0.18, 0.47, 0.82))
        arc_bot = FootprintArc3D(cx=0, cy=0, radius=1.0, angle_start=0, angle_end=360, layer_id=34, z=-1.002, color=(0.88, 0.85, 0.62))

        self.assertAlmostEqual(line_top.z, 0.002)
        self.assertAlmostEqual(line_bot.z, -1.002)
        self.assertAlmostEqual(arc_bot.z, -1.002)

        viewer = Footprint3DViewer()
        viewer.view_bottom()
        self.assertEqual(viewer.yaw, 0.0)
        self.assertEqual(viewer.pitch, -89.0)

    def test_through_hole_plated_tube_geometry(self):
        """Verify plated through-hole tube connects top face (0.0mm) to bottom face (-1.0mm)."""
        pad = Pad3D(
            x=0.0, y=0.0, width=2.0, height=2.0,
            shape="ROUND", is_thru_hole=True, hole_diameter=1.0
        )
        model = Footprint3DModel(name="TEST_TH", pads=[pad])
        viewer = Footprint3DViewer()
        viewer.model = model

        # Mock OpenGL VBO to capture extruded vertices
        captured_verts = []
        class MockVBO:
            def bind(self): pass
            def release(self): pass
            def allocate(self, data, size):
                import struct
                num_floats = len(data) // 4
                floats = struct.unpack(f"{num_floats}f", data)
                captured_verts.extend(floats)

        viewer._vbo = MockVBO()
        viewer._render_pads_gl(stride=24)

        self.assertGreater(len(captured_verts), 0)
        # Verify vertices have Z coordinates spanning 0.0, -0.1, -0.9, -1.0
        z_coords = [captured_verts[i] for i in range(2, len(captured_verts), 6)]
        min_z = min(z_coords)
        max_z = max(z_coords)
        self.assertAlmostEqual(min_z, -1.0, places=3)
        self.assertAlmostEqual(max_z, 0.0, places=3)
        # Verify presence of intermediate barrel wall at -0.1 and -0.9
        self.assertTrue(any(abs(z - (-0.1)) < 1e-3 for z in z_coords))
        self.assertTrue(any(abs(z - (-0.9)) < 1e-3 for z in z_coords))


if __name__ == "__main__":
    unittest.main()

