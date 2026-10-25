"""Verify explicit C# control settings against the original native routine."""
import json
from pathlib import Path
import unittest
import scipy.sparse as sp
from histra.types.umfpack import UmfpackFactorization, find_umfpack_library
from histra.types.linear_system import LinearSystem


class NativeLinearControlTests(unittest.TestCase):
    def test_explicit_native_solver_profile(self):
        if find_umfpack_library() is None:
            self.skipTest('UMFPACK library is unavailable')
        data=json.loads((Path(__file__).parent/'fixtures/csharp_linear_controls_2026_1_1.json').read_text(encoding='utf-8-sig'))
        ls=LinearSystem(2,backend='umfpack',precision='accurate',ordering='amd')
        self.assertEqual(ls.irstep,data['refinement'])
        with UmfpackFactorization(sp.csc_matrix([[4.,1.],[1.,3.]]),irstep=ls.irstep,ordering=ls.ordering) as factor:
            for slot,name in ((5,'strategy'),(7,'refinement'),(10,'ordering')):
                with self.subTest(setting=name):
                    self.assertEqual(factor.control[slot],data[name])
