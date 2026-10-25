"""Direct original DB restoration versus scalar and numeric material transfer."""
import json
from pathlib import Path

import numpy as np
import pytest

from histra.solver.restart import transfer_committed_spring_state
from histra.tests.masonry_native_helpers import (
    assert_native_state, assert_native_trial, masonry_spring, numeric_group,
)
from histra.solver.hysteretic_kernels.transverse import (
    _PARAM_NAMES, TRANSVERSE_PARAM_SIZE, _evaluate_linear_batch,
)
from histra.solver.hysteretic_topology import _extract_spring_committed, _extract_spring_trial


FIXTURE = Path(__file__).parent / "fixtures/csharp-masonry-backbone-state-transfer-2026.1.1.json"
NATIVE = json.loads(FIXTURE.read_text(encoding="utf-8-sig"))


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("mode", ["scalar", "numeric-fibres", "cached-proxies"])
def test_native_material_transfer_and_continuation(index, mode):
    numeric = mode != "scalar"
    case, expected = NATIVE["inputs"]["transfers"][index], NATIVE["transfers"][index]
    source = masonry_spring(case["definition"])
    for strain in case["strains"]:
        source.set_trial_strain(strain)
        source.commit()
    source.f0 = case.get("f0", 0.0)
    assert_native_state(source, expected["before"])
    group = numeric_group(source, cached=mode == "cached-proxies") if numeric else None
    for definition, reset in zip(case["targets"], expected["resets"], strict=True):
        target = masonry_spring(definition)
        energy = source.cenergy_d
        if numeric:
            target_group = numeric_group(target)
            target_group.copy_committed_state_from(group)
            group, target = target_group, target_group[0]
        else:
            transfer_committed_spring_state(source, target)
        assert target.cenergy_d == energy  # Deliberate lossless Python history policy.
        assert_native_state(target, reset["restored"], include_energy=False)
        params = np.zeros((1, TRANSVERSE_PARAM_SIZE))
        params[0, :len(_PARAM_NAMES)] = [getattr(target, name) for name in _PARAM_NAMES]
        committed = np.array([_extract_spring_committed(target)])
        trial = np.array([_extract_spring_trial(target)])
        for row in reset["history"]:
            strain = row["strain"]
            target.set_trial_strain(strain)
            assert_native_state(target, row["trial"], include_energy=False)
            _evaluate_linear_batch(params, committed, trial, np.array([strain]), np.array([True]))
            assert_native_trial(trial, row["trial"], include_energy=False)
            target.commit()
            assert_native_state(target, row["committed"], include_energy=False)
            committed[:] = trial[:, :9]
        if numeric:
            group.sync_from_dense(np.array([_extract_spring_committed(target)]),
                                  np.array([_extract_spring_trial(target)]))
            if mode == "numeric-fibres":
                group._cache.clear()
        source = target
