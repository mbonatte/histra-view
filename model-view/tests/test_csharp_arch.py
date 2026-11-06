import math
import sys
import unittest
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from histra_builder.generator.csharp_arch import (
    arch_extrados_point,
    arch_intrados_point,
    circular_radius,
    circular_springing_angle,
    half_arch_params,
    half_arch_params_circular,
)
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
from histra_builder.generator.csharp_writer import serialize_csharp_mesh_to_hrx


ABUTMENT_WIDTH = 90.0


def make_spec(
    *,
    circolare: bool,
    length: float = 400.0,
    rise: float = 100.0,
    tb: float = 30.0,
    tt: float = 25.0,
    s1: float = 0.0,
    s2: float = 0.0,
    dz: float = 0.0,
    nl: float = 60.0,
) -> CSharpBridgeSpec:
    span = Span(
        L=length,
        W=300.0,
        f=rise,
        Tb=tb,
        Tt=tt,
        S1=s1,
        S2=s2,
        Dz=dz,
        Asx=36.8699,
        Adx=36.8699,
        circolare=circolare,
        true_circular_geometry=circolare,
    )
    left = Abutment(kind="Sinistra", b2=ABUTMENT_WIDTH, H=0.0, Hf=0.0, w2=300.0)
    right = Abutment(kind="Destra", b2=ABUTMENT_WIDTH, H=0.0, Hf=0.0, w2=300.0)
    definition = BridgeDefinition(
        width=300.0,
        width_top_pile=300.0,
        nl=nl,
        corsias=[Corsia(width=300.0)],
    )
    elevations = Elevations([Elevation(X=0.0, H1=175.0, H2=0.0, H3=0.0)])
    return CSharpBridgeSpec(
        definition=definition,
        elements=[left, span, right],
        elevations=elevations,
    )


def arch_nodes(mesh):
    keys = {
        key
        for quad in mesh.quads.values()
        if quad.group in ("CSharp_Arch", "CSharp_ArchReinforcement")
        for key in quad.node_keys
    }
    return [mesh.nodes[key] for key in keys]


def intrados_nodes(mesh):
    """Arch-ring nodes that are not shared with the spandrel or pulvino."""
    def keys_for(group):
        return {
            key
            for quad in mesh.quads.values()
            if quad.group == group
            for key in quad.node_keys
        }

    keys = keys_for("CSharp_Arch") - keys_for("CSharp_Fill") - keys_for("CSharp_Pulvino")
    return [mesh.nodes[key] for key in keys]


class TestCircularArchParams(unittest.TestCase):
    def test_radius_matches_the_circular_segment_formula(self):
        # A 12 m span with a 3 m rise is a 7.5 m radius segment.
        self.assertAlmostEqual(circular_radius(1200.0, 300.0), 750.0)
        self.assertAlmostEqual(
            circular_springing_angle(1200.0, 300.0),
            round(math.degrees(math.asin(0.6)), 6),
            places=9,
        )

    def test_article_circular_segment_reproduces_published_intrados(self):
        # Article geometry: 16 m span, R = 11.58 m.  The review reported the
        # circular intrados at 95.91 cm for the first arch cell (x = 114.286)
        # and 249.5 cm at quarter span; the elliptical branch gave 101.34 and
        # 277.8 at the same stations.
        length = 1600.0
        radius = 1158.0
        rise = radius - math.sqrt(radius**2 - (length / 2.0) ** 2)
        self.assertAlmostEqual(circular_radius(length, rise), radius, places=6)
        params = half_arch_params_circular(0.0, rise, length, 30.0, 25.0)
        for x, expected in ((114.286, 95.91), (length / 4.0, 249.5)):
            z = params.center[2] + math.sqrt(radius**2 - (x - length / 2.0) ** 2)
            self.assertAlmostEqual(z, expected, delta=0.05)

    def test_half_arch_params_are_exactly_circular(self):
        params = half_arch_params_circular(0.0, 300.0, 1200.0, 30.0, 25.0)
        self.assertTrue(params.circular)
        self.assertAlmostEqual(params.center[2], -450.0)
        self.assertAlmostEqual(params.rx, 750.0)
        self.assertAlmostEqual(params.rz, 750.0)
        self.assertAlmostEqual(math.degrees(params.theta0), 36.8698976, places=6)
        self.assertAlmostEqual(params.crown_point[2], 325.0)

        # Every point on the intrados is at exactly the circle radius.
        for theta in (params.theta0, 0.9, 1.2, math.pi / 2.0, math.pi - params.theta0):
            extrados = arch_extrados_point(params, theta)
            intrados = arch_intrados_point(params, extrados)
            radius = math.hypot(
                intrados[0] - params.center[0], intrados[2] - params.center[2]
            )
            self.assertAlmostEqual(radius, 750.0, places=9)

        # With a constant thickness both boundaries are concentric circles.
        constant = half_arch_params_circular(0.0, 300.0, 1200.0, 40.0, 40.0)
        for theta in (constant.theta0, 1.1, math.pi / 2.0, math.pi - constant.theta0):
            extrados = arch_extrados_point(constant, theta)
            radius = math.hypot(
                extrados[0] - constant.center[0], extrados[2] - constant.center[2]
            )
            self.assertAlmostEqual(radius, 790.0, places=9)

    def test_tall_segment_with_rise_beyond_half_span_is_supported(self):
        # The C# benchmark model contains L=200, f=350.  It is a shallow
        # circular segment whose centre lies above the springing; it is not a
        # semicircle and must not be rejected.
        radius = circular_radius(200.0, 350.0)
        self.assertAlmostEqual(radius, (350.0**2 + 100.0**2) / 700.0)
        self.assertEqual(circular_springing_angle(200.0, 350.0), 0.0)
        # C# WizardBridgeSpan.SetArcoCircolare: max(0, asin((R-f)/R)).
        self.assertAlmostEqual(
            circular_springing_angle(1010.0, 300.0), 28.57434, places=4
        )
        params = half_arch_params_circular(0.0, 350.0, 200.0, 100.0, 100.0)
        self.assertAlmostEqual(params.center[2], 350.0 - radius)
        self.assertLess(params.theta0, 0.0)
        springing = arch_intrados_point(
            params, arch_extrados_point(params, params.theta0)
        )
        self.assertAlmostEqual(springing[0], radius * math.cos(params.theta0))
        self.assertAlmostEqual(springing[2], 0.0, places=9)
        crown = arch_intrados_point(
            params, arch_extrados_point(params, math.pi / 2.0)
        )
        self.assertAlmostEqual(crown[2], 350.0, places=9)

    def test_elliptical_params_keep_the_thickness_law(self):
        params = half_arch_params(0.0, 100.0, 400.0, 30.0, 25.0, 0.0)
        self.assertFalse(params.circular)
        self.assertAlmostEqual(params.thick_base, 30.0)
        self.assertAlmostEqual(params.thick_key, 25.0)


class TestCircularArchMesh(unittest.TestCase):
    def test_intrados_nodes_lie_on_the_exact_circle(self):
        length, rise, tb, tt = 400.0, 100.0, 30.0, 25.0
        mesh = build_csharp_bridge_mesh(
            make_spec(circolare=True, length=length, rise=rise, tb=tb, tt=tt)
        )
        radius = circular_radius(length, rise)
        centre_x = ABUTMENT_WIDTH + length / 2.0
        centre_z = rise - radius

        intrados = intrados_nodes(mesh)
        self.assertGreaterEqual(len(intrados), 5)
        for point in intrados:
            radial = math.hypot(point.x - centre_x, point.z - centre_z)
            self.assertAlmostEqual(radial, radius, places=3)

        # Springings and crown are present at the exact analytic positions.
        all_arch = arch_nodes(mesh)
        self.assertTrue(
            any(abs(p.x - ABUTMENT_WIDTH) < 1e-6 and abs(p.z) < 1e-6 for p in all_arch)
        )
        self.assertTrue(
            any(
                abs(p.x - (ABUTMENT_WIDTH + length)) < 1e-6 and abs(p.z) < 1e-6
                for p in all_arch
            )
        )
        self.assertTrue(
            any(abs(p.x - centre_x) < 1e-6 and abs(p.z - rise) < 1e-6 for p in all_arch)
        )

        # A node near quarter span follows the circle, not the ellipse.
        quarter_x = centre_x - length / 4.0
        nearest = min(intrados, key=lambda p: abs(p.x - quarter_x))
        expected = centre_z + math.sqrt(radius**2 - (nearest.x - centre_x) ** 2)
        self.assertAlmostEqual(nearest.z, expected, places=4)
        # The untouched elliptical intrados with Asx = 0 is f*sqrt(3)/2 there.
        self.assertLess(nearest.z, rise * math.sqrt(3.0) / 2.0)

    def test_extrados_is_radial_offset_between_springer_and_crown_thickness(self):
        length, rise, tb, tt = 400.0, 100.0, 30.0, 25.0
        mesh = build_csharp_bridge_mesh(
            make_spec(circolare=True, length=length, rise=rise, tb=tb, tt=tt)
        )
        radius = circular_radius(length, rise)
        centre_x = ABUTMENT_WIDTH + length / 2.0
        centre_z = rise - radius

        radial_gaps = []
        for point in arch_nodes(mesh):
            radial = math.hypot(point.x - centre_x, point.z - centre_z)
            if radial > radius + 1.0e-3:
                radial_gaps.append(radial - radius)
        self.assertTrue(radial_gaps)
        self.assertGreaterEqual(min(radial_gaps), tt - 1.0e-3)
        self.assertLessEqual(max(radial_gaps), tb + 1.0e-3)
        self.assertAlmostEqual(max(radial_gaps), tb, places=3)
        # Crown extrados is still at f + Tt.
        self.assertTrue(
            any(
                abs(p.x - centre_x) < 1e-6 and abs(p.z - (rise + tt)) < 1e-6
                for p in arch_nodes(mesh)
            )
        )

    def test_elliptical_mesh_intrados_is_not_the_circle(self):
        length, rise = 400.0, 100.0
        spec = make_spec(circolare=False, length=length, rise=rise)
        # Asx = 0 removes the circular-angle trim: the intrados is the full
        # semi-ellipse, so it must not be mistaken for the circular branch.
        spec.spans[0].Asx = 0.0
        spec.spans[0].Adx = 0.0
        mesh = build_csharp_bridge_mesh(spec)
        radius = circular_radius(length, rise)
        centre_x = ABUTMENT_WIDTH + length / 2.0
        centre_z = rise - radius
        errors = [
            abs(math.hypot(p.x - centre_x, p.z - centre_z) - radius)
            for p in intrados_nodes(mesh)
        ]
        self.assertTrue(errors)
        self.assertTrue(max(errors) > 0.5)

    def test_setbacks_shift_the_crown_and_widen_the_span(self):
        length, rise, s1, s2 = 400.0, 100.0, 20.0, 60.0
        mesh = build_csharp_bridge_mesh(
            make_spec(circolare=True, length=length, rise=rise, s1=s1, s2=s2)
        )
        effective = length + s1 + s2
        centre_x = ABUTMENT_WIDTH + length / 2.0 + (s2 - s1) / 2.0
        springing_z = 0.0

        nodes = arch_nodes(mesh)
        self.assertTrue(
            any(abs(p.x - (centre_x - effective / 2.0)) < 1e-4 and abs(p.z - springing_z) < 1e-6
                for p in nodes)
        )
        self.assertTrue(
            any(abs(p.x - (centre_x + effective / 2.0)) < 1e-4 and abs(p.z - springing_z) < 1e-6
                for p in nodes)
        )
        self.assertTrue(
            any(abs(p.x - centre_x) < 1e-4 and abs(p.z - rise) < 1e-6 for p in nodes)
        )

    def test_dz_drops_the_intrados_and_keeps_the_extrados_crown(self):
        length, rise, tt, dz = 400.0, 100.0, 25.0, 20.0
        mesh = build_csharp_bridge_mesh(
            make_spec(circolare=True, length=length, rise=rise, dz=dz)
        )
        centre_x = ABUTMENT_WIDTH + length / 2.0
        nodes = arch_nodes(mesh)
        self.assertTrue(
            any(abs(p.x - centre_x) < 1e-4 and abs(p.z - (rise - dz)) < 1e-4
                for p in nodes)
        )
        self.assertTrue(
            any(abs(p.x - centre_x) < 1e-4 and abs(p.z - (rise + tt)) < 1e-4
                for p in nodes)
        )
        # The first arch-ring node still snaps to the support level (C# parity).
        self.assertTrue(
            any(abs(p.x - ABUTMENT_WIDTH) < 1e-4 and abs(p.z) < 1e-6 for p in nodes)
        )


class TestCircularArchSerialization(unittest.TestCase):
    def test_hrx_round_trip_keeps_circolare_and_derived_angle(self):
        mesh = build_csharp_bridge_mesh(make_spec(circolare=True, length=400.0, rise=100.0))
        root = etree.fromstring(serialize_csharp_mesh_to_hrx(mesh))
        span = root.find("WizardData/Span")
        self.assertIsNotNone(span)
        self.assertEqual(span.get("Circolare"), "true")
        expected = circular_springing_angle(400.0, 100.0)
        self.assertAlmostEqual(float(span.get("Asx")), expected, places=6)
        self.assertAlmostEqual(float(span.get("Adx")), expected, places=6)

        # The native flag survives, but does not encode the viewer extension.
        from histra_builder.generator.csharp_import import spec_from_wizard_data

        imported = spec_from_wizard_data(root.find("WizardData"))
        self.assertTrue(imported.spans[0].circolare)
        self.assertFalse(imported.spans[0].true_circular_geometry)

    def test_hrx_elliptical_span_keeps_user_springing_angle(self):
        mesh = build_csharp_bridge_mesh(make_spec(circolare=False))
        root = etree.fromstring(serialize_csharp_mesh_to_hrx(mesh))
        span = root.find("WizardData/Span")
        self.assertEqual(span.get("Circolare"), "false")
        self.assertAlmostEqual(float(span.get("Asx")), 36.8699, places=4)

    def test_ui_payload_parses_the_shape_flag(self):
        from histra_builder.ui import UiPayloadError, build_spec, default_payload

        payload = default_payload()
        payload["spans"][0]["circolare"] = "true"
        payload["spans"][1]["circolare"] = False
        spec = build_spec(payload)
        self.assertTrue(spec.spans[0].circolare)
        self.assertFalse(spec.spans[1].circolare)

        payload["spans"][0]["circolare"] = "maybe"
        with self.assertRaises(UiPayloadError):
            build_spec(payload)


if __name__ == "__main__":
    unittest.main()
