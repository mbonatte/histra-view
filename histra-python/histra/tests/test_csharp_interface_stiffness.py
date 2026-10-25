"""All three native interface stiffness blocks, including uniform tangents."""
import json
from pathlib import Path
import unittest
import numpy as np

from histra.elements.interface import Interface
from histra.model._types import Point
from histra.springs.elastic import SpringElastic
from histra.springs.hysteretic import SpringHysteretic
from histra.solver.assembler import _evaluate_stiffness_terms_batch
from histra.solver.hysteretic_kernels.transverse import _finish_transverse_batch
from histra.solver.hysteretic_kernels.interface_coulomb import (
    CTSTRESS, _assemble_full_interface_forces)


class NativeInterfaceStiffnessTests(unittest.TestCase):
    def test_scalar_and_compiled_blocks(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_interface_stiffness_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for case in fixture['cases']:
            with self.subTest(constrained=case['constrained'], uniform=case['uniform'], alpha=case['alpha']):
                i = Interface(length=case['length'], thickness=case['thickness'], nrow=2, ncol=3, nspring=6,
                              parent_type_element1='Restraint' if case['constrained'] else 'Quad',
                              parent_type_element2='Quad')
                i.vint2d = [Point(x=x, y=y) for x, y in case['vertices']]
                i.trasv_1 = [SpringHysteretic(k=k, k_tang=kt) for k, kt in zip(case['spring_k'], case['spring_kt'])]
                i.slid = [SpringElastic(k=37.219)]
                i.slid_out_plan = [SpringElastic(k=37.219), SpringElastic(k=37.219+.19)]
                i.compute_k(case['alpha'])
                i._ensure_performance_cache()
                for name, field in [('k', 'K'), ('kslid', 'Kslid'), ('kslid_out_plan', 'Kout')]:
                    with self.subTest(path='scalar', block=name):
                        np.testing.assert_array_equal(getattr(i.status, name), case[field])
                terms = np.empty(34)
                trial = np.zeros((6, 10));trial[:, 9] = case['spring_kt']
                ints = lambda v: np.array([v], dtype=np.int32)
                _evaluate_stiffness_terms_batch(
                    terms, case['alpha'], np.empty(0), np.empty(0), np.empty(0, dtype=np.int32), np.empty((0,66)),
                    ints(0), np.array([i.length]), ints(case['constrained']), ints(1), ints(1), ints(1),
                    np.array([i._perf_dist[0]]), np.array([i._perf_dist[1]]), ints(2), ints(3), ints(6), ints(0),
                    np.array([i._perf_sum_di2]), np.array([i._perf_sum_dj2]), np.array([i._perf_sum_didj]),
                    np.array([i._perf_sum_dm]), np.array([i._perf_sum_dm2]), np.array([i._perf_sum_ecc2]),
                    np.array([i._perf_sum_djecc]), np.array([i._perf_sum_diecc]),
                    np.asarray(i._perf_di), np.asarray(i._perf_dj), np.asarray(i._perf_ecc),
                    .5*i.length-np.asarray(i._perf_di), np.asarray(case['spring_k']), trial,
                    ints(0), np.array([37.219]), ints(1), np.array([37.219]),
                    ints(2), np.array([37.219+.19]), np.zeros((3,70)))
                expected = np.concatenate([np.asarray(case[f])[np.triu_indices(n)]
                                           for f, n in [('K',6), ('Kslid',2), ('Kout',4)]])
                with self.subTest(path='compiled'):
                    np.testing.assert_array_equal(terms, expected)
                for spring, force in zip(i.trasv_1, case['transverse_forces']):
                    spring._tstress = force
                for spring, force in zip([*i.slid, *i.slid_out_plan], case['sliding_forces']):
                    spring._tstress = force
                i.set_resisting_force()
                with self.subTest(path='scalar forces'):
                    np.testing.assert_array_equal(i.f, case['local_forces'])
                force_trial = np.zeros((6,10));force_trial[:,6] = case['transverse_forces']
                local_flex = np.zeros((1,6));normals=np.zeros(1);committed_force=np.zeros(1);max_u=np.zeros(1)
                _finish_transverse_batch(
                    force_trial,np.zeros((6,9)),np.asarray(i._perf_di),np.asarray(i._perf_dj),
                    np.asarray(i._perf_ecc),np.array([i.length]),ints(0),ints(6),
                    np.array([case['constrained']]),local_flex,normals,committed_force,max_u)
                coulomb=np.zeros((3,70));coulomb[:,CTSTRESS] = case['sliding_forces']
                full=np.zeros((1,12))
                _assemble_full_interface_forces(
                    local_flex,coulomb,ints(0),ints(1),ints(2),np.array([i._perf_dist]),
                    full,max_u,np.zeros(3))
                with self.subTest(path='compiled forces'):
                    np.testing.assert_array_equal(full[0],case['local_forces'])
