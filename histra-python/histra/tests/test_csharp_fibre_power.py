"""Cancellation-sensitive fibres from original C# 2026.1.1 routines."""
import ctypes
import json
from pathlib import Path
import sys
import unittest
import numpy as np
from histra.preprocessing.csharp_fibre_geometry import _csharp_stiffness, _csharp_fibre_stiffness_batch_nb
from histra.preprocessing.fibre_geometry import _fiber_stiffness_batch_nb

try:
    _runtime = ctypes.CDLL("msvcr120_clr0400.dll") if sys.platform == "win32" else None
except OSError:
    _runtime = None

@unittest.skipIf(_runtime is None, "Exact .NET Framework arithmetic requires its Windows runtime")
class NativeFibrePowerTests(unittest.TestCase):
    def test_scalar_and_compiled_fibres(self):
        self.assertIs(_fiber_stiffness_batch_nb, _csharp_fibre_stiffness_batch_nb)
        fixture = Path(__file__).parent / "fixtures/csharp_fibre_power_2026_1_1.json"
        for case in json.loads(fixture.read_text())["cases"]:
            face = case["face"]
            vint = np.asarray(case["vint"], dtype=np.float32)
            far = vint[{0:2,1:3,2:0,3:1,4:5,5:4}[face]]
            if face >= 4:
                far = far[::-1].copy()
            cells = np.asarray(case["cells"], dtype=np.float32)
            e2 = np.asarray(case["e2"], dtype=np.float32)
            output = np.empty((len(cells), 3))
            errors = np.zeros(len(cells), dtype=np.int32)
            _fiber_stiffness_batch_nb(vint[face], far, cells, 1., e2, output, errors)
            np.testing.assert_array_equal(errors, 0)
            for ref in case["expected"]:
                with self.subTest(interface=case["interface"], quad=case["quad"], cell=ref["Cell"]):
                    scalar = _csharp_stiffness.py_func(vint[face], far, cells[ref["Cell"]], 1., e2)
                    for actual in (scalar, output[ref["Cell"]]):
                        self.assertAlmostEqual(actual[0], ref["KPerE"], delta=1e-12)
                        self.assertEqual(actual[1], ref["SpringArea"])
                        self.assertEqual(actual[2], ref["SpringLength"])
