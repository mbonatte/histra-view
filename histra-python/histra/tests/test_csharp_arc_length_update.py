"""Binary outputs of the installed C# ArcLength.Update, not a formula replica."""
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from histra.solver.arc_length import ArcLength


class NativeArcLengthUpdateTests(unittest.TestCase):
    def _run(self, case, mode="csharp"):
        class System:
            matrix_version = 1
            x = np.array([case["bar"]])

            def solve(self, rhs):
                self.x = rhs.copy()

            def set_x_vector(self, values):
                self.x = values.copy()

        arc = ArcLength(constraint_mode=mode)
        arc._alpha2 = case["alpha2"]
        arc._phat = np.array([case["hat"]])
        arc._delta_u_step = np.array([case["step"]])
        arc._dofs = np.array([0])
        arc.u = np.zeros(1)
        arc.state.combination = 1
        arc.update_ptarget = lambda *args: None
        arc.apply_load_domain = lambda *args: None
        with patch("histra.solver.arc_length.ModelManager.update_domain"):
            self.assertEqual(arc.update(object(), SimpleNamespace(ls=System()), object()), case.get("code", 0))
        return arc

    def test_original_update_binary_outputs(self):
        fixture = Path(__file__).with_name("fixtures") / "csharp_arc_length_update_2026_1_1.json"
        for case in json.loads(fixture.read_text(encoding="utf-8-sig"))["cases"]:
            with self.subTest(case=case):
                arc = self._run(case)
                if case["code"] < 0:
                    self.assertTrue(arc.errors)
                    self.assertEqual(arc._delta_lambda_step, 0.0)
                    self.assertEqual(arc.u[0], 0.0)
                    continue
                for value, key in ((arc._last_delta_lambda, "lambda_bits"), (arc._last_delta_u[0], "du_bits")):
                    self.assertEqual(struct.unpack("<q", struct.pack("<d", value))[0], int(case[key]))

    def test_stable_shortcut_is_explicit(self):
        case = dict(alpha2=0.0, hat=1.1, bar=0.3, step=0.01)
        source = self._run(case)
        stable = self._run(case, "stable")
        self.assertEqual(stable._last_delta_lambda, -case["bar"] / case["hat"])
        self.assertNotEqual(source._last_delta_lambda, stable._last_delta_lambda)

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            ArcLength(constraint_mode="unknown")
