"""2026.1.1 CTest* contracts, including observable reference quirks."""
import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from histra.types.convergence_test import ConvergenceTest
from histra.types.linear_system import LinearSystem


class TestCSharpConvergenceContracts(unittest.TestCase):
    def setUp(self):
        self.system = LinearSystem(1, backend="superlu")
        self.program = SimpleNamespace(max_u=0.0)
        self.model = SimpleNamespace()
        self.find_max_u = patch("histra.solver.model_manager.ModelManager.find_max_u")
        self.find_max_u.start()
        self.addCleanup(self.find_max_u.stop)

    def test_relative_force_first_iteration_uses_initial_reference_one(self):
        test = ConvergenceTest(tolerance=0.5, criterion="ForceMoment", absolute=False)
        test.start()
        self.system.b[:] = 4.0
        self.assertEqual(test.test(self.program, self.model, self.system), -1)
        self.assertEqual(test.get_error(), 4.0)
        self.system.b[:] = 1.0
        self.assertEqual(test.test(self.program, self.model, self.system), 2)
        self.assertEqual(test.get_error(), 0.25)

    def test_zero_reference_retains_ieee_nan_and_iteration_limit(self):
        test = ConvergenceTest(tolerance=-1.0, max_iter=2, absolute=False)
        test.start()
        self.assertEqual(test.test(self.program, self.model, self.system), -1)
        self.assertEqual(test.test(self.program, self.model, self.system), -2)
        self.assertTrue(math.isnan(test.get_error()))

    def test_displacement_and_work_ignore_relative_flag_like_csharp(self):
        self.system.x[:] = 4.0
        self.system.b[:] = 3.0
        for criterion, expected in (("DispRotation",4.0),("Work",6.0)):
            with self.subTest(criterion=criterion):
                test=ConvergenceTest(tolerance=0.5,criterion=criterion,absolute=False)
                test.start()
                self.assertEqual(test.test(self.program,self.model,self.system),-1)
                self.assertEqual(test.get_error(),expected)

    def test_force_copy_reproduces_csharp_displacement_constructor(self):
        original=ConvergenceTest(tolerance=0.5,max_iter=10,max_u=99,norm_type=1,absolute=False)
        original.current_iter=7
        copied=original.get_copy(3)
        self.assertEqual((copied.criterion,copied.max_u,copied.norm_type),("DispRotation",1.0,2))
        self.assertEqual((copied.max_iter,copied.current_iter),(3,0))
        self.assertTrue(copied.absolute)
        copied.start()
        self.system.x[:] = 0.25
        self.system.b[:] = 100.0
        self.assertEqual(copied.test(self.program,self.model,self.system),1)

    def test_other_copy_constructors_preserve_their_csharp_fields(self):
        for criterion,norm in (("DispRotation",1),("Work",2)):
            with self.subTest(criterion=criterion):
                copied=ConvergenceTest(tolerance=0.3,max_u=7,norm_type=1,criterion=criterion).get_copy(4)
                self.assertEqual((copied.criterion,copied.max_u,copied.norm_type),(criterion,7,norm))
                self.assertEqual((copied.tolerance,copied.max_iter),(0.3,4))

    def test_csharp_precedence_convergence_then_iterations_then_displacement(self):
        test=ConvergenceTest(tolerance=0.5,max_iter=1,max_u=2)
        self.program.max_u=3.0
        test.start()
        self.assertEqual(test.test(self.program,self.model,self.system),1)
        test.start()
        self.system.b[:] = 1.0
        self.assertEqual(test.test(self.program,self.model,self.system),-2)
        test.max_iter=2
        test.start()
        self.assertEqual(test.test(self.program,self.model,self.system),-3)
