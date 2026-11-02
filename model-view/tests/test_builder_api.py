import base64
import unittest
from xml.etree import ElementTree as ET

from builder_api import apply_edits, build, catalog, defaults, inspect_source
from hrx_model import parse_hrx


class BuilderIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = defaults()
        cls.original = build({'mode': 'create', 'payload': cls.payload})
        cls.source = base64.b64encode(cls.original).decode('ascii')

    def test_generated_bridge_opens_in_viewer(self):
        model = parse_hrx(self.original, 'bridge.hrx')
        self.assertGreater(len(model['nodes']), 0)
        self.assertGreater(len(model['quads']), 0)

    def test_unedited_source_is_byte_identical(self):
        self.assertEqual(build({'mode': 'edit', 'source': self.source, 'changes': []}), self.original)

    def test_material_edit_preserves_other_model_data(self):
        materials = inspect_source(self.source)['materials']
        index = next(i for i, item in enumerate(materials) if 'Ehor' in item['attributes'])
        change = {'material': index, 'attribute': 'Ehor', 'value': '1234'}
        edited = build({'mode': 'edit', 'source': self.source, 'changes': [change]})
        before = ET.fromstring(self.original)
        after = ET.fromstring(edited)
        candidates = [e for e in after.findall('Template') if e.get('TypeOf', '').endswith('Material')]
        self.assertEqual(candidates[index].get('Ehor'), '1234')
        candidates[index].set('Ehor', materials[index]['attributes']['Ehor'])
        self.assertEqual(ET.tostring(before), ET.tostring(after))
        self.assertGreater(len(parse_hrx(edited, 'edited.hrx')['quads']), 0)

    def test_edits_cannot_modify_keys_or_target_unknown_materials(self):
        for change in ({'material': 0, 'attribute': 'Key', 'value': '999'},
                       {'material': 999, 'attribute': 'Ehor', 'value': '1'}):
            with self.assertRaises(ValueError):
                build({'mode': 'edit', 'source': self.source, 'changes': [change]})

    def test_analysis_and_nested_stage_settings_are_edited_losslessly(self):
        source = b"""<HiStrA><Template TypeOf="HiStrA.Objects.MasonryMaterial" Key="18" Name="M"><ShearEnergy Sigma="2" Energy="3"/></Template><Analysis Key="1" Name="Dynamic" AnalysisType="4" Method="Newmark"><StageDefinitions><StageDefinition Operation="Add" Factor="1"/></StageDefinitions><States><State Key="1" Exit="Complete"/></States></Analysis><LoadFunction key="2" DiscrVal="0.05"/><LoadFunctionItem key="3" loadFunctionKey="2" multiplier="1"/></HiStrA>"""
        encoded = base64.b64encode(source).decode('ascii')
        inspected = inspect_source(encoded)
        analysis = inspected['analyses'][0]
        stage = next(n for n in analysis['nodes'] if n['tag'] == 'StageDefinition')
        self.assertFalse(any(n['tag'] == 'State' for n in analysis['nodes']))
        energy = inspected['materials'][0]['nodes'][1]
        changes = [
            {'collection': 'analysis', 'index': 0, 'node': [], 'attribute': 'Method', 'value': 'Changed'},
            {'collection': 'analysis', 'index': 0, 'node': stage['path'], 'attribute': 'Factor', 'value': '0.5'},
            {'collection': 'material', 'index': 0, 'node': energy['path'], 'attribute': 'Energy', 'value': '4'},
            {'collection': 'load_function_item', 'index': 0, 'node': [], 'attribute': 'multiplier', 'value': '0.8'},
        ]
        result = ET.fromstring(build({'mode': 'edit', 'source': encoded, 'changes': changes}))
        self.assertEqual(result.find('Analysis').get('Method'), 'Changed')
        self.assertEqual(result.find('Analysis/StageDefinitions/StageDefinition').get('Factor'), '0.5')
        self.assertEqual(result.find('Template/ShearEnergy').get('Energy'), '4')
        self.assertEqual(result.find('LoadFunctionItem').get('multiplier'), '0.8')
        self.assertEqual(result.find('Analysis/States/State').get('Exit'), 'Complete')
        protected = {'collection': 'analysis', 'index': 0, 'node': [1, 0], 'attribute': 'Exit', 'value': 'Changed'}
        with self.assertRaises(ValueError):
            build({'mode': 'edit', 'source': encoded, 'changes': [protected]})

    def test_rejects_unsafe_mesh_size(self):
        payload = {**self.payload, 'nl': 0.001}
        with self.assertRaises(ValueError):
            build({'mode': 'create', 'payload': payload})

    def test_generated_model_has_the_native_analysis_and_load_schema(self):
        root = ET.fromstring(self.original)
        self.assertEqual(
            [analysis.get('Name') for analysis in root.findall('Analysis')],
            ['Vert', 'Modal_0', 'LiveLoad_1', 'scour_1', 'scour_2', 'LiveLoad_2',
             'scour_3', 'LiveLoad_3', 'scour_4', 'LiveLoad_0', 'Modal_-1',
             'Modal_1', 'LiveLoad_4'],
        )
        self.assertEqual(len(root.findall('LoadCondition')), 11)
        self.assertEqual(len(root.findall('LoadCombination')), 12)
        self.assertEqual(len(root.findall('LoadFunction')), 32)
        self.assertEqual(len(root.findall('LoadFunctionItem')), 64)
        self.assertEqual(
            root.find("Analysis[@Name='Vert']").get('AdapticConvergenceCriteria'),
            'ForceMoment',
        )
        self.assertEqual(
            root.find("Analysis[@Name='Modal_0']").get('AdapticConvergenceCriteria'),
            'Work',
        )

    def test_editor_exposes_every_native_masonry_attribute(self):
        materials = inspect_source(self.source)['materials']
        self.assertGreaterEqual(len(materials), 6)
        for material in materials:
            self.assertGreaterEqual(len(material['attributes']), 130)
            for attribute in ('Ehor', 'Ever', 'FmHor', 'FtmHor', 'Gt', 'Gc',
                              'ConstitutiveLawFlex', 'TensileCurveType',
                              'CompressiveCurveType', 'UnloadShear',
                              'SlidingYieldingDomainHor', 'scorrhor'):
                self.assertIn(attribute, material['attributes'])

    def test_catalog_lists_native_templates(self):
        data = catalog()
        self.assertEqual(
            [item['key'] for item in data['materials']],
            ['18', '19', '20', '21', '22', '141', '146', '147'],
        )
        self.assertEqual(data['analyses'][:4], ['Vert', 'Modal_0', 'LiveLoad_1', 'scour_1'])

    def test_add_duplicate_and_delete_analysis_round_trip(self):
        added = apply_edits({
            'mode': 'edit', 'source': self.source, 'changes': [],
            'operations': [{'op': 'add_analysis', 'template': 'Modal_0'}],
        })
        analyses = added['inspection']['analyses']
        self.assertEqual(len(analyses), 14)
        self.assertEqual(analyses[-1]['name'], 'Modal_0 (2)')
        edited = ET.fromstring(base64.b64decode(added['source']))
        last = edited.findall('Analysis')[-1]
        self.assertEqual(last.find('States/State').get('State'), 'NotExecutedNotToBeExecuted')
        self.assertEqual(last.get('MasterPoint'), edited.find('ModelPoint').get('Key'))

        duplicated = apply_edits({
            'mode': 'edit', 'source': added['source'], 'changes': [],
            'operations': [{'op': 'duplicate_analysis', 'duplicate': 0}],
        })
        self.assertEqual(duplicated['inspection']['analyses'][-1]['name'], 'Vert copy')

        removed = apply_edits({
            'mode': 'edit', 'source': duplicated['source'], 'changes': [],
            'operations': [{'op': 'delete_analysis', 'index': len(duplicated['inspection']['analyses']) - 1}],
        })
        self.assertEqual(len(removed['inspection']['analyses']), 14)

    def test_referenced_objects_cannot_be_deleted(self):
        with self.assertRaisesRegex(ValueError, 'referenced'):
            apply_edits({
                'mode': 'edit', 'source': self.source, 'changes': [],
                'operations': [{'op': 'delete_analysis', 'index': 0}],
            })
        materials = inspect_source(self.source)['materials']
        index = next(i for i, item in enumerate(materials) if item['key'] == '18')
        with self.assertRaisesRegex(ValueError, 'referenced'):
            apply_edits({
                'mode': 'edit', 'source': self.source, 'changes': [],
                'operations': [{'op': 'delete_material', 'index': index}],
            })

    def test_add_and_delete_unreferenced_material(self):
        added = apply_edits({
            'mode': 'edit', 'source': self.source, 'changes': [],
            'operations': [{'op': 'add_material', 'template': '18'}],
        })
        materials = added['inspection']['materials']
        self.assertEqual(materials[-1]['name'], 'Masonry (2)')
        removed = apply_edits({
            'mode': 'edit', 'source': added['source'], 'changes': [],
            'operations': [{'op': 'delete_material', 'index': len(materials) - 1}],
        })
        self.assertEqual(len(removed['inspection']['materials']), len(materials) - 1)

    def test_unknown_edit_operation_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_edits({
                'mode': 'edit', 'source': self.source, 'changes': [],
                'operations': [{'op': 'drop_database'}],
            })

    def test_create_mode_can_add_and_edit_materials_and_analyses(self):
        self.assertIn('inspection', self.payload)
        self.assertGreaterEqual(len(self.payload['inspection']['materials']), 6)
        self.assertEqual(len(self.payload['inspection']['analyses']), 13)

        step1 = apply_edits({
            'mode': 'create',
            'payload': self.payload,
            'steps': [],
            'changes': [{'collection': 'material', 'index': 0, 'node': [], 'attribute': 'Ehor', 'value': '2100'}],
            'operations': [
                {'op': 'add_material', 'template': '18'},
                {'op': 'add_analysis', 'template': 'Modal_0'},
            ],
        })
        self.assertEqual(len(step1['inspection']['analyses']), 14)
        self.assertEqual(step1['inspection']['analyses'][-1]['name'], 'Modal_0 (2)')
        new_mat_index = len(step1['inspection']['materials']) - 1
        self.assertEqual(step1['inspection']['materials'][new_mat_index]['name'], 'Masonry (2)')

        final_hrx = build({
            'mode': 'create',
            'payload': self.payload,
            'steps': [{
                'changes': [{'collection': 'material', 'index': 0, 'node': [], 'attribute': 'Ehor', 'value': '2100'}],
                'operations': [
                    {'op': 'add_material', 'template': '18'},
                    {'op': 'add_analysis', 'template': 'Modal_0'},
                ],
            }],
            'changes': [
                {'collection': 'material', 'index': new_mat_index, 'node': [], 'attribute': 'Ehor', 'value': '3333'},
                {'collection': 'analysis', 'index': 13, 'node': [], 'attribute': 'MaxIterations', 'value': '42'},
            ],
        })
        root = ET.fromstring(final_hrx)
        materials = [e for e in root.findall('Template') if e.get('TypeOf', '').endswith('Material')]
        analyses = root.findall('Analysis')
        self.assertEqual(materials[0].get('Ehor'), '2100')
        self.assertEqual(materials[-1].get('Name'), 'Masonry (2)')
        self.assertEqual(materials[-1].get('Ehor'), '3333')
        self.assertEqual(len(analyses), 14)
        self.assertEqual(analyses[-1].get('Name'), 'Modal_0 (2)')
        self.assertEqual(analyses[-1].get('MaxIterations'), '42')


if __name__ == '__main__':
    unittest.main()
