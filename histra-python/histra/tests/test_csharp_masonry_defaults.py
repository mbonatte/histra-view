"""Omitted material attributes: original constructor, XML reader and law factories."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import xml.etree.ElementTree as ET

from histra.io.hr_loader import load_model
from histra.model.masonry_material import MasonryMaterial
from histra.preprocessing.constitutive_laws import flex_law, shear_law, sliding_law, material_float


def fixture():
    return json.loads((Path(__file__).parent / 'fixtures' /
                      'csharp_masonry_defaults_2026_1_1.json').read_text(encoding='utf-8-sig'))


class NativeMasonryDefaultsTests(unittest.TestCase):
    def test_original_constructor_defaults(self):
        material = MasonryMaterial()
        for name, expected in fixture()['constructor'].items():
            with self.subTest(property=name):
                actual = material.value(name, None)
                self.assertEqual(actual, expected)
                if isinstance(expected, bool):
                    self.assertIs(actual, expected)
        self.assertEqual(material.value('UnknownProperty', 17), 17)

    def test_native_xml_omissions_and_law_builders(self):
        data = fixture()
        element = ET.fromstring(data['xml'])
        root = ET.Element('HiStrA')
        element.tag = 'Template'
        element.set('PurposeType', 'MasonryMaterial')
        element.set('Key', '1')
        root.append(element)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'omitted.hrx'
            ET.ElementTree(root).write(path, encoding='utf-8')
            material = load_model(path).collections.materials[1]
        self.assertNotIn('IsDuctTraz', material.properties)
        for native in data['laws']:
            with self.subTest(slot=native['slot']):
                slot = native['slot']
                if slot.endswith('Flexional'):
                    law = flex_law(material, vertical=slot.startswith('Vertical'))
                    for field, original in [('fy_t','Fy_t'),('fy_c','Fy_c'),('eps_u_t','Eps_u_t'),('eps_u_c','Eps_u_c')]:
                        self.assertEqual(getattr(law, field), native[original])
                    self.assertEqual(law.tensile_curve, native['TensileCurveType'])
                    self.assertEqual(law.compressive_curve, native['CompressiveCurveType'])
                elif slot == 'Shear':
                    law = shear_law(material)
                else:
                    direction = 'hor' if slot.endswith('Horizontal') else 'vert' if slot.endswith('Vertical') else 'dir3'
                    law = sliding_law(material, out_of_plane=slot.startswith('OutOfplane'), direction=direction)
                self.assertEqual(law.E, native['E'])
                if slot == 'Shear':
                    # Diagonal construction dispatches the Linear sub-law to
                    # SpringElastic; CoulombLaw.is_elastic is a sliding flag.
                    self.assertEqual(law.sub_law, 'Linear')
                    self.assertEqual(native['type'], 'ConstitutiveLawElastic')
                else:
                    self.assertEqual(law.is_elastic, native['type'] == 'ConstitutiveLawElastic')

    def test_explicit_zero_false_and_nondefault_values_override_constructor(self):
        material = MasonryMaterial(properties={
            'IsDuctTraz':'true', 'ShearMaxTensileRatio':'0',
            'SlidingPlasticStiffnessRatioVer':'0', 'GsDir3':'0.125',
            'SlidingYieldingDomainHor':'Linear', 'scorrhor':'false'})
        self.assertIs(material.value('IsDuctTraz', False), True)
        self.assertIs(material.value('scorrhor', True), False)
        for name, value in [('ShearMaxTensileRatio',0.),('SlidingPlasticStiffnessRatioVer',0.),('GsDir3',.125)]:
            self.assertEqual(material_float(material,name), value)
        self.assertEqual(material.value('SlidingYieldingDomainHor', ''), 'Linear')

    def test_serialized_ductility_and_ultimate_strain_share_the_native_value(self):
        data = fixture()
        material = MasonryMaterial(properties=dict(ET.fromstring(data['alias_xml']).attrib))
        self.assertNotIn('ShearUltimateStrain',material.properties)
        for name, bits in data['alias_values_bits'].items():
            expected = np.array([int(bits)],dtype=np.int64).view(np.float64)[0]
            self.assertEqual(material_float(material,name),expected)
        # The scalar material path reads the same value as the law builder.
        native = np.array([int(data['alias_ultimate_bits'])],dtype=np.int64).view(np.float64)[0]
        self.assertEqual(material.get_shear_ultimate_strain(1.,0.,1.,0.),native)
