"""Zero-friction shear dispatch and cycles from original C# 2026.1.1 routines."""
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

from histra.elements.quad import Quad
from histra.model.masonry_material import MasonryMaterial
from histra.preprocessing.constitutive_laws import HystereticLaw, CoulombLaw, shear_law, diagonal_flex_law
from histra.preprocessing.spring_assignment import _quad_spring
from histra.springs.hysteretic import SpringHysteretic


def doubles(bits):
    return np.array([int(x) for x in np.atleast_1d(bits)], dtype=np.int64).view(np.float64)


def cases():
    path = Path(__file__).parent / 'fixtures/csharp_zero_friction_diagonal_2026_1_1.json'
    return json.loads(path.read_text(encoding='utf-8-sig'))['cases']


def construct(case):
    properties = {k: str(v) for k, v in case['properties'].items()}
    properties.update(CriterioSnervamento='Coulomb', ConstitutiveLawMasonryShear=case['shear_type'])
    material = MasonryMaterial(key=1, properties=properties)
    shear = shear_law(material)
    with patch('histra.preprocessing.constitutive_laws.flex_law', side_effect=lambda m, *, vertical=False: replace(shear, E=321.25 if vertical else 500.)):
        flex = diagonal_flex_law(material)
    g = {k: doubles(v).tolist() for k, v in case['geometry_bits'].items()}
    quad = Quad(key=1, material_key=1, length=g['Length'], diago=g['Diago'], sin=g['Sin'], cos=g['Cos'], thickness=g['thickness'])
    model = SimpleNamespace(collections=SimpleNamespace(materials={1: material}))
    with patch('histra.preprocessing.spring_assignment._cached_diagonal_laws', return_value=(flex, shear)):
        spring = _quad_spring(model, quad)
    return material, quad, spring


class NativeZeroFrictionDiagonalTests(unittest.TestCase):
    def test_original_law_dispatch_construction_and_cycles(self):
        for case in cases():
            with self.subTest(geometry=case['geometry'], law=case['shear_type'], strength=case['properties']['FmHor']):
                material, quad, spring = construct(case)
                law = shear_law(material)
                self.assertIsInstance(law, HystereticLaw)
                self.assertEqual(case['law_type'], 'ConstitutiveLawHysteretic')
                np.testing.assert_array_equal([law.E, law.fy_t, law.fy_c], [doubles(case[k])[0] for k in ('law_E', 'law_Fyt', 'law_Fyc')])
                np.testing.assert_array_equal([law.eps_u_t, law.eps_u_c], doubles(case['law_eps']))
                self.assertIsInstance(spring, SpringHysteretic)
                self.assertEqual(case['initial']['type'], 'SpringHysteretic')
                for attr, native in (('k','K'),('area','Area'),('length','Length'),('fy','Fy'),('ur','Ur'),('kt','Kt'),('alfar','Alfar'),('alfau','Alfau')):
                    np.testing.assert_array_equal(np.atleast_1d(getattr(spring, attr)), doubles(case['initial'][native]), err_msg=attr)
                for frame in case['states']:
                    spring.u = doubles(frame['u'])[0]
                    spring.set_trial_strain(spring.u)
                    spring.commit()
                    self.assertEqual(int(spring.phase), frame['Phase'])
                    np.testing.assert_allclose([spring.get_force(),spring.k_tang,spring.cenergy_d,*spring.umax], [doubles(frame[k])[0] for k in ('F','K_tang','energy')]+doubles(frame['Umax']).tolist(), rtol=1e-12, atol=1e-12)

    def test_only_single_zero_coulomb_friction_selects_hysteretic(self):
        for domain, mu, expected in [('Coulomb',0.,HystereticLaw),('Coulomb',1e-50,HystereticLaw),('Coulomb',1e-20,CoulombLaw),('Cacovic',0.,CoulombLaw),('Linear',0.,CoulombLaw)]:
            with self.subTest(domain=domain, mu=mu):
                material = MasonryMaterial(properties={'CriterioSnervamento':domain,'FrictionRatioShear':str(mu),'Gd':'184','AlfaShearUser':'.8'})
                self.assertIsInstance(shear_law(material), expected)

    def test_compiled_cycles_snapshots_and_disabled_springs(self):
        from histra.model.model import Model, Collections
        from histra.types.afference_entry import AfferenceEntry
        from histra.solver.hysteretic_runtime import HystereticBatchRuntime
        from histra.solver.hysteretic_kernels import quad_takeda as qk
        for case in cases():
            with self.subTest(geometry=case['geometry'], law=case['shear_type'], strength=case['properties']['FmHor']):
                material, quad, spring = construct(case)
                quad.spring = spring
                quad.aff = [[AfferenceEntry(j+1,1.)] for j in range(7)]
                collection = Collections()
                collection.materials, collection.quads = {1:material}, {1:quad}
                runtime = HystereticBatchRuntime(Model(gdl=7, collections=collection))
                self.assertEqual(len(runtime.unmanaged_quads), 0)
                self.assertEqual(runtime.performance_counts()['managed_quad_hysteretic_springs'], 1)
                initial_state = runtime.quad_state.copy()
                for frame in case['states']:
                    u = doubles(frame['u'])[0]
                    qk._evaluate_quad_takeda_batch(runtime.quad_params, runtime.quad_state, np.array([u]), np.array([999.]), runtime._quad_volumes, runtime._quad_sigma_initial)
                    row = runtime.quad_state[0]
                    self.assertEqual(int(row[qk.QTPHASE]), frame['Phase'])
                    np.testing.assert_allclose(row[[qk.QTSTRESS,qk.QKTANG,qk.QTENERGY,qk.QTROT_MAX,qk.QTROT_MIN]], [doubles(frame[k])[0] for k in ('F','K_tang','energy')]+doubles(frame['Umax']).tolist(), rtol=1e-12, atol=1e-12)
                    runtime.commit(sync_objects=True)
                    np.testing.assert_array_equal([spring._cstress, spring._cstrain, spring.cenergy_d], row[[qk.QCSTRESS,qk.QCSTRAIN,qk.QCENERGY]])
                    np.testing.assert_array_equal(spring.fy, doubles(case['initial']['Fy']))
                    saved = runtime.snapshot()
                    expected_quad = runtime.quad_state.copy()
                    runtime.quad_state[:] = 123.
                    runtime.restore(saved)
                    np.testing.assert_array_equal(runtime.quad_state, expected_quad)
                runtime.reset_to_initial_state()
                np.testing.assert_array_equal(runtime.quad_state, initial_state)
                saved = runtime.quad_state.copy()
                runtime.quad_params[0,qk.QPENABLED] = 0.
                qk._evaluate_quad_takeda_batch(runtime.quad_params, runtime.quad_state, np.array([1.]), np.array([999.]), runtime._quad_volumes, runtime._quad_sigma_initial)
                runtime.commit()
                np.testing.assert_array_equal(runtime.quad_state, saved)

    def test_fresh_preparation_rebuild_and_actual_compiled_solve(self):
        from histra.io.hr_loader import load_model
        from histra.solver.model_manager import ModelManager
        from histra.solver import inspect_solver_backend, solve_static_nonlinear
        model = load_model(Path(__file__).resolve().parents[1] / 'model-benchmark' / 'model.hrx')
        self.addCleanup(ModelManager.clear_hysteretic_batch)
        for material in model.collections.materials.values():
            material.properties.update(CriterioSnervamento='Coulomb', FrictionRatioShear='0', ShearUltimateStrain='.015')
        ModelManager.prepare_model(model, force=True)
        for _ in range(2):
            report = inspect_solver_backend(model)
            report.require_compiled()
            self.assertEqual(report.managed_quad_hysteretic_springs, len(model.collections.quads))
            self.assertTrue(all(isinstance(q.spring, SpringHysteretic) for q in model.collections.quads.values()))
            ModelManager.prepare_hysteretic_batch(model, rebuild=True)
        code, _ = solve_static_nonlinear(model, model.collections.analyses[1], max_committed_steps=1, linear_solver_backend='superlu', performance_policy='compiled', equilibrium_policy='off')
        self.assertEqual(code, 0)
        inspect_solver_backend(model).require_compiled()
        from histra.solver.session import AnalysisSession
        from histra.solver.hysteretic_kernels import quad_takeda as qk
        runtime = ModelManager.prepare_hysteretic_batch(model)
        strains = np.zeros(len(runtime.quad_records))
        strains[0] = 1.2 * runtime.quad_records[0].spring.fy[0] / runtime.quad_records[0].spring.k
        qk._evaluate_quad_takeda_batch(runtime.quad_params, runtime.quad_state, strains, np.zeros_like(strains), runtime._quad_volumes, runtime._quad_sigma_initial)
        runtime.commit(sync_objects=True)
        before = runtime.quad_state.copy()
        session = AnalysisSession(model)
        interface = next(iter(model.collections.interfaces.values()))
        session.change_interface_materials([interface.key], next(iter(model.collections.materials)), preserve_committed_state=False)
        updated = ModelManager.prepare_hysteretic_batch(model, rebuild=True)
        np.testing.assert_array_equal(updated.quad_state, before)
        inspect_solver_backend(model).require_compiled()

    def test_native_failed_trial_revert_in_scalar_and_compiled_paths(self):
        from histra.model.model import Model, Collections
        from histra.types.afference_entry import AfferenceEntry
        from histra.solver.hysteretic_runtime import HystereticBatchRuntime
        from histra.solver.hysteretic_kernels import quad_takeda as qk
        for case in cases():
            with self.subTest(geometry=case['geometry'], law=case['shear_type'], strength=case['properties']['FmHor']):
                material, quad, spring = construct(case)
                quad.spring = spring
                quad.aff = [[AfferenceEntry(j+1,1.)] for j in range(7)]
                collection = Collections()
                collection.materials, collection.quads = {1:material}, {1:quad}
                runtime = HystereticBatchRuntime(Model(gdl=7, collections=collection))
                expected = case['rollback']
                for key in ('accepted', 'failed'):
                    u = doubles(expected[key])[0]
                    qk._evaluate_quad_takeda_batch(runtime.quad_params, runtime.quad_state, np.array([u]), np.zeros(1), runtime._quad_volumes, runtime._quad_sigma_initial)
                    if key == 'accepted': runtime.commit()
                runtime.revert_quad(quad)
                np.testing.assert_allclose([spring.get_force(), spring.k_tang, spring._cstrain, spring._tstrain], [doubles(expected[k])[0] for k in ('F','K_tang','Cstrain','Tstrain')], rtol=1e-12, atol=1e-12)
                self.assertEqual(int(spring.phase), expected['Phase'])
                self.assertEqual(int(spring.t_phase), expected['TPhase'])
                _, _, scalar = construct(case)
                for key in ('accepted', 'failed'):
                    scalar.u = doubles(expected[key])[0]
                    scalar.set_trial_strain(scalar.u)
                    if key == 'accepted': scalar.commit()
                scalar.revert_to_last_commit()
                np.testing.assert_allclose([scalar.get_force(),scalar.k_tang,scalar._cstrain,scalar._tstrain], [doubles(expected[k])[0] for k in ('F','K_tang','Cstrain','Tstrain')], rtol=1e-12, atol=1e-12)
                self.assertEqual(int(scalar.t_phase), expected['TPhase'])
