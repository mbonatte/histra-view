"""Sliding material interpolation against calls to the original assemblies."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from histra.preprocessing.constitutive_laws import CoulombLaw
from histra.preprocessing.material_selection import _interface_sliding_law


class NativeCoulombBlendTests(unittest.TestCase):
    def test_oblique_axes_and_mixed_elastic_laws(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_coulomb_blend_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for index, case in enumerate(fixture['cases']):
            with self.subTest(case=index):
                primary, secondary = CoulombLaw(**case['primary']), CoulombLaw(**case['secondary'])
                quad = SimpleNamespace(reference_e1=case['quad_e1'])
                model = SimpleNamespace(collections=SimpleNamespace(quads={1: quad}))
                interface = SimpleNamespace(reference_e1=case['interface_e1'])
                with patch('histra.preprocessing.material_selection._cached_sliding_law',
                           side_effect=lambda material, *, direction, **kwargs:
                           primary if direction == 'hor' else secondary):
                    actual = _interface_sliding_law(
                        model, interface, parent_type='Quad', parent_key=1, face=1,
                        material=None, out_of_plane=False, vertical=False, cache=None)
                for name in ('E', 'cohesion', 'mu', 'ductility'):
                    self.assertEqual(getattr(actual, name), case['expected'][name], name)
                for name in ('plastic_stiffness_ratio', 'max_tensile_ratio', 'is_elastic'):
                    self.assertEqual(getattr(actual, name), getattr(primary, name), name)
