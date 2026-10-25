"""Runtime-class dispatch and cycles from actual C# spring factory calls."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.preprocessing.constitutive_laws import HystereticLaw
from histra.preprocessing.spring_factory import _configure_hysteretic, _combine_hysteretic, _configure_combined_hysteretic_batch
from histra.springs.elastic import SpringElastic


def law(elastic):
    return HystereticLaw(E=500.,fy_t=.2,fy_c=3.,tensile_curve='Elastic' if elastic else 'LinearSoftening',
        compressive_curve='Elastic' if elastic else 'LinearSoftening',ratio_et_t=0.,ratio_et_c=0.,
        alfa_r_t=1.,alfa_r_c=1.,alfa_u_t=0.,alfa_u_c=0.,G_t=.03,G_c=.05,
        eps_u_t=.04,eps_u_c=.06,law_type='ElastoPlasticDuctilityFixed',is_elastic=elastic)


class NativeElasticTransverseTests(unittest.TestCase):
    def test_original_factory_and_committed_cycles(self):
        data=json.loads((Path(__file__).parent/'fixtures/csharp_elastic_transverse_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for case in data['cases']:
            for batched in (False,True):
                if batched and case['restrained']:
                    continue
                with self.subTest(case=case['initial']['type'],restrained=case['restrained'],batched=batched,elastic1=case['elastic1']):
                    l1,l2=law(case['elastic1']),law(case['elastic2'])
                    if batched:
                        spring=_configure_combined_hysteretic_batch(np.array([[80.,4.,.8]]),l1,np.array([[120.,9.,1.1]]),l2,interface_key=7)[0]
                    else:
                        a=SpringElastic(k=-1.,area=4.) if case['restrained'] else _configure_hysteretic(80.,4.,.8,l1)
                        b=_configure_hysteretic(120.,9.,1.1,l2)
                        spring=_combine_hysteretic(a,b,case['restrained'],l1,l2)
                    self.assertEqual(isinstance(spring,SpringElastic),case['initial']['type']=='SpringLinearElastic')
                    self.assertEqual((spring.k,spring.area,spring.length),(case['initial']['K'],case['initial']['Area'],case['initial']['Length']))
                    from histra.solver.hysteretic_topology import _extract_spring_params, _extract_spring_committed, _extract_spring_trial
                    from histra.solver.hysteretic_kernels.transverse import _evaluate_linear_batch, TRANSVERSE_PARAM_SIZE
                    params = np.zeros((1, TRANSVERSE_PARAM_SIZE))
                    params[0, :32] = _extract_spring_params(spring, False)
                    from histra.solver.hysteretic_topology import _extract_spring_curve_type
                    params[0, 32] = _extract_spring_curve_type(spring)
                    committed = np.array([_extract_spring_committed(spring)])
                    trial = np.array([_extract_spring_trial(spring)])
                    for state in case['states']:
                        spring.set_trial_strain(state['u']);spring.commit()
                        _evaluate_linear_batch(params, committed, trial, np.array([state['u']]), np.array([True]))
                        np.testing.assert_allclose(trial[0, [6, 9]], [state['F'], state['K_tang']], rtol=1e-13, atol=1e-12)
                        self.assertEqual(int(trial[0, 8]), state['Phase'])
                        committed[:] = trial[:, :9]
                        self.assertEqual(spring.phase,state['Phase'])
                        np.testing.assert_allclose([spring.get_force(),spring.k_tang],[state['F'],state['K_tang']],rtol=1e-13,atol=1e-12)

    def test_elastic_preparation_and_material_reset_keep_compiled_coverage(self):
        import copy
        from histra.io.hr_loader import load_model
        from histra.solver.model_manager import ModelManager
        from histra.solver.interface_material import change_interface_materials
        from histra.solver.backend_coverage import inspect_solver_backend
        from histra.preprocessing.constitutive_laws import flex_law
        path = Path(__file__).resolve().parents[1] / 'model-benchmark' / 'model.hrx'
        model = load_model(path)
        self.addCleanup(ModelManager.clear_hysteretic_batch)
        for material in model.collections.materials.values():
            for suffix in ('', 'Vertical'):
                material.properties['TensileCurveType' + suffix] = 'Elastic'
                material.properties['CompressiveCurveType' + suffix] = 'Elastic'
            self.assertTrue(flex_law(material).is_elastic)
        ModelManager.prepare_model(model, force=True)
        for _ in range(2):
            report = inspect_solver_backend(model)
            self.assertEqual(report.unmanaged_interfaces, 0)
            self.assertEqual(report.unmanaged_quads, 0)
            report.require_compiled()
            for interface in model.collections.interfaces.values():
                self.assertTrue(all(isinstance(s, SpringElastic) for s in interface.trasv_1))
            runtime = ModelManager.prepare_hysteretic_batch(model, rebuild=True)
            self.assertFalse(runtime._simple_hysteretic)
            for u in (.001, -.002, .0003, 0.):
                expected = runtime.committed[:, 6] + runtime.trial[:, 9] * (u - runtime.committed[:, 7])
                runtime.targets[:] = u
                runtime.evaluate()
                np.testing.assert_array_equal(runtime.trial[:, 6], expected)
                np.testing.assert_array_equal(runtime.trial[:, 8], 0)
                runtime.commit(sync_objects=True)
                first = runtime.springs[0]
                self.assertEqual(first._cstress, runtime.committed[0, 6])
                self.assertEqual(first._cstrain, runtime.committed[0, 7])
        interface = next(iter(model.collections.interfaces.values()))
        material = copy.deepcopy(next(iter(model.collections.materials.values())))
        material.key = max(model.collections.materials) + 1
        model.collections.materials[material.key] = material
        change_interface_materials(model, [interface.key], material.key, preserve_committed_state=False)
        self.assertTrue(all(isinstance(s, SpringElastic) for s in interface.trasv_1))
        inspect_solver_backend(model).require_compiled()

    def test_nonlinear_to_elastic_material_change_rebuilds_compiled_layout(self):
        import copy
        from histra.io.hr_loader import load_model
        from histra.solver.model_manager import ModelManager
        from histra.solver.session import AnalysisSession
        from histra.solver.backend_coverage import inspect_solver_backend
        model = load_model(Path(__file__).resolve().parents[1] / 'model-benchmark' / 'model.hrx')
        self.addCleanup(ModelManager.clear_hysteretic_batch)
        ModelManager.prepare_model(model, force=True)
        old = ModelManager.prepare_hysteretic_batch(model, rebuild=True)
        session = AnalysisSession(model)
        material = copy.deepcopy(next(iter(model.collections.materials.values())))
        material.key = max(model.collections.materials) + 1
        for suffix in ('', 'Vertical'):
            material.properties['TensileCurveType' + suffix] = 'Elastic'
            material.properties['CompressiveCurveType' + suffix] = 'Elastic'
        model.collections.materials[material.key] = material
        interface = next(iter(model.collections.interfaces.values()))
        session.change_interface_materials([interface.key], material.key, preserve_committed_state=False)
        new = ModelManager.prepare_hysteretic_batch(model)
        self.assertIsNot(new, old)
        self.assertFalse(new._simple_hysteretic)
        self.assertTrue(all(isinstance(s, SpringElastic) for s in interface.trasv_1))
        inspect_solver_backend(model).require_compiled()
