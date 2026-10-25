from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from saved_result_geometry import interface_geometry, fibre_weights
from result_preview import step_resultants


class SavedGeometryTests(unittest.TestCase):
    def fixture(self):
        # Skewed, tapered interface with reversed column direction; centre
        # and origin cannot be inferred from a bounding box or half-length.
        local = np.array([[24, 11], [3, 9], [1, -12], [20, -8]], dtype=float)
        axes = np.array([[.6, 0], [0, 1], [.8, 0]])
        origin = np.array([100, 70, -20])
        g = {'nrow': 9, 'ncol': 9, 'reference_e1': axes[:, 0].tolist(),
             'reference_e3': axes[:, 1].tolist(), 'vint3d': (local @ axes.T + origin).tolist()}
        state = {'trasv_1': [{'di': x, 'ecc': y} for x, y in fibre_weights(9, 9) @ local]}
        return g, state, origin, local

    def test_missing_coordinates_recovered_from_saved_centres(self):
        g, state, origin, local = self.fixture()
        result = interface_geometry(g, state)
        np.testing.assert_allclose(result['reference_origin'], origin, atol=1e-6)
        np.testing.assert_allclose(result['vint2d'], local, atol=1e-6)
        self.assertNotIn('reference_origin', g, 'source geometry remains unchanged')

    def test_inconsistent_saved_geometry_fails_closed(self):
        g, state, _, _ = self.fixture()
        state['trasv_1'][2]['di'] += 1
        with self.assertRaisesRegex(ValueError, 'bilinear'):
            interface_geometry(g, state)
        g, state, _, _ = self.fixture()
        g['vint3d'][0][0] += 1
        with self.assertRaisesRegex(ValueError, 'corners'):
            interface_geometry(g, state)

    def test_array_resultants_keep_key_order_and_both_signs(self):
        s = {'interface_resultant_forces': [[1,-2,3],[4,5,6]], 'interface_bending_moments': [[-4,5,-6],[7,8,9]]}
        self.assertEqual(step_resultants(s, ['1','2']), [[1,-2,3,-4,5,-6],[4,5,6,7,8,9]])
        with self.assertRaisesRegex(ValueError, 'one-based'):
            step_resultants(s, ['1','3'])
        s['interface_bending_moments'].pop()
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            step_resultants(s, ['1','2'])
