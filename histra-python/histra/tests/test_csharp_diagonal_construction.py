"""Whole native Quad.SetDiagonalQuad construction with masonry flexural laws."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

from histra.elements.quad import Quad
from histra.preprocessing.constitutive_laws import HystereticLaw, CoulombLaw, diagonal_flex_law
from histra.preprocessing.spring_assignment import _quad_spring


class NativeDiagonalConstructionTests(unittest.TestCase):
    def test_hysteretic_flexural_dispatch_and_weak_compression(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_diagonal_construction_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for case in fixture['cases']:
            with self.subTest(geometry=case['geometry'], fy_c=case['input_fy_c']):
                def law(E):
                    return HystereticLaw(E=E, fy_t=.23, fy_c=case['input_fy_c'],
                        tensile_curve='LinearSoftening', compressive_curve='LinearSoftening',
                        ratio_et_t=0., ratio_et_c=0., alfa_r_t=1., alfa_r_c=1.,
                        alfa_u_t=0., alfa_u_c=0., G_t=0., G_c=0.,
                        eps_u_t=.06, eps_u_c=.08, law_type='ElastoPlasticDuctilityFixed')
                with patch('histra.preprocessing.constitutive_laws.flex_law',
                           side_effect=lambda material, *, vertical=False: law(321.25 if vertical else 500.)):
                    flex = diagonal_flex_law(None)
                self.assertEqual(case['flex_type'], 'Hysteretic')
                with self.subTest(quantity='blend'):
                    self.assertEqual(flex.E, case['blend_E'])
                    self.assertEqual(flex.eps_u_t, case['blend_eps_t'])
                    self.assertEqual(flex.eps_u_c, case['blend_eps_c'])
                shear = CoulombLaw(E=230., cohesion=.5, mu=.45, plastic_stiffness_ratio=.001,
                                  max_tensile_ratio=.4, reload_stiffness_ratio=.8, ductility=1.5)
                q = Quad(material_key=1, length=case['Length'], diago=case['Diago'],
                         sin=case['Sin'], cos=case['Cos'], thickness=case['thickness'])
                with patch('histra.preprocessing.spring_assignment._material', return_value=object()), \
                     patch('histra.preprocessing.spring_assignment._cached_diagonal_laws', return_value=(flex, shear)):
                    spring = _quad_spring(SimpleNamespace(collections=object()), q)
                self.assertEqual(spring.k, case['K'])
                self.assertEqual(q.compute_volume(), case['volume'])
                np.testing.assert_allclose(spring.fy, case['Fy'], rtol=1e-13, atol=1e-10)
                np.testing.assert_allclose(spring.ur, case['Ur'], rtol=1e-13, atol=1e-12)
                self.assertEqual(spring.area, case['Area'])
