"""Original native p-norm selectors and ordered reductions."""
import json
from pathlib import Path
import unittest

import numpy as np

from histra.types.linear_system import LinearSystem

FIXTURES = Path(__file__).parent / 'fixtures'


def decode(values):
    return np.asarray([int(value) for value in values], dtype=np.int64).view(np.float64)


def bits(value):
    return int(np.asarray([value], dtype=np.float64).view(np.int64)[0])


class NativeVectorNormTests(unittest.TestCase):
    def test_vector_norm_selectors_and_order_match_original(self):
        fixture = json.loads((FIXTURES / 'csharp_vector_norm_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for index, case in enumerate(fixture['cases']):
            with self.subTest(case=index, norm=case['norm']):
                system = LinearSystem(len(case['b_bits']), backend='superlu')
                system.b[:] = decode(case['b_bits'])
                system.x[:] = decode(case['x_bits'])
                self.assertEqual(bits(system.get_b_norm(case['norm'])), int(case['b_norm_bits']))
                self.assertEqual(bits(system.get_x_norm(case['norm'])), int(case['x_norm_bits']))

    def test_nonfinite_max_norm_remains_fail_closed(self):
        system = LinearSystem(2, backend='superlu')
        system.b[:] = [float('nan'), 1.]
        self.assertTrue(np.isnan(system.get_b_norm(0)))
