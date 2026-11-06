"""Rectangular pier shoulders: geometry, persistence and structural contacts."""
import base64
import tempfile
import unittest
from pathlib import Path
from lxml import etree

from builder_api import build, export, inspect_source, preview
from histra_builder.ui import build_spec, default_payload
from histra_builder.generator.csharp_mesher import build_csharp_bridge_mesh
from histra_builder.generator.csharp_writer import serialize_csharp_mesh_to_hrx


class PierShoulderTests(unittest.TestCase):
    def payload(self):
        payload = default_payload()
        payload['nl'] = 100
        payload['piers'][0].update(w2=500, shoulder_height=50)
        return payload

    def test_rectangles_use_pier_material_and_match_pier_extension(self):
        mesh = build_csharp_bridge_mesh(build_spec(self.payload()))
        shoulder = [q for q in mesh.quads.values() if q.group == 'CSharp_PierShoulder']
        self.assertTrue(shoulder)
        self.assertEqual({q.material_key for q in shoulder}, {mesh.spec.piers[0].material_key})
        y_bounds = [(mesh.nodes[q.node_keys[0]].y - q.thickness/2,
                     mesh.nodes[q.node_keys[0]].y + q.thickness/2) for q in shoulder]
        self.assertAlmostEqual(min(a for a, _ in y_bounds), -250)
        self.assertAlmostEqual(max(b for _, b in y_bounds), 250)
        self.assertTrue(all(a >= 150 or b <= -150 for a, b in y_bounds))
        self.assertEqual({mesh.nodes[k].z for q in shoulder for k in q.node_keys}, {0, 50})

    def test_editor_saves_and_reopens_shoulder_setting(self):
        payload = self.payload()
        payload['piers'][0]['shoulder_height'] = 0
        original = build({'mode': 'create', 'payload': payload})
        source = base64.b64encode(original).decode('ascii')
        record = inspect_source(source)['collections']['wizard_pier'][0]
        self.assertEqual(record['attributes']['HiStrAShoulderHeight'], '0')
        change = {'collection': 'wizard_pier', 'index': 0, 'node': [],
                  'attribute': 'HiStrAShoulderHeight', 'value': '50'}
        request = {'mode': 'edit', 'source': source, 'changes': [change], 'rebuild_geometry': True}
        live, saved = etree.fromstring(preview(request)), etree.fromstring(export(request))
        self.assertEqual(saved.find('./WizardData/Pier').get('HiStrAShoulderHeight'), '50')
        self.assertEqual(len(live.findall('Quad')), len(saved.findall('Quad')))
        reopened = base64.b64encode(etree.tostring(saved)).decode('ascii')
        again = export({'mode': 'edit', 'source': reopened, 'rebuild_geometry': True})
        self.assertEqual(etree.fromstring(again).find('./WizardData/Pier').get('HiStrAShoulderHeight'), '50')

    def test_shoulder_quads_connect_to_pier_and_other_masonry_on_preparation(self):
        from histra.io.hr_loader import load_model
        from histra.preprocessing.prepare_model import prepare_model
        mesh = build_csharp_bridge_mesh(build_spec(self.payload()))
        shoulders = {q.key for q in mesh.quads.values() if q.group == 'CSharp_PierShoulder'}
        piers = {q.key for q in mesh.quads.values() if q.group == 'CSharp_Pier'}
        others = set(mesh.quads) - shoulders - piers
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'shoulders.hrx'
            path.write_bytes(serialize_csharp_mesh_to_hrx(mesh))
            model = load_model(path)
            prepare_model(model, force=True, use_cache=False)
        pairs = [(i.parent_element_key1, i.parent_element_key2)
                 for i in model.collections.interfaces.values()
                 if i.parent_type_element1 == i.parent_type_element2 == 'Quad']
        connected_to_pier = {a if a in shoulders else b for a, b in pairs
                             if (a in shoulders and b in piers) or (b in shoulders and a in piers)}
        self.assertEqual(connected_to_pier, shoulders)
        self.assertTrue(any((a in shoulders and b in others) or (b in shoulders and a in others)
                            for a, b in pairs))

    def test_unsupported_skew_is_rejected(self):
        spec = build_spec(self.payload())
        spec.definition.inclination_angle = 10
        with self.assertRaisesRegex(NotImplementedError, 'straight, level'):
            build_csharp_bridge_mesh(spec)

    @unittest.skipUnless((Path(__file__).resolve().parents[2] / 'Scozzese_regenerated-edited.hrx').exists(),
                         'local Scozzese model is not present')
    def test_scozzese_both_shoulders_save_with_live_preview(self):
        from hrx_model import parse_hrx
        path = Path(__file__).resolve().parents[2] / 'Scozzese_regenerated-edited.hrx'
        raw = path.read_bytes()
        source = base64.b64encode(raw).decode('ascii')
        changes = [{'collection': 'wizard_pier', 'index': i, 'node': [],
                    'attribute': 'HiStrAShoulderHeight', 'value': '56.5'} for i in range(2)]
        request = {'mode': 'edit', 'source': source, 'changes': changes, 'rebuild_geometry': True}
        live = parse_hrx(preview(request), 'preview.hrx')
        result = export(request)
        saved = parse_hrx(result, 'saved.hrx')
        self.assertEqual(live['nodes'], saved['nodes'])
        self.assertEqual(live['quads'], saved['quads'])
        self.assertGreater(len(saved['quads']), len(parse_hrx(raw, 'original.hrx')['quads']))
        self.assertEqual([p.get('HiStrAShoulderHeight') for p in etree.fromstring(result).findall('./WizardData/Pier')],
                         ['56.5', '56.5'])


if __name__ == '__main__':
    unittest.main()
