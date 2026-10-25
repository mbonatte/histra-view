"""Bitwise parity tests for Arc-Length Crisfield constraint update.

Compares root selection, delta_lambda, and incremental displacement delta_u
between authoritative C# HiStrA ArcLength and Python ArcLength with exact
IEEE-754 bit representations.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from histra.solver.arc_length import ArcLength

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "csharp_arc_length_update_2026_1_1.json"


class MockLinearSystem:
    def __init__(self, val: float):
        self.matrix_version = 1
        self.x = np.array([val], dtype=np.float64)

    def solve(self, rhs):
        self.x = rhs.copy()

    def set_x_vector(self, values):
        self.x = values.copy()


def _run_python_arc_length(case: dict) -> tuple[int, ArcLength]:
    arc = ArcLength(constraint_mode="csharp")
    arc._alpha2 = float(case["alpha2"])
    arc._phat = np.array([float(case["hat"])], dtype=np.float64)
    arc._delta_u_step = np.array([float(case["step"])], dtype=np.float64)
    arc._dofs = np.array([0])
    arc.u = np.zeros(1, dtype=np.float64)
    arc.state.combination = 1
    arc.update_ptarget = lambda *args: None
    arc.apply_load_domain = lambda *args: None

    with patch("histra.solver.arc_length.ModelManager.update_domain"):
        code = arc.update(object(), SimpleNamespace(ls=MockLinearSystem(float(case["bar"]))), object())
    return code, arc


def test_csharp_arc_length_fixture_cases():
    """Verify all authoritative ArcLength update cases against C# bit representations."""
    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8-sig"))["cases"]

    for i, case in enumerate(cases):
        py_code, arc = _run_python_arc_length(case)

        # Verification of return code
        assert py_code == case["code"], f"Case {i} return code mismatch: py={py_code}, cs={case['code']}"

        if case["code"] < 0:
            assert arc.errors
            assert arc._delta_lambda_step == 0.0
            assert arc.u[0] == 0.0
        else:
            py_lambda_bits = int(np.asarray([arc._last_delta_lambda], dtype=np.float64).view(np.int64)[0])
            cs_lambda_bits = int(case["lambda_bits"])
            assert py_lambda_bits == cs_lambda_bits, f"Case {i} lambda_bits mismatch: py={py_lambda_bits}, cs={cs_lambda_bits}"

            py_du_bits = int(np.asarray([arc._last_delta_u[0]], dtype=np.float64).view(np.int64)[0])
            cs_du_bits = int(case["du_bits"])
            assert py_du_bits == cs_du_bits, f"Case {i} du_bits mismatch: py={py_du_bits}, cs={cs_du_bits}"


@pytest.mark.parametrize(
    ("alpha2", "hat", "bar", "step", "expected_code", "expected_lambda_bits", "expected_du_bits"),
    [
        (0.0, 2.0, 0.5, 0.02, 0, -4625196817309499397, 4374121138083594240),
        (1.0, 1.5, -0.2, 0.05, 0, 4593971859893063953, 0),
        (0.5, 3.0, 1.2, -0.01, 0, 4600877379321698714, 4612586738352862004),
    ],
)
def test_csharp_arc_length_dynamic_cases(
    alpha2: float,
    hat: float,
    bar: float,
    step: float,
    expected_code: int,
    expected_lambda_bits: int,
    expected_du_bits: int,
):
    """Verify synthesized parameter states against authoritative C# bit values."""
    case = {"alpha2": alpha2, "hat": hat, "bar": bar, "step": step}
    references = json.loads(FIXTURE_PATH.read_text(encoding="utf-8-sig"))["cases"]
    native = next(row for row in references if all(row[key] == value for key, value in case.items()))
    assert (expected_code, expected_lambda_bits, expected_du_bits) == (
        native["code"], int(native["lambda_bits"]), int(native["du_bits"]))
    py_code, arc = _run_python_arc_length(case)

    assert py_code == expected_code
    if py_code == 0:
        py_lambda_bits = int(np.asarray([arc._last_delta_lambda], dtype=np.float64).view(np.int64)[0])
        assert py_lambda_bits == expected_lambda_bits

        py_du_bits = int(np.asarray([arc._last_delta_u[0]], dtype=np.float64).view(np.int64)[0])
        assert py_du_bits == expected_du_bits
