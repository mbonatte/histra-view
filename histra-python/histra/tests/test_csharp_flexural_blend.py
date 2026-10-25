"""Exact native orthotropic law blending, including isotropic cancellation."""
import json
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from histra.preprocessing.constitutive_laws import HystereticLaw
from histra.preprocessing.material_selection import _blend_hysteretic_laws, _flex_alignment
from histra.preprocessing.material_selection import _interface_flex_law


class NativeFlexuralBlendTests(unittest.TestCase):
    def test_broad_face_preserves_unblended_primary_source_slot(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_flexural_blend_2026_1_1.json').read_text())
        case = fixture['cases'][-2]
        horizontal = HystereticLaw(**case['primary'])
        material = SimpleNamespace(value=lambda name, default: True)
        interface = SimpleNamespace(reference_e1=case['interface_e1'])
        quad = SimpleNamespace(reference_e1=case['quad_e1'])
        with patch('histra.preprocessing.material_selection._cached_flex_law',
                   side_effect=lambda material, *, vertical, cache:
                   HystereticLaw(**case['secondary' if vertical else 'primary'])):
            for face in (4, 5):
                self.assertEqual(_interface_flex_law(material, interface, quad, face), horizontal)

    def test_laws_and_alignment_match_original_csharp(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_flexural_blend_2026_1_1.json').read_text())
        for case in fixture['cases']:
            with self.subTest(interface=case['interface'], quad=case['quad'], axes=case['quad_e1']):
                expected = case['expected']
                c1, c2 = _flex_alignment(case['interface_e1'], case['quad_e1'])
                self.assertEqual(c1, expected['c1'])
                self.assertEqual(c2, expected['c2'])
                primary = HystereticLaw(**case['primary'])
                secondary = HystereticLaw(**case['secondary'])
                actual = _blend_hysteretic_laws(primary, secondary, c1, c2)
                for name, value in expected.items():
                    if name not in ('c1', 'c2'):
                        self.assertEqual(getattr(actual, name), value, name)
                for name in ('alfa_r_t','alfa_r_c','alfa_u_t','alfa_u_c','law_type'):
                    self.assertEqual(getattr(actual, name), getattr(primary, name), name)
