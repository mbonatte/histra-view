"""Geometric checks for layered fill intersecting an arch extrados."""
from __future__ import annotations

import unittest
import base64
from collections import defaultdict
from pathlib import Path

from builder_api import _regenerated_geometry, build, export, needs_backfill_regeneration, preview
from histra_builder.generator.csharp_mesher import build_csharp_bridge_mesh
from hrx_model import parse_hrx
from histra_builder.ui import build_spec, default_payload


def _area(points):
    return abs(sum(a[0]*b[1] - b[0]*a[1] for a, b in zip(points, points[1:] + points[:1]))) / 2


def _intersection(subject, clip):
    """Clip convex X/Z polygons; used to detect fill overlapping the arch."""
    winding = sum(a[0]*b[1] - b[0]*a[1] for a, b in zip(clip, clip[1:] + clip[:1]))
    sign = 1 if winding > 0 else -1
    result = list(subject)
    for a, b in zip(clip, clip[1:] + clip[:1]):
        def side(p):
            return sign * ((b[0]-a[0])*(p[1]-a[1]) - (b[1]-a[1])*(p[0]-a[0]))
        if not result:
            break
        output = []
        for p, q in zip(result, result[1:] + result[:1]):
            sp, sq = side(p), side(q)
            if sp >= -1e-9:
                output.append(p)
            if (sp < -1e-9 and sq > 1e-9) or (sp > 1e-9 and sq < -1e-9):
                t = sp / (sp-sq)
                output.append((p[0] + t*(q[0]-p[0]), p[1] + t*(q[1]-p[1])))
        result = output
    return result


class BackfillMeshTests(unittest.TestCase):
    def _mesh(self, h1):
        payload = default_payload()
        payload['nl'] = 50
        payload['strips'] = [{'width':300, 'height':0, 'material_key':0}]
        payload['spans'] = payload['spans'][:1]
        payload['piers'] = []
        payload['elevation'].update(H1=h1, H2=200, H3=0, layer1_material_key=19, layer2_material_key=20)
        return build_csharp_bridge_mesh(build_spec(payload))

    def test_crossing_layer_is_clipped_to_arch_and_subdivided(self):
        mesh = self._mesh(50)
        fills = [q for q in mesh.quads.values() if q.group == 'CSharp_Fill']
        arches = [q for q in mesh.quads.values() if q.group == 'CSharp_Arch']
        self.assertTrue(fills and arches)
        self.assertEqual({q.material_key for q in fills}, {19, 20})
        for quad in fills:
            points = [mesh.nodes[key] for key in quad.node_keys]
            self.assertEqual(len(set(quad.node_keys)), 4)
            poly = [(p.x, p.z) for p in points]
            self.assertGreater(_area(poly), 1e-6)
            if quad.material_key == 19:
                self.assertLessEqual(max(p.z for p in points), 50.0001)
            else:
                self.assertGreaterEqual(min(p.z for p in points), 49.9999)
            for arch in arches:
                arch_points = [mesh.nodes[key] for key in arch.node_keys]
                if abs(arch_points[0].y - points[0].y) > 1e-6:
                    continue
                arch_poly = [(p.x, p.z) for p in arch_points]
                overlap = _intersection(poly, arch_poly)
                if len(overlap) >= 3:
                    self.assertLess(_area(overlap), 1e-3, 'fill overlaps the arch ring')
        upper = [q for q in fills if q.material_key == 20]
        heights = {round(mesh.nodes[k].z, 4) for q in upper for k in q.node_keys}
        self.assertGreater(len(heights), 2, 'upper layer needs intermediate vertical rows')

    def test_uncut_upper_layer_has_multiple_rows(self):
        mesh = self._mesh(150)
        upper = [q for q in mesh.quads.values() if q.group == 'CSharp_Fill' and q.material_key == 20]
        heights = {round(mesh.nodes[k].z, 4) for q in upper for k in q.node_keys}
        self.assertGreaterEqual(len(heights), 5)

    def test_strip_masonry_overrides_layers_until_removed(self):
        payload = default_payload()
        payload['nl'] = 50
        payload['strips'] = [{'width': 300, 'height': 0, 'material_key': 18}]
        payload['spans'] = payload['spans'][:1]
        payload['piers'] = []
        payload['elevation'].update(H1=150, H2=200, H3=0,
                                    layer1_material_key=19, layer2_material_key=20)
        def fill_materials():
            mesh = build_csharp_bridge_mesh(build_spec(payload))
            return {q.material_key for q in mesh.quads.values() if q.group == 'CSharp_Fill'}
        self.assertEqual(fill_materials(), {18})
        payload['strips'][0]['material_key'] = 0
        self.assertEqual(fill_materials(), {19, 20})
        payload['elevation']['layer2_material_key'] = 21
        self.assertEqual(fill_materials(), {19, 21})

    def test_layer_material_edit_preserves_both_wall_strips(self):
        payload = default_payload()
        payload['nl'] = 50
        payload['strips'] = [
            {'width': 50, 'height': 50, 'material_key': 18},
            {'width': 200, 'height': 0, 'material_key': 0},
            {'width': 50, 'height': 50, 'material_key': 18},
        ]
        payload['spans'] = payload['spans'][:1]
        payload['piers'] = []
        payload['elevation'].update(H1=150, H2=200, H3=0,
                                    layer1_material_key=19, layer2_material_key=20)
        def materials_by_strip():
            mesh = build_csharp_bridge_mesh(build_spec(payload))
            result = defaultdict(set)
            for quad in mesh.quads.values():
                if quad.group == 'CSharp_Fill':
                    result[round(mesh.nodes[quad.node_keys[0]].y)].add(quad.material_key)
            return result
        before = materials_by_strip()
        payload['elevation']['layer2_material_key'] = 21
        after = materials_by_strip()
        self.assertEqual(before[-125], {18})
        self.assertEqual(before[125], {18})
        self.assertEqual(after[-125], {18})
        self.assertEqual(after[125], {18})
        self.assertEqual(before[0], {19, 20})
        self.assertEqual(after[0], {19, 21})

    def test_variable_elevation_crossing_fails_closed(self):
        spec = build_spec(default_payload())
        spec.elevations.elevations[0].H1 = 50
        from copy import deepcopy
        second = deepcopy(spec.elevations.elevations[0])
        second.X = 1000
        spec.elevations.elevations.append(second)
        with self.assertRaisesRegex(NotImplementedError, 'variable elevations'):
            build_csharp_bridge_mesh(spec)

    def test_overhanging_arch_fill_fails_closed(self):
        payload = default_payload()
        payload['spans'] = [dict(payload['spans'][0], L=200, f=350, circolare=True)]
        payload['piers'] = []
        payload['elevation'].update(H1=100, H2=500)
        with self.assertRaisesRegex(NotImplementedError, 'overhanging arch'):
            build_csharp_bridge_mesh(build_spec(payload))

    def test_legacy_backfill_mesh_is_recognized_and_safely_regenerated(self):
        payload = default_payload()
        payload['elevation'].update(H1=50, H2=200, H3=0)
        current = build({'mode':'create', 'payload':payload})
        old = _regenerated_geometry(current, legacy_backfill=True)
        self.assertTrue(needs_backfill_regeneration(old))
        self.assertFalse(needs_backfill_regeneration(current))
        request = {'mode':'edit', 'source':base64.b64encode(old).decode('ascii'), 'rebuild_geometry':True}
        saved = export(request)
        self.assertEqual(parse_hrx(saved, 'saved.hrx')['nodes'], parse_hrx(current, 'current.hrx')['nodes'])
        self.assertFalse(needs_backfill_regeneration(saved))

    def test_previous_clipped_mesh_can_be_edited_and_regenerated(self):
        payload = default_payload()
        payload['elevation'].update(H1=50, H2=200, H3=0)
        current = build({'mode': 'create', 'payload': payload})
        previous = _regenerated_geometry(current, previous_backfill=True)
        self.assertTrue(needs_backfill_regeneration(previous))
        request = {'mode': 'edit', 'source': base64.b64encode(previous).decode('ascii'),
                   'rebuild_geometry': True}
        saved = export(request)
        self.assertEqual(parse_hrx(saved, 'saved.hrx')['nodes'], parse_hrx(current, 'current.hrx')['nodes'])


USER_MODEL = Path(__file__).resolve().parents[2] / 'check_backfill.hrx'
SCOZZESE_MODEL = Path(__file__).resolve().parents[2] / 'Scozzese_regenerated-edited.hrx'


@unittest.skipUnless(SCOZZESE_MODEL.exists(), 'local Scozzese edited model is not present')
class ScozzeseStratigraphyTests(unittest.TestCase):
    def test_stratigraphy_edits_preview_and_export_the_same_mesh(self):
        source = base64.b64encode(SCOZZESE_MODEL.read_bytes()).decode('ascii')
        changes = [
            {'collection': 'wizard_elevation', 'index': 0, 'node': [0, 0], 'attribute': 'H1', 'value': '113'},
            {'collection': 'wizard_elevation', 'index': 0, 'node': [0, 0], 'attribute': 'H2', 'value': '353'},
        ]
        request = {'mode': 'edit', 'source': source, 'changes': changes, 'rebuild_geometry': True}
        previewed = parse_hrx(preview(request), 'preview.hrx')
        saved = parse_hrx(export(request), 'saved.hrx')
        self.assertEqual(previewed['nodes'], saved['nodes'])
        self.assertEqual(previewed['quads'], saved['quads'])


@unittest.skipUnless(USER_MODEL.exists(), 'local check_backfill.hrx is not present')
class UserBackfillModelTests(unittest.TestCase):
    def test_saved_rounding_difference_does_not_block_regeneration(self):
        source = USER_MODEL.read_bytes()
        if not needs_backfill_regeneration(source):
            self.skipTest('local model no longer matches the earlier generated mesh')
        request = {'mode': 'edit', 'source': base64.b64encode(source).decode('ascii'),
                   'rebuild_geometry': True}
        saved = export(request)
        self.assertTrue(parse_hrx(saved, 'regenerated.hrx')['quads'])

    def test_clipped_fill_does_not_overlap_arch_and_has_upper_rows(self):
        from histra_builder.generator.csharp_import import spec_from_hrx
        mesh = build_csharp_bridge_mesh(spec_from_hrx(USER_MODEL))
        arches = defaultdict(list)
        for quad in mesh.quads.values():
            if quad.group == 'CSharp_Arch':
                points = [mesh.nodes[k] for k in quad.node_keys]
                arches[points[0].y].append(([(p.x, p.z) for p in points],
                                             min(p.x for p in points), max(p.x for p in points)))
        fill = [q for q in mesh.quads.values() if q.group == 'CSharp_Fill']
        self.assertTrue(fill and arches)
        upper_levels = set()
        for quad in fill:
            points = [mesh.nodes[k] for k in quad.node_keys]
            poly = [(p.x, p.z) for p in points]
            self.assertEqual(len(set(quad.node_keys)), 4)
            self.assertGreater(_area(poly), 1e-6)
            upper_levels.update(round(p.z, 3) for p in points if 113 < p.z < 466)
            for arch, xmin, xmax in arches[points[0].y]:
                if max(p.x for p in points) <= xmin or xmax <= min(p.x for p in points):
                    continue
                overlap = _intersection(poly, arch)
                if len(overlap) >= 3:
                    self.assertLess(_area(overlap), 0.01)
        self.assertGreater(len(upper_levels), 2)


if __name__ == '__main__':
    unittest.main()
