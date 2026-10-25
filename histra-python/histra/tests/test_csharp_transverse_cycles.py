"""Original transverse spring construction and 15 cyclic curve combinations."""
import json
from pathlib import Path
import unittest

import numpy as np
from histra.preprocessing.constitutive_laws import HystereticLaw
from histra.preprocessing.spring_factory import (
    _configure_hysteretic, _set_ultimate_displacement, _apply_ultimate_displacement_arrays)
from histra.solver.hysteretic_kernels.transverse import (
    _PARAM_NAMES, TRANSVERSE_PARAM_SIZE, _evaluate_linear_batch)


class NativeTransverseCycleTests(unittest.TestCase):
    def test_construction_scalar_and_compiled_cycles(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_transverse_cycles_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for case in fixture['cases']:
            law = HystereticLaw(**case['law'])
            with self.subTest(tensile=law.tensile_curve, compressive=law.compressive_curve):
                s = _configure_hysteretic(case['k'], case['area'], case['length'], law)
                if 'law2' not in case:
                    ur_t, ur_c = np.array([s.ur[0]]), np.array([s.ur[1]])
                    kt_t, kt_c = np.array([s.kt[0]]), np.array([s.kt[1]])
                    _apply_ultimate_displacement_arrays(
                        law=law, k=np.array([s.k]), area=np.array([s.area]),
                        fy_t=np.array([s.fy[0]]), fy_c=np.array([s.fy[1]]),
                        tensile_linear_softening=np.array([law.tensile_curve == 'LinearSoftening']),
                        tensile_exponential=np.array([law.tensile_curve == 'Exponential']),
                        compressive_linear_softening=np.array([law.compressive_curve == 'LinearSoftening']),
                        compressive_parabolic=np.array([law.compressive_curve == 'Parabolic']),
                        ur_t=ur_t, ur_c=ur_c, kt_t=kt_t, kt_c=kt_c)
                    np.testing.assert_allclose([ur_t[0], ur_c[0]], case['initial']['Ur'], rtol=1e-12, atol=1e-12)
                    np.testing.assert_allclose([kt_t[0], kt_c[0]], case['initial']['Kt'], rtol=1e-12, atol=1e-12)
                second = HystereticLaw(**case['law2']) if 'law2' in case else law
                _set_ultimate_displacement(s, law, second)
                s.initialize()
                for name in ('fy', 'kt', 'ur'):
                    np.testing.assert_allclose(getattr(s, name), case['initial'][name.capitalize()], rtol=1e-12, atol=1e-12)
                params = np.zeros((1, TRANSVERSE_PARAM_SIZE))
                params[0, :len(_PARAM_NAMES)] = [getattr(s, name) for name in _PARAM_NAMES]
                params[0, 32] = float(law.tensile_curve == 'Exponential')
                params[0, 33] = float(law.compressive_curve == 'Parabolic')
                committed = np.zeros((1, 9))
                trial = np.zeros((1, 10))
                trial[0, 9] = s.k_tang
                enabled = np.array([True])
                for step, (strain, expected) in enumerate(zip(case['strains'], case['states'], strict=True)):
                    with self.subTest(step=step):
                        s.u = strain
                        s.set_trial_strain(strain)
                        s.commit()
                        _evaluate_linear_batch(params, committed, trial, np.array([strain]), enabled)
                        self.assertEqual(int(s.phase), expected['Phase'], 'scalar phase')
                        self.assertEqual(int(trial[0, 8]), expected['Phase'], 'compiled phase')
                        reference = [expected['F'], expected['Cstrain'], expected['CenergyD'], *expected['Umax'], expected['K_tang']]
                        scalar = [s.f, s._cstrain, s.cenergy_d, *s.umax, s.k_tang]
                        compiled = trial[0, [6, 7, 4, 0, 1, 9]]
                        np.testing.assert_allclose(scalar, reference, rtol=1e-12, atol=1e-12)
                        np.testing.assert_allclose(compiled, reference, rtol=1e-12, atol=1e-12)
                        committed[:] = trial[:, :9]
