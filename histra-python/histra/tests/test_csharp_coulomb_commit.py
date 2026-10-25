"""Coulomb commit bookkeeping checked against original C# routines."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.springs.coulomb03 import SpringCoulomb03
from histra.types.phase_enum import PhaseEnum
from histra.solver.hysteretic_kernels import interface_coulomb as ik
from histra.solver.hysteretic_kernels import quad_takeda as qk


class NativeCoulombCommitTests(unittest.TestCase):
    def test_scalar_and_compiled_commits_match_original(self):
        cases = json.loads((Path(__file__).parent / "fixtures/csharp_coulomb_commit_2026_1_1.json").read_text(encoding="utf-8"))["cases"]
        for case in cases:
            with self.subTest(phase=case["phase"], plastic_t=case["plastic_t"], plastic_c=case["plastic_c"]):
                spring = SpringCoulomb03(k=100.)
                spring.tangent_reload_t = 0.0
                spring.tangent_reload_c = 0.0
                spring.t_phase = PhaseEnum(case["phase"])
                spring.k_tang = case["tangent"]
                spring._tplastic_tension_indicator = case["plastic_t"]
                spring._tplastic_compression_indicator = case["plastic_c"]
                spring.commit()
                actual = [int(spring._c_phase_unload_t), int(spring._c_phase_unload_c), int(spring._cplastic_tension_indicator), int(spring._cplastic_compression_indicator), spring.tangent_reload_t, spring.tangent_reload_c]
                np.testing.assert_array_equal(actual, case["expected"])
                for routine in (ik._commit_initial_coulomb_batch, ik._commit_initial_coulomb_batch.py_func):
                    state = np.zeros((1, ik.COULOMB_STATE_SIZE))
                    state[0, ik.CTPHASE] = case["phase"]
                    state[0, ik.CKTANG] = case["tangent"]
                    state[0, ik.CTANGENT_RELOAD_T] = case["initial_reload_tangent"]
                    state[0, ik.CTANGENT_RELOAD_C] = case["initial_reload_tangent"]
                    state[0, ik.CCPLASTIC_T] = case["plastic_t"]
                    state[0, ik.CCPLASTIC_C] = case["plastic_c"]
                    routine(state, np.ones(1, dtype=np.bool_))
                    columns = [ik.CCUNLOAD_T, ik.CCUNLOAD_C, ik.CCPLASTIC_T, ik.CCPLASTIC_C, ik.CTANGENT_RELOAD_T, ik.CTANGENT_RELOAD_C]
                    np.testing.assert_array_equal(state[0, columns], case["expected"])
                for law in (qk.QUAD_HYSTERETIC_INITIAL, qk.QUAD_HYSTERETIC_TAKEDA):
                    params = np.zeros((1, qk.QUAD_PARAM_SIZE))
                    state = np.zeros((1, qk.QUAD_STATE_SIZE))
                    params[0, qk.QPENABLED] = 1.
                    params[0, qk.QPHYSTERETIC_TYPE] = law
                    state[0, qk.QTPHASE] = case["phase"]
                    state[0, qk.QKTANG] = case["tangent"]
                    state[0, qk.QTANG_RELOAD_T] = case["initial_reload_tangent"]
                    state[0, qk.QTANG_RELOAD_C] = case["initial_reload_tangent"]
                    state[0, qk.QTPLAST_T] = case["plastic_t"]
                    state[0, qk.QTPLAST_C] = case["plastic_c"]
                    qk._commit_quad_takeda_batch(params, state)
                    columns = [qk.QCUNLOAD_T, qk.QCUNLOAD_C, qk.QCPLAST_T, qk.QCPLAST_C, qk.QTANG_RELOAD_T, qk.QTANG_RELOAD_C]
                    np.testing.assert_array_equal(state[0, columns], case["expected"])
