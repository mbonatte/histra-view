import math
import sys
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from material_preview import preview


class MaterialPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = ET.parse(Path(__file__).resolve().parents[2] / 'model_example.hrx').getroot()
        cls.attributes = next(dict(e.attrib) for e in root.findall('Template') if e.get('Key') == '18')

    def test_elastic_range_has_correct_stress_and_units(self):
        result = preview({'attributes': self.attributes, 'amplitude': 1e-7, 'cycles': 1})
        for strain, stress in result['points']:
            self.assertAlmostEqual(stress, 1620 * strain, delta=1e-8)
        self.assertEqual(result['stressUnit'], 'kN/cm²')

    def test_cyclic_shear_reaches_strength_and_dissipates_energy(self):
        result = preview({'attributes': self.attributes, 'mechanism': 'shear'})
        points = result['points']
        self.assertAlmostEqual(max(p[1] for p in points), .029, places=7)
        self.assertAlmostEqual(min(p[1] for p in points), -.029, places=7)
        work = sum((b[0] - a[0]) * (b[1] + a[1]) / 2 for a, b in zip(points, points[1:]))
        self.assertGreater(abs(work), 1e-7)

    def test_preview_is_repeatable_and_does_not_mutate_material(self):
        attributes = self.attributes.copy()
        first = preview({'attributes': attributes})
        second = preview({'attributes': attributes})
        self.assertEqual(first, second)
        self.assertEqual(attributes, self.attributes)

    def test_each_mechanism_and_local_direction_produces_finite_response(self):
        for mechanism, direction in [('rocking', '1'), ('rocking', '2'), ('shear', '1'), ('sliding', '1'), ('sliding', '2'), ('sliding', '3')]:
            with self.subTest(mechanism=mechanism, direction=direction):
                result = preview({'attributes': self.attributes, 'mechanism': mechanism, 'direction': direction})
                self.assertEqual(len(result['points']), 721)
                self.assertTrue(all(math.isfinite(value) for point in result['points'] for value in point))

    def test_invalid_controls_and_non_masonry_fail_closed(self):
        for controls in [{'cycles': 100}, {'amplitude': float('nan')}, {'amplitude': -1}, {'direction': '5'}, {'history': 'unknown'}]:
            with self.subTest(controls=controls), self.assertRaises(ValueError):
                preview({'attributes': self.attributes, **controls})
        with self.assertRaises(ValueError):
            preview({'attributes': {'PurposeType': 'SteelMaterial'}})


if __name__ == '__main__':
    unittest.main()
