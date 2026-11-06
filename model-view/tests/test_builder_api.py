import base64
import unittest
from xml.etree import ElementTree as ET

from builder_api import add_abutment_end_restraints, apply_edits, build, catalog, defaults, export, inspect_source, preview, _document, _geometry_matches
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

    def test_quad_roundoff_is_allowed_but_mesh_edits_are_not(self):
        original = _document(self.original)
        candidate = _document(self.original)
        quad = candidate.find('Quad')
        quad.set('Length1', str(float(quad.get('Length1')) + 0.00009))
        centroid = [float(value) for value in quad.get('G').split(';')]
        centroid[0] += 0.00015
        quad.set('G', ';'.join(map(str, centroid)))
        ref = quad.find('ReferenceSystem')
        origin = [float(value) for value in ref.get('Origin').split(';')]
        origin[0] += 0.00009
        ref.set('Origin', ';'.join(map(str, origin)))
        self.assertTrue(_geometry_matches(original, candidate, 'Quad'))
        quad.set('MaterialKey', '999')
        self.assertFalse(_geometry_matches(original, candidate, 'Quad'))
        quad.set('MaterialKey', original.find('Quad').get('MaterialKey'))
        quad.set('Length1', str(float(original.find('Quad').get('Length1')) + 0.001))
        self.assertFalse(_geometry_matches(original, candidate, 'Quad'))

    def test_fixed_abutment_end_restraints_round_trip(self):
        result = add_abutment_end_restraints({'mode': 'edit', 'source': self.source, 'changes': []})
        edited = base64.b64decode(result['source'])
        before, after = ET.fromstring(self.original), ET.fromstring(edited)
        glrs = [e for e in after.findall('GeometryLineRestraint') if e.get('Name', '').startswith('HiStrAView_EndSupport_')]
        self.assertTrue(any('Sinistra' in e.get('Name') for e in glrs))
        self.assertTrue(any('Destra' in e.get('Name') for e in glrs))
        nodes = {e.get('Key'): [float(v) for v in e.get('Point').split(';')] for e in after.findall('Node')}
        length = float(after.find('Bridge').get('L'))
        deck_height = float(after.find('Bridge').get('H'))
        for side in ('Sinistra', 'Destra'):
            side_glrs = [e for e in glrs if f'EndSupport_{side}_' in e.get('Name')]
            self.assertGreaterEqual(max(nodes[e.get(key)][2] for e in side_glrs for key in ('NodeKey1', 'NodeKey2')), deck_height)
            self.assertTrue(any(nodes[e.get(key)][2] > 0 for e in side_glrs for key in ('NodeKey1', 'NodeKey2')))
        for glr in glrs:
            x = 0.0 if 'Sinistra' in glr.get('Name') else length
            self.assertAlmostEqual(nodes[glr.get('NodeKey1')][0], x)
            self.assertAlmostEqual(nodes[glr.get('NodeKey2')][0], x)
            self.assertNotEqual(nodes[glr.get('NodeKey1')][2], nodes[glr.get('NodeKey2')][2])
            self.assertEqual(glr.get('K'), '-1|-1|-1|-1|-1|-1')
            key = glr.find('RestraintKeys/RestraintKey').get('Value')
            restraint = after.find(f"Restraint[@Key='{key}']")
            self.assertTrue(all(restraint.get(k) == '-1' for k in ('K1','K2','K3','Kr1','Kr2','Kr3')))
        self.assertEqual(ET.tostring(before.find('Quad')), ET.tostring(after.find('Quad')))
        self.assertEqual(ET.tostring(before.find('Analysis')), ET.tostring(after.find('Analysis')))
        self.assertEqual(export({'mode':'edit', 'source':result['source']}), edited)
        regenerated = export({'mode':'edit', 'source':result['source'], 'rebuild_geometry':True, 'replace_existing_mesh':True})
        regenerated_root = ET.fromstring(regenerated)
        self.assertEqual(len([e for e in regenerated_root.findall('GeometryLineRestraint') if e.get('Name', '').startswith('HiStrAView_EndSupport_')]), len(glrs))
        with self.assertRaisesRegex(ValueError, 'already been added'):
            add_abutment_end_restraints({'mode':'edit', 'source':result['source']})

    def test_geometry_change_regenerates_abutment_end_restraints(self):
        result = add_abutment_end_restraints({'mode':'edit', 'source':self.source})
        changes = [{'collection':'wizard_abutment', 'index':0, 'node':[], 'attribute':'H', 'value':'150'}]
        request = {'mode':'edit', 'source':result['source'], 'changes':changes, 'rebuild_geometry':True}
        generated = preview(request)
        saved = export(request)
        self.assertEqual(parse_hrx(generated, 'preview.hrx')['nodes'], parse_hrx(saved, 'saved.hrx')['nodes'])
        root = ET.fromstring(saved)
        nodes = {n.get('Key'): [float(v) for v in n.get('Point').split(';')] for n in root.findall('Node')}
        supports = [e for e in root.findall('GeometryLineRestraint') if 'HiStrAView_EndSupport_Sinistra_' in e.get('Name', '')]
        self.assertTrue(supports)
        self.assertAlmostEqual(min(nodes[e.get(key)][2] for e in supports for key in ('NodeKey1', 'NodeKey2')), -150)
        self.assertTrue(all(e.get('K') == '-1|-1|-1|-1|-1|-1' for e in supports))

    def test_end_restraints_reject_pending_geometry(self):
        change = {'collection':'wizard_pier', 'index':0, 'node':[], 'attribute':'H', 'value':'500'}
        with self.assertRaisesRegex(ValueError, 'Regenerate and reopen'):
            add_abutment_end_restraints({'mode':'edit', 'source':self.source, 'changes':[change]})

    def test_elevation_section_edit_preserves_mesh(self):
        inspected = inspect_source(self.source)
        elevation = inspected['collections']['wizard_elevation'][0]
        section = next(n for n in elevation['nodes'] if n['tag'] == 'Elevation')
        change = {'collection': 'wizard_elevation', 'index': 0, 'node': section['path'], 'attribute': 'H1', 'value': '234'}
        before = ET.fromstring(self.original)
        after = ET.fromstring(build({'mode': 'edit', 'source': self.source, 'changes': [change]}))
        self.assertEqual(after.find('.//WizardData/Elevations/Elevations/Elevation').get('H1'), '234')
        self.assertEqual(ET.tostring(before.find('Quad')), ET.tostring(after.find('Quad')))
        generated = preview({'mode': 'edit', 'source': self.source, 'changes': [change], 'rebuild_geometry': True})
        preview_model = parse_hrx(generated, 'preview.hrx')
        original_model = parse_hrx(self.original, 'original.hrx')
        self.assertNotEqual(preview_model['nodes'], original_model['nodes'])

    def test_pier_height_changes_regenerated_preview(self):
        changes = [{'collection': 'wizard_pier', 'index': 0, 'node': [], 'attribute': 'H', 'value': '500'}]
        generated = preview({'mode': 'edit', 'source': self.source, 'changes': changes, 'rebuild_geometry': True})
        self.assertNotEqual(parse_hrx(generated, 'preview.hrx')['nodes'],
                            parse_hrx(self.original, 'original.hrx')['nodes'])
        saved = export({'mode': 'edit', 'source': self.source, 'changes': changes})
        self.assertEqual(parse_hrx(saved, 'saved.hrx')['nodes'], parse_hrx(generated, 'preview.hrx')['nodes'])
        before, after = ET.fromstring(self.original), ET.fromstring(saved)
        self.assertEqual(ET.tostring(before.find('Template')), ET.tostring(after.find('Template')))
        self.assertEqual(ET.tostring(before.find('Analysis')), ET.tostring(after.find('Analysis')))

    def test_export_regenerates_geometry_after_an_intermediate_edit_operation(self):
        change = {'collection':'wizard_pier', 'index':0, 'node':[], 'attribute':'H', 'value':'500'}
        request = {'mode':'edit', 'source':self.source,
                   'steps':[{'changes':[change], 'operations':[{'op':'duplicate_material', 'duplicate':0}]}]}
        saved = export(request)
        root = ET.fromstring(saved)
        self.assertEqual(root.find('./WizardData/Pier').get('H'), '500')
        self.assertNotEqual(parse_hrx(saved, 'saved.hrx')['nodes'], parse_hrx(self.original, 'original.hrx')['nodes'])
        self.assertEqual(len(root.findall('Template')), len(ET.fromstring(self.original).findall('Template')) + 1)

    def test_open_endpoint_projects_model_before_replacing_active_source(self):
        import io
        import json
        from unittest.mock import patch
        from server import ACTIVE_MODEL, Handler
        def call(source):
            body = json.dumps({'source':source, 'name':'opened.hrx'}).encode()
            handler = Handler.__new__(Handler)
            handler.path = '/api/builder/open'
            handler.headers = {'Content-Length':str(len(body))}
            handler.rfile = io.BytesIO(body)
            handler.reply = lambda code, payload, *args: (code, payload)
            return handler.do_POST()
        with patch.dict(ACTIVE_MODEL, {'bytes':None, 'name':'old.hrx'}, clear=True):
            code, result = call(self.source)
            self.assertEqual(code, 200)
            self.assertEqual(result['model']['name'], 'opened.hrx')
            self.assertEqual(len(result['model']['quads']), len(parse_hrx(self.original, 'original.hrx')['quads']))
            self.assertEqual(ACTIVE_MODEL['bytes'], self.original)
            code, _ = call('bad')
            self.assertEqual(code, 400)
            self.assertEqual(ACTIVE_MODEL['bytes'], self.original)

    def test_regeneration_rejects_unrecognized_model_objects(self):
        source = ET.fromstring(self.original)
        ET.SubElement(source, 'CustomElement', Key='1')
        encoded = base64.b64encode(ET.tostring(source)).decode('ascii')
        with self.assertRaisesRegex(ValueError, 'unsupported objects CustomElement'):
            export({'mode': 'edit', 'source': encoded, 'rebuild_geometry': True})

    def test_explicit_regeneration_replaces_stale_mesh(self):
        change = {'collection': 'wizard_pier', 'index': 0, 'node': [], 'attribute': 'H', 'value': '500'}
        stale = build({'mode': 'edit', 'source': self.source, 'changes': [change]})
        stale_source = base64.b64encode(stale).decode('ascii')
        saved = export({'mode': 'edit', 'source': stale_source, 'rebuild_geometry': True, 'replace_existing_mesh': True})
        self.assertNotEqual(parse_hrx(stale, 'stale.hrx')['nodes'], parse_hrx(saved, 'saved.hrx')['nodes'])
        self.assertEqual(ET.tostring(ET.fromstring(stale).find('Analysis')), ET.tostring(ET.fromstring(saved).find('Analysis')))

    def test_explicit_regeneration_rejects_quad_load(self):
        root = ET.fromstring(self.original)
        root.find('Quad').set('LoadTemplateLineKey', '7')
        source = base64.b64encode(ET.tostring(root)).decode('ascii')
        with self.assertRaisesRegex(ValueError, 'loads assigned directly'):
            export({'mode': 'edit', 'source': source, 'rebuild_geometry': True, 'replace_existing_mesh': True})

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
            'Work',
        )
        self.assertEqual(
            root.find("Analysis[@Name='Modal_0']").get('AdapticConvergenceCriteria'),
            'Work',
        )

    def test_generated_model_has_arch_crown_and_pier_model_points(self):
        root = ET.fromstring(self.original)
        points = root.findall('ModelPoint')
        labels = [point.get('Description').split(' · ')[0] for point in points[1:]]
        self.assertEqual(points[0].get('Key'), '1')
        self.assertEqual(labels, [
            'Span 1 arch crown -Y', 'Span 1 arch crown 0Y', 'Span 1 arch crown +Y',
            'Span 2 arch crown -Y', 'Span 2 arch crown 0Y', 'Span 2 arch crown +Y',
            'Pier 1 top -Y', 'Pier 1 top +Y', 'Pier 1 bottom -Y', 'Pier 1 bottom +Y',
        ])
        nodes = {node.get('Key') for node in root.findall('Node')}
        for point in points:
            self.assertEqual(point.get('ElementType'), 'Node')
            self.assertIn(point.get('ElementKey'), nodes)
        active = root.find("Analysis[@Name='Vert']/ActiveModelPoints")
        self.assertEqual(
            [item.get('Key') for item in active],
            [point.get('Key') for point in points],
        )

    def test_monitoring_points_use_widened_pier_and_masonry_wall_strips(self):
        payload = defaults()
        payload['strips'][0]['material_key'] = 18
        payload['strips'][-1]['material_key'] = 18
        payload['piers'][0]['w2'] = 500
        root = ET.fromstring(build({'mode': 'create', 'payload': payload}))
        points = {p.get('Description', '').split(' · ')[0]: p for p in root.findall('ModelPoint')}
        for label in ('Span 1 spandrel top -Y', 'Span 1 spandrel top +Y',
                      'Pier 1 spandrel top -Y', 'Pier 1 spandrel top +Y'):
            self.assertIn(label, points)
        for side in ('-Y', '+Y'):
            pier = points[f'Pier 1 top {side}'].get('Point')
            wall = points[f'Pier 1 spandrel top {side}'].get('Point')
            py = float(pier.split(';')[1])
            wy = float(wall.split(';')[1])
            self.assertGreater(abs(py), abs(wy))

    def test_legacy_generated_points_migrate_without_changing_existing_keys(self):
        from builder_api import _regenerated_geometry, _regenerate_export
        payload = defaults()
        payload['strips'][0]['material_key'] = 18
        payload['strips'][-1]['material_key'] = 18
        payload['piers'][0]['w2'] = 500
        source = build({'mode': 'create', 'payload': payload})
        legacy = _regenerated_geometry(source, legacy_monitoring_points=True)
        old = ET.fromstring(legacy)
        updated = ET.fromstring(_regenerate_export(legacy, legacy))
        old_points, new_points = old.findall('ModelPoint'), updated.findall('ModelPoint')
        self.assertGreater(len(new_points), len(old_points))
        self.assertEqual([p.get('Key') for p in new_points[:len(old_points)]],
                         [p.get('Key') for p in old_points])
        active = updated.find("Analysis[@Name='Vert']/ActiveModelPoints")
        self.assertEqual([item.get('Key') for item in active], [point.get('Key') for point in new_points])

    def test_build_persists_minor_scour_preference(self):
        from hrx_model import parse_hrx
        payload = defaults()
        payload['minor_scour_stages'] = True
        source = build({'mode': 'create', 'payload': payload})
        self.assertEqual(parse_hrx(source, 'test.hrx')['metadata']['HiStrAViewMinorScourStages'], 'true')

    def test_add_next_scour_analysis_preserves_predecessor(self):
        source = build({'mode': 'create', 'payload': defaults(),
                        'operations': [{'op': 'add_next_scour_analysis'}]})
        root = ET.fromstring(source)
        previous = root.find("Analysis[@Name='scour_4']")
        added = root.find("Analysis[@Name='scour_5']")
        self.assertIsNotNone(added)
        self.assertEqual(added.get('InitialAnalysisKey'), previous.get('Key'))
        self.assertEqual(added.get('IntegrationMethod'), 'LoadControl')
        self.assertEqual(added.get('Mult'), '0')

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

    def test_span_load_and_arch_control_point_generation(self):
        import copy
        payload = copy.deepcopy(self.payload)
        payload['spans'][0]['load_position'] = '1/4'
        payload['spans'][0]['load_value'] = 0.02
        raw = build({'mode': 'create', 'payload': payload})
        root = ET.fromstring(raw)

        # Check Load Template Key="3"
        templates = [t for t in root.findall('Template') if t.get('Key') == '3']
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0].get('PurposeType'), 'LineLoad')
        item = templates[0].find('LoadtemplateItemList/LoadTemplateItem')
        self.assertIsNotNone(item)
        self.assertEqual(item.get('LoadValue'), '0.02')
        self.assertEqual(item.get('IdLoadCondition'), '11')

        # Check LoadElement
        load_elements = root.findall('LoadElement')
        self.assertGreaterEqual(len(load_elements), 1)
        self.assertEqual(load_elements[0].get('IdLoadTemplate'), '3')
        self.assertEqual(load_elements[0].get('ElementType'), 'Quad')

        # Check arch control ModelPoint
        model_points = root.findall('ModelPoint')
        control_mps = [mp for mp in model_points if 'arch control point' in mp.get('Description', '')]
        self.assertEqual(len(control_mps), 1)
        control_key = control_mps[0].get('Key')

        # Check LiveLoad_1 analysis has MasterPoint set to control_key
        analyses = {a.get('Name'): a for a in root.findall('Analysis')}
        self.assertIn('LiveLoad_1', analyses)
        live_load = analyses['LiveLoad_1']
        self.assertEqual(live_load.get('MasterPoint'), control_key)
        adaptic_phase = live_load.find('AdapticPhases/AdapticPhase')
        self.assertIsNotNone(adaptic_phase)
        self.assertEqual(adaptic_phase.get('ModelPointKey'), control_key)


if __name__ == '__main__':
    unittest.main()

class AnalysisStepEditTests(unittest.TestCase):
    def test_load_function_step_discretization_is_saved_to_hrx(self):
        payload = defaults()
        original = build({'mode': 'create', 'payload': payload})
        encoded = base64.b64encode(original).decode('ascii')
        edited = build({'mode': 'edit', 'source': encoded, 'changes': [
            {'collection': 'load_function', 'index': 0, 'node': [],
             'attribute': 'DiscrVal', 'value': '0.05000000000005'},
        ]})
        before, after = _document(original), _document(edited)
        self.assertEqual(before.find('LoadFunction').get('DiscrVal'), '0.2')
        self.assertEqual(after.find('LoadFunction').get('DiscrVal'), '0.05000000000005')
        self.assertEqual(len(before.findall('LoadFunctionItem')), len(after.findall('LoadFunctionItem')))
