"""Native .NET Framework diagonal stiffness arithmetic."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from histra.elements.quad_geometry import QuadGeometryMixin
from histra.preprocessing.csharp_math import POWER_BACKEND, csharp_pow


class NativeQuadPowerTests(unittest.TestCase):
    @unittest.skipUnless(POWER_BACKEND == 'dotnet-framework-crt',
                         'Exact native arithmetic requires the Windows Framework CRT')
    def test_diagonal_factor_and_stiffness_match_native(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_quad_power_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for case in fixture['cases']:
            with self.subTest(quad=case['quad']):
                factor, k = float(case['factor']), float(case['k'])
                self.assertEqual(csharp_pow(factor, 2.0), float(case['power']))
                quad = SimpleNamespace(
                    spring=SimpleNamespace(get_k=lambda alfa: k),
                    d_alfa_2d_diag=lambda: factor, status=SimpleNamespace(k=0.0))
                self.assertEqual(QuadGeometryMixin.compute_k(quad), float(case['stiffness']))
