"""Material-reset registration strategies and rollback regressions."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from histra.elements.quad import Quad
from histra.io.hr_loader import load_model
from histra.solver.interface_material import (
    change_interface_materials, InterfaceRegistrationWarning,
)
from histra.solver.model_manager import ModelManager
from histra.solver.session import AnalysisSession


class InterfaceRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.quad = Quad(key=1)
        self.quad.interface_keys = [[7], [], [], [], [], []]
        self.interface = SimpleNamespace(
            key=7, material_key=0, parent_type_element1="Restraint",
            parent_element_key1=2, parent_type_element2="Quad",
            parent_element_key2=1, face1=0, face2=0,
            trasv_1=[], slid=[], slid_out_plan=[],
            status=SimpleNamespace(u=[0.] * 12), f=[0.] * 12,
            _perf_di=None, _perf_dj=None, _perf_ecc=None, _perf_area=None,
            area=lambda: 10., compute_dn=lambda nr: 8.,
        )
        self.model = SimpleNamespace(collections=SimpleNamespace(
            interfaces={7:self.interface}, quads={1:self.quad},
            materials={2:object(), 3:object()}, analyses={},
        ))
        self.patcher=patch("histra.solver.interface_material.rebuild_interface_springs", return_value=self.interface)
        self.patcher.start(); self.addCleanup(self.patcher.stop)
        ModelManager.clear_hysteretic_batch()
        self.addCleanup(ModelManager.clear_hysteretic_batch)

    def test_default_appends_current_interface_and_changes_normal_increment(self):
        self.assertEqual(self.quad.compute_dn(self.model.collections,nr=True)[0],4.)
        result=change_interface_materials(self.model,[7],2,preserve_committed_state=False)
        self.assertEqual(result.interface_registration,"csharp")
        self.assertEqual(result.added_quad_links,1)
        self.assertEqual(self.quad.interface_keys[0],[7,7])
        self.assertEqual(self.quad.compute_dn(self.model.collections,nr=True)[0],8.)
        self.assertEqual(len(self.model.collections.interfaces),1)

    def test_single_link_warns_and_keeps_previous_normal_increment(self):
        with self.assertWarns(InterfaceRegistrationWarning):
            result=change_interface_materials(self.model,[7],2,preserve_committed_state=False,interface_registration="single_link")
        self.assertEqual(result.added_quad_links,0)
        self.assertEqual(self.quad.interface_keys[0],[7])
        self.assertEqual(self.quad.compute_dn(self.model.collections,nr=True)[0],4.)

    def test_each_reset_appends_even_when_material_key_is_unchanged(self):
        for material in (2,3,3):
            change_interface_materials(self.model,[7,7],material,preserve_committed_state=False)
        self.assertEqual(self.quad.interface_keys[0],[7,7,7,7])

    def test_invalid_strategy_is_rejected_without_mutation(self):
        with self.assertRaisesRegex(ValueError,"interface_registration"):
            change_interface_materials(self.model,[7],2,interface_registration="double_everything")
        self.assertEqual(self.interface.material_key,0)
        self.assertEqual(self.quad.interface_keys[0],[7])

    def test_post_mutation_session_failure_restores_quad_links_and_caches(self):
        session=AnalysisSession(self.model)
        with patch("histra.solver.backend_coverage.inspect_solver_backend",side_effect=RuntimeError("coverage failure")):
            with self.assertRaisesRegex(RuntimeError,"coverage failure"):
                session.change_interface_materials([7],2,preserve_committed_state=False)
        self.assertEqual(self.model.collections.interfaces[7].material_key,0)
        self.assertEqual(self.quad.interface_keys[0],[7])
        self.assertIsNone(self.quad._perf_dn_edges)
        self.assertFalse(session.mutations)


class CompiledRegistrationTests(unittest.TestCase):
    def test_material_reset_rebuilds_compiled_edges_without_losing_committed_state(self):
        from histra.solver.backend_coverage import inspect_solver_backend
        path=Path(__file__).resolve().parents[1]/"model-benchmark"/"model.hrx"
        if not path.exists(): self.skipTest("benchmark fixture unavailable")
        model=load_model(path); ModelManager.prepare_model(model,force=True)
        self.addCleanup(ModelManager.clear_hysteretic_batch)
        old=ModelManager.prepare_hysteretic_batch(model)
        self.assertIsNotNone(old)
        interface=next(i for i in model.collections.interfaces.values() if i.parent_type_element1=="Restraint")
        # Authoritative arrays differ from their stale object mirrors.
        old._local_u[:]=0.001
        old._quad_local_u[:]=0.002
        from histra.solver.hysteretic_runtime import _prepare_quad_kinematics
        def diagonal_increment(runtime):
            runtime._normal_increments[:]=0.
            index=next(j for j,r in enumerate(runtime.records) if r.interface.key==interface.key)
            runtime._normal_increments[index]=8.
            runtime._prepare_test_du = np.zeros_like(runtime._quad_local_du)
            _prepare_quad_kinematics(
                runtime._prepare_test_du, runtime._quad_local_u,
                runtime._quad_edge_offsets, runtime._quad_edge_records,
                runtime._quad_edge_areas, runtime._normal_increments,
                runtime._committed_forces, runtime._quad_d_alfa,
                2, runtime._quad_sigma_initial, runtime._quad_strains,
                runtime._quad_dns, runtime.quad_params,
            )
            qindex=next(j for j,q in enumerate(runtime.quad_records) if q.key==interface.parent_element_key2)
            return runtime._quad_dns[qindex]
        self.assertEqual(diagonal_increment(old),4.)
        expected_state=old.quad_state.copy()
        expected_edges=len(old._quad_edge_records)
        material=next(k for k in model.collections.materials if k!=interface.material_key)
        result=change_interface_materials(model,[interface.key],material,preserve_committed_state=False)
        self.assertEqual(result.added_quad_links,1)
        self.assertIsNone(ModelManager.hysteretic_batch_for(model))
        new=ModelManager.prepare_hysteretic_batch(model)
        self.assertIsNotNone(new)
        self.assertEqual(len(new._quad_edge_records),expected_edges+1)
        np.testing.assert_array_equal(new._quad_local_u,0.002)
        np.testing.assert_array_equal(new._local_u,0.001)
        np.testing.assert_array_equal(new.quad_state,expected_state)
        self.assertEqual(diagonal_increment(new),8.)
        inspect_solver_backend(model).require_compiled()


if __name__=="__main__": unittest.main()
