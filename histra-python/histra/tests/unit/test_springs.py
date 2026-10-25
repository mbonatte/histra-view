"""Tests for histra.springs — now using correct constructor signatures."""
import unittest
import numpy as np
from histra.types.phase_enum import PhaseEnum
from histra.springs.base import Spring
from histra.springs.elastic import SpringElastic
from histra.springs.coulomb import SpringCoulomb
from histra.springs.multilinear import SpringMultiLinear


class TestSpringElastic(unittest.TestCase):
    def setUp(self):
        self.s = SpringElastic(k=2000.0)

    def test_initial_state(self):
        self.assertEqual(self.s.u, 0.0)
        self.assertEqual(self.s.f, 0.0)

    def test_set_trial_strain_elastic(self):
        self.s.set_trial_strain(0.01)
        self.assertAlmostEqual(self.s.get_force(), 20.0)
        self.assertAlmostEqual(self.s.get_displacement(), 0.01)
        self.assertEqual((self.s.f, self.s.u), (0.0, 0.0))

    def test_commit(self):
        self.s.set_trial_strain(0.02)
        self.s.commit()
        self.assertAlmostEqual(self.s.u, 0.02)
        self.assertAlmostEqual(self.s.f, 40.0)

    def test_trial_increment_and_revert_match_csharp(self):
        self.s.set_trial_strain(0.02)
        self.s.commit()
        self.s.set_trial_strain(0.025)
        self.assertAlmostEqual(self.s.get_force(), 50.0)
        self.assertAlmostEqual(self.s.get_incr_force(), 10.0)
        self.s.revert_to_last_commit()
        self.assertAlmostEqual(self.s.get_force(), 40.0)
        self.assertAlmostEqual(self.s.get_displacement(), 0.02)

    def test_stiffness(self):
        self.assertEqual(self.s.k, 2000.0)

    def test_revert_to_start(self):
        self.s.set_trial_strain(0.5)
        self.assertAlmostEqual(self.s.get_force(), 1000.0)
        self.s.commit()
        self.assertAlmostEqual(self.s.f, 1000.0)
        self.s.revert_to_start()
        self.assertEqual(self.s.u, 0.0)
        self.assertEqual(self.s.f, 0.0)


class TestSpringCoulomb(unittest.TestCase):
    def setUp(self):
        self.s = SpringCoulomb(k=2000.0)

    def test_basic_elastic(self):
        """SpringCoulomb (without overriding set_trial_strain) is elastic."""
        self.s.set_trial_strain(0.04)
        self.assertAlmostEqual(self.s.f, 80.0)
        self.assertAlmostEqual(self.s.u, 0.04)

    def test_stiffness(self):
        self.assertEqual(self.s.k, 2000.0)


class TestSpringMultiLinear(unittest.TestCase):
    """The legacy container preserves fields and rejects unimplemented solving."""

    def setUp(self):
        self.s = SpringMultiLinear(deformations="0.0,0.1,0.2,0.3",
                                   forces="0.0,100.0,100.0,150.0")

    def test_initial(self):
        self.assertEqual(self.s.f, 0.0)
        self.assertEqual(self.s.u, 0.0)

    def test_stores_deformations(self):
        self.assertEqual(self.s.deformations, "0.0,0.1,0.2,0.3")

    def test_stores_forces(self):
        self.assertEqual(self.s.forces, "0.0,100.0,100.0,150.0")

    def test_unsupported_update_preserves_stored_state(self):
        with self.assertRaisesRegex(NotImplementedError, "multilinear plastic"):
            self.s.set_trial_strain(0.05)
        self.assertEqual(self.s.u, 0.0)
        self.assertEqual(self.s.f, 0.0)


if __name__ == "__main__":
    unittest.main()
