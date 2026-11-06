import unittest
from unittest.mock import patch
import numpy as np
from bridge_v2 import _saved_strain_available_ids, _saved_strain_fields


class SavedStrainTests(unittest.TestCase):
    def test_missing_normal_strain_never_enables_tensor_fields(self):
        data = {'springs/transverse_strain': np.array([0.0]),
                'springs/transverse_strain_valid': np.array([False]),
                'springs/sliding_strain': np.array([0.0000123]),
                'springs/sliding_strain_valid': np.array([True])}
        ids = _saved_strain_available_ids(data)
        self.assertIn('localStrainInPlane', ids)
        self.assertNotIn('localStrainNormal', ids)
        self.assertNotIn('globalStrainX', ids)
        def fake_projection(proxy, **kwargs):
            value = proxy['springs/sliding_stress'][0]
            return ([{'id': 'localStressInPlane', 'available': True, 'step': 2,
                      'quadCornerValues': [[value] * 4]},
                     {'id': 'globalStressX', 'available': True, 'step': 2,
                      'quadCornerValues': [[0.0] * 4]}], None)
        with patch('bridge_v2._stress_fields', side_effect=fake_projection):
            fields = _saved_strain_fields(data)
        self.assertEqual(fields['localStrainInPlane']['quadCornerValues'][0][0], 0.0000123)
        self.assertNotIn('globalStrainX', fields)

    def test_complete_strains_enable_global_and_principal(self):
        data = {'springs/transverse_strain': np.array([1e-6]),
                'springs/transverse_strain_valid': np.array([True]),
                'springs/sliding_strain': np.array([2e-6]),
                'springs/sliding_strain_valid': np.array([True])}
        ids = _saved_strain_available_ids(data)
        self.assertIn('globalStrainX', ids)
        self.assertIn('principalStrainCompressive', ids)
