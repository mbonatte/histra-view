"""Native masonry SpringHysteretic piecewise backbones, not a test-only law.

SpringMultiLinearPlastic is a different C# class and remains unqualified.
These retain the former monotonic strain cases and add reversals, trial
increments, committed histories and the actual compiled transverse evaluator.
"""
import json
import hashlib
from pathlib import Path

import numpy as np
import pytest

from histra.solver.hysteretic_kernels.transverse import (
    _PARAM_NAMES, TRANSVERSE_PARAM_SIZE, _evaluate_linear_batch,
)
from histra.tests.masonry_native_helpers import assert_native_state, assert_native_trial, masonry_spring
from histra.springs.multilinear import SpringMultiLinear
from tools.benchmarks.masonry_spring_reference_inputs import reference_inputs


FIXTURE = Path(__file__).parent / "fixtures/csharp-masonry-backbone-state-transfer-2026.1.1.json"
NATIVE = json.loads(FIXTURE.read_text(encoding="utf-8-sig"))


def test_original_oracle_inputs_and_script_provenance():
    inputs = (json.dumps(reference_inputs(), indent=2) + "\n").encode()
    assert hashlib.sha256(inputs).hexdigest() == NATIVE["input_lf_sha256"]
    script = Path(__file__).parents[2] / "tools/csharp-diagnostics/Invoke-MasonrySpringStateOracle.ps1"
    assert hashlib.sha256(script.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == NATIVE["oracle_lf_sha256"]


@pytest.mark.parametrize("operation", ["trial", "force", "commit"])
def test_unimplemented_generic_multilinear_cannot_silently_act_linear(operation):
    spring = SpringMultiLinear(k=1000.0, deformations="0;0.01;0.02", forces="0;10;15")
    with pytest.raises(NotImplementedError, match="multilinear plastic"):
        if operation == "trial":
            spring.set_trial_strain(0.015)
        elif operation == "force":
            spring.get_force()
        else:
            spring.commit()


@pytest.mark.parametrize("index", range(3))
def test_native_masonry_multilinear_backbone_and_cyclic_history(index):
    assert NATIVE["inputs"] == reference_inputs()
    case = NATIVE["inputs"]["backbones"][index]
    expected = NATIVE["backbones"][index]
    spring = masonry_spring(case["definition"])
    assert_native_state(spring, expected["initial"])
    params = np.zeros((1, TRANSVERSE_PARAM_SIZE))
    params[0, :len(_PARAM_NAMES)] = [getattr(spring, name) for name in _PARAM_NAMES]
    committed, trial = np.zeros((1, 9)), np.zeros((1, 10))
    trial[0, 9] = spring.k_tang
    for row in expected["history"]:
        strain = row["strain"]
        spring.set_trial_strain(strain)
        assert_native_state(spring, row["trial"])
        _evaluate_linear_batch(params, committed, trial, np.array([strain]), np.array([True]))
        assert_native_trial(trial, row["trial"])
        spring.commit()
        assert_native_state(spring, row["committed"])
        committed[:] = trial[:, :9]
