"""Preserve the source's force-minus-increment cancellation in Quad sigma."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.solver.hysteretic_kernels.transverse import _finish_transverse_batch


class NativeNormalForceTests(unittest.TestCase):
    def test_cached_force_uses_native_getter_arithmetic(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_normal_force_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for case in fixture['cases']:
            for constrained in (False, True):
                with self.subTest(case=case, constrained=constrained):
                    trial=np.zeros((1,10));committed=np.zeros((1,9))
                    trial[0,6]=case['trial'];committed[0,6]=case['committed']
                    normal=np.zeros(1);force=np.zeros(1);max_u=np.zeros(1)
                    _finish_transverse_batch(
                        trial,committed,np.array([1.]),np.array([1.]),np.array([0.]),np.array([2.]),
                        np.array([0]),np.array([1]),np.array([constrained]),np.zeros((1,6)),normal,force,max_u)
                    self.assertEqual(force[0],case['reconstructed_committed'])
                    self.assertEqual(normal[0],-case['increment'])
