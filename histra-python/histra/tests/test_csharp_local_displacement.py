"""Native per-afference accumulation into a nonzero local displacement."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np
from histra.elements.quad import Quad
from histra.springs.elastic import SpringElastic
from histra.types.afference_entry import AfferenceEntry
from histra.solver.hysteretic_kernels.kinematics import (
    _map_global_to_local, _map_and_prepare_interface_kinematics)


class NativeLocalDisplacementTests(unittest.TestCase):
    def test_scalar_quad_and_compiled_projections(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_local_displacement_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for index, case in enumerate(fixture['cases']):
            with self.subTest(case=index):
                x = np.asarray(case['x'], dtype=np.float64)
                coefficients = np.asarray(case['coefficients'], dtype=np.float64)
                q = Quad(spring=SpringElastic(k=1.0))
                q.aff = [[AfferenceEntry(gdl=i+1, alfa=c) for i, c in enumerate(coefficients)]] + [[] for _ in range(6)]
                q.status.u[0] = case['initial']
                q.update_domain(x, SimpleNamespace(step=1))
                self.assertEqual(q.status.u[0], case['expected'])
                for width in (7, 12):
                    offsets = np.full(width+1, x.size, dtype=np.int32)
                    offsets[0] = 0
                    gdls = np.arange(x.size, dtype=np.int32)
                    du = np.zeros((1, width))
                    local_u = np.zeros((1, width))
                    local_u[0, 0] = case['initial']
                    _map_global_to_local(x, offsets, gdls, coefficients, du, local_u)
                    self.assertEqual(local_u[0, 0], case['expected'])
                    if width == 12:
                        local_u.fill(0.0)
                        local_u[0, 0] = case['initial']
                        _map_and_prepare_interface_kinematics(
                            x, offsets, gdls, coefficients, du, local_u,
                            np.array([2.0]), np.array([False]), np.array([6]), np.array([2]),
                            np.zeros(1), np.zeros(1), np.zeros(1), np.zeros((1, 3)))
                        self.assertEqual(local_u[0, 0], case['expected'])
