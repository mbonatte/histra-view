import unittest
import numpy as np
from histra_results import _project_full_dof_modes
from solver_api import start_job

class LateralSubgradeIntegrationTests(unittest.TestCase):
    def test_extra_restraint_dofs_are_ignored_only_for_vertex_projection(self):
        args = (np.array([1, 2, 3, 4]),
                np.array([[0, 0, 0], [1, 0, 0], [1, 0, 1], [0, 0, 1]]),
                np.array([1]), np.array([[1, 2, 3, 4]]),
                {'quads': [{'key': '1'}]}, [{'number': 1, 'frequency': 2}])
        original = _project_full_dof_modes(np.array([[1, 0, 0, 0, 0, 0, 0]]), *args)
        with_support = _project_full_dof_modes(np.array([[1, 0, 0, 0, 0, 0, 0, 999]]), *args)
        self.assertTrue(original)
        self.assertEqual(original, with_support)
        self.assertEqual(_project_full_dof_modes(np.array([[1, 0, 0]]), *args), [])

    def test_rejects_invalid_inputs_before_starting_job(self):
        for settings in ({'restraintKeys': [], 'kx': 1, 'ky': 1},
                         {'restraintKeys': [1, 1], 'kx': 1, 'ky': 1},
                         {'restraintKeys': [1], 'kx': -1, 'ky': 1},
                         {'restraintKeys': [1], 'kx': float('nan'), 'ky': 1}):
            with self.assertRaises(ValueError):
                start_job(b'not empty', 'model.hrx', 1, lateral_subgrade=settings)
