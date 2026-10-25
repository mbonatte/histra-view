"""Original node-interface law-slot selection on all six Quad faces."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from histra.preprocessing.constitutive_laws import CoulombLaw
from histra.preprocessing.material_selection import _interface_sliding_law


class NativeOutOfPlaneSelectionTests(unittest.TestCase):
    def test_both_sides_and_all_quad_faces(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_out_of_plane_selection_2026_1_1.json').read_text(encoding='utf-8-sig'))
        model = SimpleNamespace(collections=SimpleNamespace(quads={
            1: SimpleNamespace(reference_e1=[1., 0., 0.]),
            2: SimpleNamespace(reference_e1=[.6, .8, 0.])}))
        interface = SimpleNamespace(reference_e1=[1., 0., 0.])
        laws = {name: CoulombLaw(E=E, cohesion=.3, mu=.5,
                                plastic_stiffness_ratio=0., max_tensile_ratio=.2)
                for name, E in [('hor', 15.), ('vert', 16.), ('dir3', 17.)]}
        for case in fixture['cases']:
            for side, field in [(1, 'first_side_E'), (2, 'second_side_E')]:
                with self.subTest(face=case['face'], side=side):
                    with patch('histra.preprocessing.material_selection._cached_sliding_law',
                               side_effect=lambda material, *, direction, **kwargs: laws[direction]):
                        law = _interface_sliding_law(
                            model, interface, parent_type='Quad', parent_key=side,
                            face=case['face'], material=None, out_of_plane=True,
                            vertical=False, cache=None, side=side)
                    self.assertEqual(law.E, case[field])
                    if side == 2:
                        self.assertIs(law, laws['vert' if case['second_is_vertical'] else 'dir3'])
