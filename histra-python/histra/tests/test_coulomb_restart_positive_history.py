"""Preserve persisted history that the native restart routine omits.

The native oracle explicitly documents this intentional correction: reopening
a saved model must not silently discard its committed positive-force maximum.
"""
import json
from pathlib import Path
import unittest

from histra.solver.restart import _restore_coulomb
from histra.springs.coulomb03 import SpringCoulomb03


class CoulombRestartPositiveHistoryTests(unittest.TestCase):
    def test_restore_retains_the_saved_native_history(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_coulomb_restart_omission_2026_1_1.json').read_text())
        state = fixture['saved_state']
        for oracle in fixture['native_calls']:
            with self.subTest(initial=oracle['InitialCmomMax']):
                spring = SpringCoulomb03(k=100.0)
                spring._cmom_max = oracle['InitialCmomMax']
                _restore_coulomb(spring, state)
                self.assertEqual(spring._cmom_max, state['CmomMax'])
                self.assertEqual(spring._tmom_max, state['CmomMax'])
                self.assertEqual(spring._cmom_min, state['CmomMin'])
                self.assertEqual(spring.u, state['U'])
                self.assertEqual(spring.f, state['F'])
                self.assertEqual(spring._cstrain, state['U'])
                # This deliberate correction must remain visible rather than
                # silently adopting the lossy native restart behavior.
                self.assertNotEqual(spring._cmom_max, oracle['RestoredCmomMax'])
