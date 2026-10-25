from pathlib import Path
import base64
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from result_preview import project_results, project_contours, project_interface
FOLDER = Path(__file__).resolve().parents[2] / '3D_bridge'
OUTPUT = FOLDER / 'Bridge.json'
HRX = FOLDER / 'Bridge.hrx'


@unittest.skipUnless(OUTPUT.is_file(), 'Legacy Bridge.json bundle not installed (v2 is tested separately)')
class BridgeResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Includes independent final nodal and keyed force/moment comparisons.
        cls.result = project_results(HRX, OUTPUT)

    def test_bridge_history_and_diagnostics_are_preserved(self):
        r = self.result
        self.assertEqual(len(r['mesh']['nodes']), 3216)
        self.assertEqual(len(r['mesh']['quads']), 2520)
        self.assertEqual(len(r['mesh']['thrustPairs']), 3752)
        self.assertEqual(len(r['mesh']['interfaces']), 6762)
        self.assertEqual(r['modal'], [])
        self.assertEqual([(a['name'], len(a['steps'])) for a in r['analyses']], [('Vert', 6), ('Pushover_Span2_Quarter', 56)])
        for a in r['analyses']:
            self.assertEqual(a['interfaceOrder'], list(range(1, 6763)))
            for s in a['steps']:
                self.assertEqual(len(s['displacements']), 3216)
                self.assertIn('quadDisplacements', s)
                self.assertEqual(len(s['interfaceResultants']), 6762)
                self.assertTrue(np.isfinite(s['displacements']).all())

    def test_bridge_contour_recovers_every_interface_without_solver_preparation(self):
        r = project_contours(OUTPUT, 'Pushover_Span2_Quarter')
        self.assertEqual(r['cellCount'], 547722)
        self.assertEqual(len(r['groups']), 6762)
        self.assertEqual(sum(g['restrained'] for g in r['groups']), 112)
        self.assertIn('RuptureTraz', r['phaseNames'])
        positions = np.frombuffer(base64.b64decode(r['positions']), dtype='<f4').reshape(-1, 4, 3)
        self.assertTrue(np.isfinite(positions).all())
        # Original global corners must remain the outer contour corners,
        # including for restrained interfaces with IDs above the old limit.
        actual = np.array([[positions[g['start'], 0],
                            positions[g['start'] + g['ncol'] - 1, 1],
                            positions[g['start'] + g['count'] - 1, 2],
                            positions[g['start'] + g['count'] - g['ncol'], 3]]
                           for g in r['groups']])
        expected = np.array([g['corners'] for g in r['groups']])
        np.testing.assert_allclose(actual, expected, rtol=0, atol=5e-4)
        detail = project_interface(OUTPUT, 'Pushover_Span2_Quarter', 6762)
        group = r['groups'][-1]
        stress = np.frombuffer(base64.b64decode(r['stress']), dtype='<f4')[group['start']:]
        np.testing.assert_allclose(stress, [s['stress'] for s in detail['normal']], rtol=1e-6, atol=1e-7)
        self.assertIn('reference_origin', detail['geometry'])
        self.assertIn('vint2d', detail['geometry'])


