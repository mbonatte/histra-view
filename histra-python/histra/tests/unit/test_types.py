"""Tests for histra.types — lowest-level types."""
import unittest

from histra.model.model import Collections, Model
from histra.solver.program import Program
import numpy as np
from histra.types.point import Point
from histra.types.afference_entry import AfferenceEntry
from histra.types.phase_enum import PhaseEnum
from histra.types.hysteretic_curve_types import (
    HystereticTensileCurveTypeEnum,
    HystereticCompressiveCurveTypeEnum,
)
from histra.types.convergence_test import ConvergenceTest
from histra.types.linear_system import LinearSystem
from histra.types.integrator_state import IntegratorState
from histra.types.xml_utils import _attr


class TestPoint(unittest.TestCase):
    def test_defaults(self):
        p = Point()
        self.assertEqual(p.x, 0.0)
        self.assertEqual(p.y, 0.0)
        self.assertEqual(p.z, 0.0)

    def test_from_str(self):
        p = Point.from_str("1.5;2.5;3.0")
        self.assertEqual(p.x, 1.5)
        self.assertEqual(p.y, 2.5)
        self.assertEqual(p.z, 3.0)

    def test_from_str_partial(self):
        p = Point.from_str("1.0;2.0")
        self.assertEqual(p.x, 1.0)
        self.assertEqual(p.y, 2.0)
        self.assertEqual(p.z, 0.0)

    def test_iter(self):
        p = Point(1.0, 2.0, 3.0)
        xs = list(p)
        self.assertEqual(xs, [1.0, 2.0, 3.0])


class TestAfferenceEntry(unittest.TestCase):
    def test_create(self):
        e = AfferenceEntry(gdl=5, alfa=2.5)
        self.assertEqual(e.gdl, 5)
        self.assertEqual(e.alfa, 2.5)


class TestPhaseEnum(unittest.TestCase):
    def test_members(self):
        self.assertEqual(PhaseEnum.Elastic, 0)
        self.assertEqual(PhaseEnum.Plastic_t, 1)
        self.assertEqual(PhaseEnum.Plastic_c, 2)
        self.assertEqual(PhaseEnum.Slip, 10)


class TestHystereticCurveTypes(unittest.TestCase):
    def test_tensile_members(self):
        self.assertIn(HystereticTensileCurveTypeEnum.Elastic, [
            HystereticTensileCurveTypeEnum.Elastic,
            HystereticTensileCurveTypeEnum.LinearHardening,
            HystereticTensileCurveTypeEnum.LinearSoftening,
            HystereticTensileCurveTypeEnum.Exponential,
        ])

    def test_compressive_members(self):
        self.assertIn(HystereticCompressiveCurveTypeEnum.Parabolic, [
            HystereticCompressiveCurveTypeEnum.Elastic,
            HystereticCompressiveCurveTypeEnum.LinearHardening,
            HystereticCompressiveCurveTypeEnum.LinearSoftening,
            HystereticCompressiveCurveTypeEnum.Parabolic,
        ])


class TestXmlUtils(unittest.TestCase):
    class FakeElem:
        def __init__(self, d):
            self._d = d
        def get(self, k, default=None):
            return self._d.get(k, default)

    def test_attr_present(self):
        e = self.FakeElem({"K": "1500"})
        self.assertEqual(_attr(e, "K", 0, float), 1500.0)

    def test_attr_missing(self):
        e = self.FakeElem({})
        self.assertEqual(_attr(e, "K", 100, float), 100)

    def test_attr_bool(self):
        e = self.FakeElem({"Flag": "true"})
        self.assertTrue(_attr(e, "Flag", False, lambda v: str(v).lower() == "true"))


class TestConvergenceTest(unittest.TestCase):
    @staticmethod
    def _context(values):
        ls = LinearSystem(len(values))
        ls.b[:] = values
        return Program(gdl=len(values), ls=ls), Model(collections=Collections()), ls

    def test_converges_on_small_residual(self):
        ct = ConvergenceTest(tolerance=1e-6, max_iter=10)
        p, model, ls = self._context([1e-10] * 5)
        ct.start()
        result = ct.test(p, model, ls)
        self.assertGreaterEqual(result, 0)

    def test_continues_on_large_residual(self):
        ct = ConvergenceTest(tolerance=1e-6, max_iter=10)
        p, model, ls = self._context([1.0] * 5)
        ct.start()
        result = ct.test(p, model, ls)
        self.assertEqual(result, -1)


class TestLinearSystem(unittest.TestCase):
    def test_create(self):
        ls = LinearSystem(10)
        self.assertEqual(ls.n, 10)
        self.assertEqual(len(ls.x), 10)
        self.assertEqual(len(ls.b), 10)

    def test_sumb(self):
        ls = LinearSystem(5)
        ls.sumb(2, 3.0)
        self.assertEqual(ls.b[2], 3.0)

    def test_zero_b(self):
        ls = LinearSystem(5)
        ls.b[2] = 3.0
        ls.zero_b()
        self.assertEqual(ls.b[2], 0.0)

    def test_copy_b_to_b0(self):
        ls = LinearSystem(5)
        ls.b[0] = 42.0
        ls.copy_b_to_b0()
        self.assertEqual(ls.b0[0], 42.0)

    def test_solve_and_factorization_counters(self):
        ls = LinearSystem(2, backend="superlu")
        ls.set_k(0, 0, 2.0)
        ls.set_k(1, 1, 4.0)

        ls.solve(np.array([2.0, 8.0]))
        np.testing.assert_allclose(ls.x, [1.0, 2.0])
        self.assertEqual(ls.solve_count, 1)
        self.assertEqual(ls.factorization_count, 1)

        ls.solve(np.array([4.0, 4.0]))
        np.testing.assert_allclose(ls.x, [2.0, 1.0])
        self.assertEqual(ls.solve_count, 2)
        self.assertEqual(ls.factorization_count, 1)

        ls.set_k(0, 0, 1.0)
        ls.solve(np.array([2.0, 4.0]))
        self.assertEqual(ls.solve_count, 3)
        self.assertEqual(ls.factorization_count, 2)

    def test_umfpack_solve_in_place(self):
        from histra.types.umfpack import find_umfpack_library
        if find_umfpack_library() is None:
            self.skipTest("UMFPACK library not available")
        ls = LinearSystem(2, backend="umfpack")
        ls.set_k(0, 0, 2.0)
        ls.set_k(1, 1, 4.0)

        ls.solve(np.array([2.0, 8.0]))
        np.testing.assert_allclose(ls.x, [1.0, 2.0])
        self.assertEqual(ls.solve_count, 1)
        self.assertEqual(ls.factorization_count, 1)

        # Ensure pointers are cached and in-place solve is exact
        ls.solve(np.array([4.0, 4.0]))
        np.testing.assert_allclose(ls.x, [2.0, 1.0])
        self.assertEqual(ls.solve_count, 2)
        self.assertEqual(ls.factorization_count, 1)


class TestIntegratorState(unittest.TestCase):
    def test_defaults(self):
        s = IntegratorState()
        self.assertEqual(s.step, 0)
        self.assertEqual(s.lambda_, 0.0)
        self.assertEqual(s.dlambda, 0.0)

    def test_custom(self):
        s = IntegratorState(step=1, lambda_=0.5, dlambda=0.1)
        self.assertEqual(s.step, 1)
        self.assertEqual(s.lambda_, 0.5)
        self.assertEqual(s.dlambda, 0.1)


if __name__ == "__main__":
    unittest.main()
