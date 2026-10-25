"""Unit tests for Quad.update_domain hysteretic_type dispatch on Coulomb springs."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock
import numpy as np

from histra.elements.quad import Quad
from histra.elements.quad_state import QuadState
from histra.springs.coulomb03 import SpringCoulomb03
from histra.springs.elastic import SpringElastic
from histra.types.phase_enum import PhaseEnum


class TestQuadCoulombInitialDispatch(unittest.TestCase):
    """Test Quad.update_domain dispatch based on hysteretic_type."""

    def setUp(self):
        self.quad = Quad()
        self.quad.key = 1
        self.quad.status = QuadState()
        self.quad.node_keys = [1, 2, 3, 4]
        # Mock aff pairs and geometry helpers
        self.quad._local_increment = MagicMock(return_value=np.zeros(7))
        self.quad.d_alfa_2d_diag = MagicMock(return_value=1.0)
        self.quad.compute_dn = MagicMock(return_value=(15.0, 50.0))
        self.quad.compute_volume = MagicMock(return_value=100.0)

    def test_coulomb_initial_dispatch(self):
        """When hysteretic_type is 'Initial', quad.update_domain calls set_trial_strain_initial and sets dn."""
        spring = SpringCoulomb03(
            k=2000.0,
            cohesion=100.0,
            mu=0.5,
            hysteretic_type="Initial",
        )
        self.quad.spring = spring

        collections = MagicMock()
        collections.materials = {self.quad.material_key: MagicMock()}
        state = MagicMock()
        state.step = 1

        x = np.zeros(7)
        self.quad.status.u[6] = 0.02
        self.quad.update_domain(x, state, collections=collections)

        self.assertEqual(spring.dn, 15.0)
        self.assertAlmostEqual(spring._tstrain, 0.02)
        self.assertEqual(self.quad.sigma_initial, 50.0)

    def test_coulomb_takeda_dispatch(self):
        """When hysteretic_type is 'Takeda', quad.update_domain calls set_trial_strain_takeda_diagonal_quad."""
        spring = SpringCoulomb03(
            k=2000.0,
            cohesion=100.0,
            mu=0.5,
            hysteretic_type="Takeda",
        )
        self.quad.spring = spring

        collections = MagicMock()
        collections.materials = {self.quad.material_key: MagicMock()}
        state = MagicMock()
        state.step = 1

        x = np.zeros(7)
        self.quad.status.u[6] = 0.02
        self.quad.update_domain(x, state, collections=collections)

        self.assertAlmostEqual(spring._tstrain, 0.02)
        self.assertEqual(self.quad.sigma_initial, 50.0)

    def test_elastic_spring_dispatch(self):
        """When spring is SpringElastic, quad.update_domain calls standard set_trial_strain."""
        spring = SpringElastic(k=5000.0)
        self.quad.spring = spring

        state = MagicMock()
        x = np.zeros(7)
        self.quad.status.u[6] = 0.01
        self.quad.update_domain(x, state)

        self.assertAlmostEqual(spring.get_force(), 50.0)

    def test_quad_initial_compiled_numba_batch(self):
        """Verify compiled Numba _evaluate_quad_takeda_batch evaluates Initial Quad springs at full speed."""
        from histra.solver.hysteretic_batch import (
            _evaluate_quad_takeda_batch,
            QUAD_PARAM_SIZE,
            QUAD_STATE_SIZE,
            QUAD_HYSTERETIC_INITIAL,
            QPHYSTERETIC_TYPE,
            QPENABLED,
            QPK,
            QPCOHESION,
            QPMU,
            QPE1P,
            QPE2P,
            QPH,
            QTSTRESS,
            QKTANG,
            QTPHASE,
        )
        params = np.zeros((1, QUAD_PARAM_SIZE), dtype=np.float64)
        state = np.zeros((1, QUAD_STATE_SIZE), dtype=np.float64)

        params[0, QPENABLED] = 1.0
        params[0, QPK] = 2000.0
        params[0, QPCOHESION] = 100.0
        params[0, QPMU] = 0.5
        params[0, QPE1P] = 2000.0
        params[0, QPE2P] = 0.0
        params[0, QPHYSTERETIC_TYPE] = QUAD_HYSTERETIC_INITIAL
        params[0, QPH] = 0.0

        strains = np.array([0.02], dtype=np.float64)
        dns = np.array([10.0], dtype=np.float64)
        volumes = np.array([100.0], dtype=np.float64)
        sigma_initial = np.array([0.0], dtype=np.float64)

        _evaluate_quad_takeda_batch(params, state, strains, dns, volumes, sigma_initial)

        # Elastic prediction: k * 0.02 = 40.0 <= cohesion (100.0) -> Elastic, stress = 40.0
        self.assertAlmostEqual(state[0, QTSTRESS], 40.0)
        self.assertAlmostEqual(state[0, QKTANG], 2000.0)
        self.assertEqual(int(state[0, QTPHASE]), int(PhaseEnum.Elastic))


if __name__ == "__main__":
    unittest.main()
