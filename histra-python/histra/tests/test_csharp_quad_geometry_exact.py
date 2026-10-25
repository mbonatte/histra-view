"""Exact corner geometry from freshly executed C# Quad.SetGeometry."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import sys
import numpy as np
from histra.preprocessing.quad_geometry import compute_quad_geometry_batch


def _assert_native_geometry_field(actual, expected, field):
    if sys.platform == 'linux' and field == 'Sin':
        # Linux libm and the Windows Framework CRT differ by a few last bits.
        np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-15)
    else:
        np.testing.assert_array_equal(actual, expected)


class NativeQuadGeometryTests(unittest.TestCase):
    def test_original_corner_geometry_exact(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/csharp_quad_geometry_exact_2026_1_1.json').read_text(encoding='utf-8'))
        for case in fixture['cases']:
            arrays=compute_quad_geometry_batch(np.array([case['points']],dtype=np.float32),np.array([case['thickness']],dtype=np.float32))
            for index,field in enumerate(('Length','Diago','Cos','Sin')):
                with self.subTest(key=case['key'],field=field):
                    _assert_native_geometry_field(arrays[index][0],case[field],field)


class GeometryTolerancePolicyTests(unittest.TestCase):
    def test_linux_sine_allows_only_rounding_noise(self):
        with patch('sys.platform', 'linux'):
            _assert_native_geometry_field([np.nextafter(1.0, 2.0)], [1.0], 'Sin')
            with self.assertRaises(AssertionError):
                _assert_native_geometry_field([1.0 + 1e-12], [1.0], 'Sin')

    def test_windows_sine_remains_exact(self):
        with patch('sys.platform', 'win32'), self.assertRaises(AssertionError):
            _assert_native_geometry_field([np.nextafter(1.0, 2.0)], [1.0], 'Sin')

    def test_other_fields_remain_exact_on_linux(self):
        for field in ('Length', 'Diago', 'Cos'):
            with self.subTest(field=field), patch('sys.platform', 'linux'), self.assertRaises(AssertionError):
                _assert_native_geometry_field([np.nextafter(1.0, 2.0)], [1.0], field)
