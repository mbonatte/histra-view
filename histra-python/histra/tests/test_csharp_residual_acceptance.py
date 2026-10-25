"""Original assembly residuals and convergence decisions from actual Dhir states."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from histra.types.convergence_test import ConvergenceTest
from histra.types.linear_system import LinearSystem

FIXTURES = Path(__file__).parent / 'fixtures'


def decode(values):
    return np.asarray([int(value) for value in values], dtype=np.int64).view(np.float64)


def bits(value):
    return int(np.asarray([value], dtype=np.float64).view(np.int64)[0])


class NativeResidualAcceptanceTests(unittest.TestCase):
    @patch('histra.solver.model_manager.ModelManager.find_max_u')
    def test_original_work_accepts_while_force_test_continues(self, _find_max):
        fixture = json.loads((FIXTURES / 'csharp_residual_acceptance_2026_1_1.json').read_text())
        with np.load(FIXTURES / 'csharp_residual_acceptance_2026_1_1.npz') as vectors:
            for case in fixture['cases']:
                with self.subTest(state=case['id']):
                    system = LinearSystem(case['compared_dofs'], backend='superlu')
                    system.b[:] = vectors[case['id'] + '_b']
                    system.x[:] = vectors[case['id'] + '_x']
                    for criterion, native in [('Work', 'CTestEnergyIncr'), ('ForceMoment', 'CTestNormUnbalance')]:
                        test = ConvergenceTest(tolerance=0.002, max_iter=3000, max_u=10., criterion=criterion)
                        test.start()
                        self.assertEqual(test.test(SimpleNamespace(max_u=0.), SimpleNamespace(), system), case[native + '_result'])
                        self.assertEqual(bits(test.get_error()), int(case[native + '_error_bits']))
                    self.assertGreater(system.get_b_norm(), 1000.)
