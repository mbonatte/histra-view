"""Regression checks against the native C# model_mesh_complete benchmark.

The model is intentionally not a regular bridge: four spans mix circular and
elliptical arches, one span has a rise greater than half its span, the deck is
skewed 10 degrees, the pier caps are wider than the deck, and the model uses
the full native material/analysis portfolio.  The file is kept outside Git
(the ``C#_Software_View`` folder is a local reference), so these tests skip
when it is absent.
"""
from __future__ import annotations

import math
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from histra_builder.generator.csharp_arch import (
    arch_extrados_point,
    arch_intrados_point,
    circular_radius,
    half_arch_params_circular,
)
from histra_builder.generator.csharp_import import spec_from_hrx
from histra_builder.generator.csharp_mesher import build_csharp_bridge_mesh
from histra_builder.generator.csharp_model import (
    Abutment,
    BridgeDefinition,
    CSharpBridgeSpec,
    Corsia,
    Elevation,
    Elevations,
    Span,
)


BENCHMARK = (
    Path(__file__).resolve().parents[2]
    / "C#_Software_View"
    / "model_mesh_complete"
    / "model_mesh_complete.hrx"
)


def _span_spec(length: float, rise: float, circolare: bool) -> CSharpBridgeSpec:
    span = Span(
        L=length,
        W=300.0,
        f=rise,
        Tb=100.0,
        Tt=100.0,
        Asx=0.0,
        Adx=0.0,
        circolare=circolare,
        true_circular_geometry=circolare,
    )
    left = Abutment(kind="Sinistra", b2=90.0, H=0.0, Hf=0.0, w2=300.0)
    right = Abutment(kind="Destra", b2=90.0, H=0.0, Hf=0.0, w2=300.0)
    return CSharpBridgeSpec(
        definition=BridgeDefinition(
            width=300.0,
            width_top_pile=300.0,
            nl=100.0,
            corsias=[Corsia(width=300.0)],
        ),
        elements=[left, span, right],
        elevations=Elevations([Elevation(X=0.0, H1=175.0, H2=0.0, H3=0.0)],
                              layer1_generate=rise <= length / 2,
                              layer2_generate=rise <= length / 2,
                              layer3_generate=rise <= length / 2),
    )


@unittest.skipUnless(BENCHMARK.exists(), "local C# benchmark model is not present")
class BenchmarkModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(BENCHMARK).getroot()

    def test_skewed_widened_support_geometry_against_csharp(self):
        # Earth-pressure restraints are outside this geometry comparison.
        # Only the imported in-memory specification is changed.
        from scipy.spatial import cKDTree
        from collections import Counter, defaultdict
        from histra_builder.generator.csharp_model import Pier
        spec = spec_from_hrx(BENCHMARK)
        for support in spec.elements:
            if isinstance(support, (Abutment, Pier)):
                support.spinta_passiva_sx = support.spinta_passiva_dx = False
        mesh = build_csharp_bridge_mesh(spec)
        nodes = {node.get('Key'): tuple(map(float, node.get('Point').split(';')))
                 for node in self.root.findall('Node')}
        quads = self.root.findall('Quad')
        points = [nodes[quad.get(f'NodeKey{i}')] for quad in quads for i in range(1, 5)]
        tree = cKDTree(points)
        def canonical(point, tolerance):
            matches = tree.query_ball_point(point, tolerance)
            if not matches:
                return None
            nearest = min(matches, key=lambda j: sum((points[j][i]-point[i])**2 for i in range(3)))
            return min(tree.query_ball_point(points[nearest], 0.0001))
        reference = defaultdict(list)
        for q in quads:
            by_node = {canonical(nodes[q.get(f'NodeKey{i}')], 0.0001): float(q.get(f'Thickness{i}'))
                       for i in range(1, 5)}
            reference[(tuple(sorted(by_node)), q.get('MaterialKey'))].append(by_node)
        matched = Counter()
        for quad in mesh.quads.values():
            if quad.group not in ('CSharp_Pier', 'CSharp_Foundation', 'CSharp_Fill'):
                continue
            ids = []
            for key in quad.node_keys:
                p = mesh.nodes[key]
                ids.append(canonical((p.x, p.y, p.z), 0.05))
            if any(key is None for key in ids):
                continue
            signature = (tuple(sorted(ids)), str(quad.material_key))
            if reference[signature]:
                thickness = reference[signature].pop()
                for index, key in enumerate(ids):
                    self.assertAlmostEqual(quad.kinematics.thicknesses[index], thickness[key], delta=0.05)
                matched[quad.group] += 1
        # All native support quads for this benchmark are accounted for.
        native_materials = Counter(q.get('MaterialKey') for q in quads)
        self.assertEqual(matched['CSharp_Pier'], native_materials['17'])
        self.assertEqual(matched['CSharp_Foundation'], native_materials['1'])
        # Backfill comparison remains partial: the native model has Vertices.
        self.assertGreaterEqual(matched['CSharp_Fill'], 1218)

    def test_model_inventory_matches_the_csharp_export(self):
        self.assertEqual(self.root.tag, "HiStrA")
        self.assertEqual(self.root.get("WizardType"), "RailBridge")
        self.assertEqual(self.root.get("version"), "2026.1.1")
        self.assertEqual(len(self.root.findall("Node")), 3235)
        self.assertEqual(len(self.root.findall("Quad")), 2529)
        self.assertEqual(len(self.root.findall("Vertex")), 20)
        self.assertEqual(len(self.root.findall("Restraint")), 315)
        self.assertEqual(len(self.root.findall("GeometryLineRestraint")), 160)
        self.assertEqual(len(self.root.findall("Analysis")), 21)

        masonry = [
            template for template in self.root.findall("Template")
            if template.get("PurposeType") == "MasonryMaterial"
        ]
        self.assertEqual(len(masonry), 8)
        self.assertEqual(
            [template.get("Name") for template in masonry],
            ["Foundations", "Piers", "Arches", "Backfill", "Fill", "Ballast", "Pier cap", "Concrete Vault"],
        )

    def test_wizard_has_the_four_mixed_spans_and_five_lanes(self):
        wizard = self.root.find("WizardData")
        self.assertIsNotNone(wizard)
        spans = wizard.findall("Span")
        self.assertEqual(
            [(float(span.get("L")), float(span.get("f")), span.get("Circolare")) for span in spans],
            [
                (1000.0, 300.0, "true"),
                (800.0, 200.0, "false"),
                (200.0, 350.0, "true"),
                (600.0, 50.0, "false"),
            ],
        )
        self.assertEqual(len(wizard.findall("Pier")), 3)
        self.assertEqual(len(wizard.findall("Abutment")), 2)
        self.assertEqual(len(wizard.find("BridgeDefinition").findall("Corsie/Corsia")), 5)
        self.assertEqual(wizard.find("BridgeDefinition").get("InclinationAngle"), "10")
        self.assertEqual(wizard.find("BridgeDefinition").get("WidthTopPile"), "600")

    def test_importer_reads_the_native_spans_and_flags(self):
        spec = spec_from_hrx(BENCHMARK)
        spans = [element for element in spec.elements if isinstance(element, Span)]
        self.assertEqual([span.L for span in spans], [1000.0, 800.0, 200.0, 600.0])
        self.assertEqual([span.f for span in spans], [300.0, 200.0, 350.0, 50.0])
        self.assertEqual([span.circolare for span in spans], [True, False, True, False])
        self.assertTrue(all(not span.true_circular_geometry for span in spans))
        self.assertEqual(spec.definition.width, 530.0)
        self.assertEqual(spec.definition.width_top_pile, 600.0)
        self.assertEqual(spec.definition.inclination_angle, 10.0)
        self.assertEqual(spec.definition.slope, 0.02)
        self.assertEqual([corsia.width for corsia in spec.definition.corsias], [40.0, 150.0, 150.0, 150.0, 40.0])

    def test_tall_circular_span_is_accepted_and_passes_through_its_three_points(self):
        length, rise = 200.0, 350.0
        radius = circular_radius(length, rise)
        params = half_arch_params_circular(0.0, rise, length, 100.0, 100.0)
        self.assertAlmostEqual(params.center[2], rise - radius)
        self.assertLess(params.theta0, 0.0)
        for theta, expected in (
            (params.theta0, (length / 2.0, 0.0)),
            (math.pi / 2.0, (0.0, rise)),
        ):
            intrados = arch_intrados_point(params, arch_extrados_point(params, theta))
            self.assertAlmostEqual(intrados[0], expected[0], places=6)
            self.assertAlmostEqual(intrados[2], expected[1], places=6)

        mesh = build_csharp_bridge_mesh(_span_spec(length, rise, circolare=True))
        self.assertGreater(len(mesh.nodes), 0)
        self.assertGreater(len(mesh.quads), 0)
        arch_nodes = {
            key
            for quad in mesh.quads.values()
            if quad.group == "CSharp_Arch"
            for key in quad.node_keys
        }
        centre_x = 90.0 + length / 2.0
        centre_z = rise - radius
        intrados = [
            mesh.nodes[key] for key in arch_nodes
            if math.hypot(mesh.nodes[key].x - centre_x, mesh.nodes[key].z - centre_z)
            <= radius + 1.0e-6
        ]
        self.assertGreaterEqual(len(intrados), 5)
        for point in intrados:
            self.assertAlmostEqual(
                math.hypot(point.x - centre_x, point.z - centre_z), radius, places=4
            )
        self.assertTrue(any(abs(point.x - 90.0) < 1e-6 and abs(point.z) < 1e-6 for point in intrados))
        self.assertTrue(any(abs(point.x - 290.0) < 1e-6 and abs(point.z) < 1e-6 for point in intrados))
        self.assertTrue(any(abs(point.x - centre_x) < 1e-6 and abs(point.z - rise) < 1e-6 for point in intrados))

    def test_short_circular_span_also_meshes(self):
        mesh = build_csharp_bridge_mesh(_span_spec(1000.0, 300.0, circolare=True))
        self.assertGreater(len(mesh.nodes), 0)
        self.assertGreater(len(mesh.quads), 0)

    def test_native_circular_flag_does_not_select_viewer_extension(self):
        native = _span_spec(1000.0, 300.0, circolare=False)
        native.elements[1].circolare = True
        elliptical = _span_spec(1000.0, 300.0, circolare=False)
        actual = build_csharp_bridge_mesh(native)
        expected = build_csharp_bridge_mesh(elliptical)
        self.assertEqual(actual.nodes, expected.nodes)
        self.assertEqual(actual.quads, expected.quads)

class SupportWidthTests(unittest.TestCase):
    def test_wider_centered_pier_and_foundation_extend_beyond_arch(self):
        from histra_builder.ui import build_spec, default_payload
        payload = default_payload()
        payload['piers'][0].update(w2=400, W1f=0, W3f=0, material_key=77, material_foundation_key=78)
        mesh = build_csharp_bridge_mesh(build_spec(payload))
        for group, material in [('CSharp_Pier', 77), ('CSharp_Foundation', 78)]:
            quads = [quad for quad in mesh.quads.values() if quad.group == group and quad.material_key == material]
            self.assertTrue(quads)
            limits = [(mesh.nodes[q.node_keys[0]].y - q.thickness / 2,
                       mesh.nodes[q.node_keys[0]].y + q.thickness / 2) for q in quads]
            self.assertAlmostEqual(min(low for low, _ in limits), -200)
            self.assertAlmostEqual(max(high for _, high in limits), 200)

    def test_wider_pier_subdivides_extensions_and_matches_foundation(self):
        from histra_builder.ui import build_spec, default_payload
        payload = default_payload()
        payload['piers'][0].update(w2=600, W1f=0, W3f=0, material_key=77, material_foundation_key=78)
        mesh = build_csharp_bridge_mesh(build_spec(payload))
        strips = []
        for group, material in [('CSharp_Pier', 77), ('CSharp_Foundation', 78)]:
            sections = {(mesh.nodes[q.node_keys[0]].y, q.thickness)
                        for q in mesh.quads.values() if q.group == group and q.material_key == material}
            strips.append(sections)
            extension = sorted((y, width) for y, width in sections if abs(y) > 150)
            self.assertEqual([y for y, _ in extension], [-275, -225, -175, 175, 225, 275])
            self.assertTrue(all(width == 50 for _, width in extension))
        self.assertEqual(strips[0], strips[1])


if __name__ == "__main__":
    unittest.main()
