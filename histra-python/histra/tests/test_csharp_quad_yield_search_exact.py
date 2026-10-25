"""Exact native capacity search, including multiplication association."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.elements.quad_kernels import quad_yield_search, quad_yield_search_scalar
from histra.preprocessing.csharp_math import POWER_BACKEND


@unittest.skipUnless(POWER_BACKEND == 'dotnet-framework-crt', 'Windows Framework arithmetic required')
class NativeQuadYieldSearchTests(unittest.TestCase):
    def test_original_capacity_search(self):
        data=json.loads((Path(__file__).parent/'fixtures/csharp_quad_yield_search_exact_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for case in data['cases']:
            args=[case[f] for f in ('k','E','G','Fyt','Fyc','dalfa')]
            args += [case['Length'][j] for j in (0,1,3)]
            args += case['Cos'][:2]+case['Sin']
            for name,fn in [('compiled',quad_yield_search),('scalar',quad_yield_search_scalar)]:
                with self.subTest(key=case['key'],backend=name):
                    np.testing.assert_array_equal(fn(*args),case['Fy'])
