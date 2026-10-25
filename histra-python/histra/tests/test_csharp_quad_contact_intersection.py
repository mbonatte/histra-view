"""Contact admission boundaries from the original C# intersection routine."""
import json
from pathlib import Path
import unittest

import numpy as np

from histra.preprocessing.contact_geometry import _coplanar_quad_intersection_prechecked


class NativeQuadContactIntersectionTests(unittest.TestCase):
    def test_original_four_vertex_contact_boundary(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_quad_contact_intersection_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for case in fixture['cases']:
            with self.subTest(case=case['name']):
                actual = _coplanar_quad_intersection_prechecked(
                    np.asarray(case['first'], dtype=float), np.asarray(case['second'], dtype=float),
                    np.array([0., 0., 1.]), node_tolerance=fixture['node_tolerance'])
                # Original GIQuadQuadSerial, Parallel and Iteration admit only
                # positive intersections containing exactly four vertices.
                admitted = case['code'] > 0 and case['native_count'] == 4
                self.assertEqual(actual is not None, admitted)
                if admitted:
                    # Contact vertices are cyclically reordered later when
                    # preparing endpoints; compare the original vertex set.
                    np.testing.assert_array_equal(
                        sorted(map(tuple, actual)), sorted(map(tuple, case['intersection'])))
