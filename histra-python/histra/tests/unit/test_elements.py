"""Tests for QuadState, InterfaceState."""
import unittest
import numpy as np
from histra.elements.quad_state import QuadState
from histra.elements.interface_state import InterfaceState


class TestQuadState(unittest.TestCase):
    def setUp(self):
        self.qs = QuadState()

    def test_initial_state(self):
        self.assertEqual(len(self.qs.u), 7)
        self.assertEqual(self.qs.k, 0.0)
        self.assertEqual(len(self.qs.p), 7)
        self.assertEqual(self.qs.f, 0.0)

    def test_set_u(self):
        self.qs.u[0] = 0.1
        self.assertEqual(self.qs.u[0], 0.1)

    def test_set_k(self):
        self.qs.k = 5000.0
        self.assertEqual(self.qs.k, 5000.0)

    def test_set_p(self):
        self.qs.p[3] = 100.0
        self.assertEqual(self.qs.p[3], 100.0)


class TestInterfaceState(unittest.TestCase):
    def setUp(self):
        self.ist = InterfaceState()

    def test_initial_u(self):
        self.assertEqual(len(self.ist.u), 12)
        self.assertTrue(all(x == 0.0 for x in self.ist.u))

    def test_initial_forces(self):
        self.assertEqual(self.ist.forces, (0.0, 0.0, 0.0))

    def test_initial_bending_moments(self):
        self.assertEqual(self.ist.bending_moments, (0.0, 0.0, 0.0))

    def test_initial_stiffness(self):
        self.assertEqual(len(self.ist.k), 6)
        self.assertEqual(len(self.ist.k[0]), 6)

    def test_set_u(self):
        self.ist.u[3] = 0.01
        self.assertEqual(self.ist.u[3], 0.01)

    def test_set_forces(self):
        self.ist.forces = (100.0, 0.0, 50.0)
        self.assertEqual(self.ist.forces[0], 100.0)


if __name__ == "__main__":
    unittest.main()
