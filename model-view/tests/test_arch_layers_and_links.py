import base64
import unittest
import tempfile
from pathlib import Path
from lxml import etree
from builder_api import build, export, inspect_source, preview
from hrx_cli import apply_dotted_overrides
from histra_builder.ui import default_payload, build_spec
from histra_builder.generator.csharp_mesher import build_csharp_bridge_mesh

class ArchLayersAndLinksTests(unittest.TestCase):
    def test_arch_layers_preserve_material_and_multiply_quad_count(self):
        counts = []
        for layers in range(1, 5):
            payload = default_payload()
            payload['nl'] = 120
            for span in payload['spans']:
                span['arch_layers'] = layers
            mesh = build_csharp_bridge_mesh(build_spec(payload))
            arches = [q for q in mesh.quads.values() if q.group == 'CSharp_Arch']
            counts.append(len(arches))
            self.assertEqual({q.material_key for q in arches}, {18})
        self.assertEqual(counts, [counts[0] * n for n in range(1, 5)])

    def test_edit_preview_export_and_reopen(self):
        payload = default_payload()
        payload['nl'] = 120
        source = base64.b64encode(build({'mode': 'create', 'payload': payload})).decode()
        original = inspect_source(source)['collections']['wizard_span'][0]
        self.assertEqual(original['attributes']['HiStrAArchLayers'], '1')
        changes = [{'collection': 'wizard_span', 'index': 0, 'node': [], 'attribute': 'HiStrAArchLayers', 'value': '3'}]
        request = {'mode': 'edit', 'source': source, 'changes': changes, 'rebuild_geometry': True}
        live = etree.fromstring(preview(request))
        saved = etree.fromstring(export(request))
        self.assertEqual(len(live.findall('Quad')), len(saved.findall('Quad')))
        self.assertEqual(saved.find('./WizardData/Span').get('HiStrAArchLayers'), '3')
        reopened = base64.b64encode(etree.tostring(saved)).decode()
        again = etree.fromstring(export({'mode': 'edit', 'source': reopened, 'rebuild_geometry': True}))
        self.assertEqual(again.find('./WizardData/Span').get('HiStrAArchLayers'), '3')
        self.assertEqual(len(saved.findall('Quad')), len(again.findall('Quad')))

    def test_subdivided_arch_has_solver_interfaces(self):
        from histra.io.hr_loader import load_model
        from histra.preprocessing.prepare_model import prepare_model
        from histra_builder.generator.csharp_writer import serialize_csharp_mesh_to_hrx
        payload = default_payload()
        payload['nl'] = 120
        for span in payload['spans']:
            span['arch_layers'] = 4
        mesh = build_csharp_bridge_mesh(build_spec(payload))
        arches = {q.key for q in mesh.quads.values() if q.group == 'CSharp_Arch'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'arch.hrx'
            path.write_bytes(serialize_csharp_mesh_to_hrx(mesh))
            model = load_model(path)
            prepare_model(model, force=True, use_cache=False)
        pairs = [(i.parent_element_key1, i.parent_element_key2)
                 for i in model.collections.interfaces.values()
                 if i.parent_type_element1 == i.parent_type_element2 == 'Quad']
        connected = {key for a, b in pairs if a in arches and b in arches for key in (a, b)}
        self.assertEqual(connected, arches)
        self.assertTrue(any((a in arches) != (b in arches) for a, b in pairs))

    def test_invalid_layers_fail(self):
        for value in [0, 5, 1.5, True, 'bad']:
            payload = default_payload()
            payload['spans'][0]['arch_layers'] = value
            with self.assertRaises(ValueError):
                build_spec(payload)

    def test_cli_links_apply_only_changed_fields_and_mirror_abutments(self):
        payload = default_payload()
        payload['spans'][1]['f'] = 123
        result = apply_dotted_overrides(payload, ['spans.0.L=700', 'spans.0.arch_layers=3', 'left_abutment.b1=45', 'piers.0.H=200'], ['all'])
        self.assertEqual([s['L'] for s in result['spans']], [700, 700])
        self.assertEqual([s['arch_layers'] for s in result['spans']], [3, 3])
        self.assertEqual(result['spans'][1]['f'], 123)
        self.assertEqual(result['right_abutment']['b3'], 45)
        self.assertEqual(result['piers'][0]['H'], 200)
