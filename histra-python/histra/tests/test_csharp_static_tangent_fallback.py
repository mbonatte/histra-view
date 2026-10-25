"""Original StaticIntegrator.UpdateK fallback on a real assembled one-DOF Quad."""
import json
from pathlib import Path
import unittest

import numpy as np

from histra.elements.quad import Quad
from histra.model.model import Model, Collections
from histra.solver.arc_length import ArcLength
from histra.solver.program import Program
from histra.solver.model_manager import ModelManager
from histra.solver.state_snapshot import SolverStateSnapshot
from histra.springs.hysteretic import SpringHysteretic
from histra.types.afference_entry import AfferenceEntry
from histra.types.linear_system import LinearSystem, LinearSolveError


def doubles(values):
    return np.array([int(v) for v in values],dtype=np.int64).view(np.float64)


class NativeStaticTangentFallbackTests(unittest.TestCase):
    def test_regular_fallback_and_unrecoverable_native_cases(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_static_tangent_fallback_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for case in fixture['cases']:
            with self.subTest(case=case['name']):
                quad = Quad(key=1, length=case['length'], diago=case['diago'],
                            sin=case['sin'], cos=case['cos'],
                            spring=SpringHysteretic(k=case['k'], k_tang=case['tangent']))
                quad.aff = [[] for _ in range(6)] + [[AfferenceEntry(1,1.)]]
                collections = Collections()
                collections.quads = {1:quad}
                model = Model(gdl=1, collections=collections)
                ls = LinearSystem(1, backend='superlu')
                ls.b[:] = doubles(case['b_bits'])
                program = Program(ls=ls, u=np.zeros(1), v=np.zeros(1))
                integrator = ArcLength()
                ModelManager.compute_ktang(model,ls,0.)
                snapshot = SolverStateSnapshot.capture(model,program,ls,integrator)
                if case['status']:
                    with self.assertRaises(LinearSolveError):
                        integrator.update_k(program,model,1.)
                    self.assertNotEqual(program.index_fact_k,0)
                    continue
                from unittest.mock import patch
                with patch.object(ls,'solve',wraps=ls.solve) as native_solve:
                    self.assertEqual(integrator.update_k(program,model,1.),0)
                # The known singular tangent is rejected without an expensive
                # native factorization; only the recovered system is solved.
                self.assertEqual(native_solve.call_count,1)
                np.testing.assert_array_equal(ls.k.toarray().ravel(),doubles(case['matrix_bits']))
                # SuperLU is the portable test backend; native fixtures use
                # UMFPACK. Require exact assembly and near-machine solve parity.
                np.testing.assert_allclose(ls.x,doubles(case['x_bits']),rtol=1e-15,atol=0.)
                np.testing.assert_array_equal(ls.b,doubles(case['b_bits']))
                self.assertEqual(program.index_fact_k,case['status'])
                if case['alpha'] == 0.:
                    self.assertEqual(program.static_tangent_alpha,0.)
                    snapshot.restore()
                    # C# alfa is a Newton-call-local ref parameter, outside
                    # element/integrator trial state and rollback checkpoints.
                    self.assertEqual(program.static_tangent_alpha,0.)
                    quad.spring.k_tang = 6.
                    integrator.update_k(program,model,case['next_alpha'])
                    np.testing.assert_array_equal(ls.k.toarray().ravel(),doubles(case['next_matrix_bits']))
                    np.testing.assert_allclose(ls.x,doubles(case['next_x_bits']),rtol=1e-15,atol=0.)
                    # A later solveCurrentStep receives a fresh by-value alfa.
                    integrator.update_k(program,model,1.)
                    self.assertEqual(program.static_tangent_alpha,case['new_call_alpha'])
                    np.testing.assert_array_equal(ls.k.toarray().ravel(),doubles(case['new_call_matrix_bits']))
                    np.testing.assert_allclose(ls.x,doubles(case['new_call_x_bits']),rtol=1e-15,atol=0.)
                else:
                    self.assertEqual(program.static_tangent_alpha,case['alpha'])

    def test_step_controller_does_not_inherit_newton_local_fallback(self):
        from histra.model.load import Analysis, LoadFunction, LoadFunctionItem, LoadCombination, LoadCombinationItem, LoadCondition
        from histra.solver.load_control import LoadControl
        from histra.solver.model_manager import ModelManager
        from histra.solver.nonlinear_step import _execute_steps
        from histra.types.convergence_test import ConvergenceTest
        from histra.types.point import Point

        collections=Collections()
        analysis=Analysis(key=1,method='StandardNewtonRaphson',master_point=-10,load_combination_key=1)
        collections.load_combinations={1:LoadCombination(key=1,items=[LoadCombinationItem(row_key=1,column_key=1,val=0.)])}
        collections.load_conditions={1:LoadCondition(id=1,action=1)}
        analysis.load_function=LoadFunction(key=1,discr_val=.5,items=[
            LoadFunctionItem(pseudo_time=0.,multiplier=0.),
            LoadFunctionItem(pseudo_time=1.,multiplier=1.)])
        collections.analyses={1:analysis}
        model=Model(gdl=1,collections=collections)
        ls=LinearSystem(1,backend='superlu')
        program=Program(gdl=1,ls=ls,u=np.zeros(1),v=np.zeros(1))
        for name in ('_ptarget','_fext','_pq','_pq_prev'):
            setattr(ModelManager,name,np.zeros(1))
        ModelManager._u_total=program.u
        integrator=LoadControl()
        integrator.state.analysis=analysis
        integrator.u=program.u;integrator.v=program.v;integrator.u_committed=program.u.copy()
        integrator.domain_changed(program,model,1)
        received=[]
        class ConvergedWithLocalFallback:
            the_test=ConvergenceTest()
            the_line_search=None
            def solve_current_step(self,p,ls,model,an,combination,step,alfa):
                received.append(alfa)
                p.static_tangent_alpha=0.
                return 0
        algorithm=ConvergedWithLocalFallback()
        code,rows,*_= _execute_steps(model,analysis,1,p=program,ls=ls,n=1,
            integrator=integrator,algorithm=algorithm,alfa=1.,dof=0,
            diagnostic_writer=None,initial_reaction=Point(),
            equilibrium_reference_load_factor=0.,equilibrium_target_force=np.zeros(3),
            reference=[0.,0.],reference_displacement=0.,equilibrium_policy='warn',
            equilibrium_force_absolute_tolerance=1e-6,equilibrium_force_relative_tolerance=1e-6,
            equilibrium_residual_tolerance=1e-6,on_step_committed=None,
            should_stop_after_commit=None,max_committed_steps=2)
        self.assertEqual(code,0)
        self.assertEqual(received,[1.,1.])
        self.assertEqual([r['load_factor'] for r in rows],[.5,1.])

    def test_exact_column_check_preserves_small_values_and_offdiagonal_rank(self):
        import scipy.sparse as sp
        from histra.solver.sparse_rank import first_exact_zero_column
        cases=[([[0.,1.],[1.,0.]],-1),([[1.,1.],[1.,1.]],-1),
               ([[1e-300,0.],[0.,1.]],-1),([[1.,0.],[0.,0.]],1),
               ([[0.,1.],[0.,2.]],0),([[0.,0.],[0.,0.]],0)]
        for values,expected in cases:
            with self.subTest(matrix=values):
                matrix=sp.csc_matrix(values)
                self.assertEqual(first_exact_zero_column(matrix.indptr,matrix.data),expected)
        # Stored zero entries are not evidence of nonzero column stiffness.
        matrix=sp.csc_matrix(([0.,2.],[0,1],[0,1,2]),shape=(2,2))
        self.assertEqual(first_exact_zero_column(matrix.indptr,matrix.data),0)
