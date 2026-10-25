"""Native spring rollback contract from a logged failed C# load attempt.

The solver's full snapshot restoration policy is a separate decision. This
test isolates the original scalar routine so changes do not conflate base U
with trial/committed strain during investigation of that policy.
"""
import json
from pathlib import Path
import unittest

from histra.springs.hysteretic import SpringHysteretic
from histra.types.phase_enum import PhaseEnum


class NativeFailedStepRollbackTests(unittest.TestCase):
    def test_transverse_rollback_matches_original_logged_calls(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'csharp_failed_step_rollback_2026_1_1.json').read_text())
        self.assertGreater(len(fixture['cases']), 0)
        for case in fixture['cases']:
            with self.subTest(identity=case['identity']):
                before = case['before']
                spring = SpringHysteretic()
                spring.u = before['U']
                spring.f = before['F']
                spring.k_tang = before['K_tang']
                spring.phase = PhaseEnum[before['Phase']]
                spring._cstrain = before['Cstrain']
                spring._tstrain = before['Tstrain']
                spring._cstress = before['Cstress']
                spring._tstress = before['Tstress']
                spring.revert_to_last_commit()
                actual = {'U': spring.u, 'F': spring.f, 'K_tang': spring.k_tang,
                          'Phase': spring.phase.name, 'Cstrain': spring._cstrain,
                          'Tstrain': spring._tstrain, 'Cstress': spring._cstress,
                          'Tstress': spring._tstress}
                self.assertEqual(actual, case['after'])
