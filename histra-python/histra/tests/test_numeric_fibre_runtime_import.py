"""All-numeric topologies must import native state without any scalar spring."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from histra.elements.interface import Interface
from histra.solver.hysteretic_runtime import HystereticBatchRuntime
from histra.tests.masonry_native_helpers import assert_native_trial, masonry_spring, numeric_group
from histra.types.point import Point


@pytest.mark.parametrize("restored", [False, True], ids=["virgin", "after-material-reset"])
def test_all_numeric_runtime_import_matches_original_state(restored):
    fixture = Path(__file__).parent / "fixtures/csharp-masonry-backbone-state-transfer-2026.1.1.json"
    data = json.loads(fixture.read_text(encoding="utf-8-sig"))
    case = data["inputs"]["transfers"][1]
    target = masonry_spring(case["targets"][0])
    if restored:
        source = masonry_spring(case["definition"])
        for strain in case["strains"]:
            source.set_trial_strain(strain)
            source.commit()
        group = numeric_group(target)
        group.copy_committed_state_from(numeric_group(source))
        native = data["transfers"][1]["resets"][0]["restored"]
    else:
        case = data["inputs"]["backbones"][0]
        target = masonry_spring(case["definition"])
        group = numeric_group(target)
        native = data["backbones"][0]["initial"]
    interface = Interface(key=1, length=2.0, thickness=[1.0, 1.0], nrow=1, ncol=1, nspring=1)
    interface.vint2d = [Point(0., 0., 0.), Point(2., 0., 0.), Point(2., 1., 0.), Point(0., 1., 0.)]
    interface.trasv_1 = group
    model = SimpleNamespace(gdl=12, collections=SimpleNamespace(interfaces={1: interface}, quads={}, materials={}))
    assert group._cache == {}
    runtime = HystereticBatchRuntime(model)
    assert runtime.is_batch_backed
    assert runtime.unmanaged_interfaces == runtime.unmanaged_quads == ()
    assert_native_trial(runtime.trial, native, include_energy=False)
    assert runtime._transverse_k[0] == target.k
    assert runtime._params[0, 13] == target.e1p  # The new envelope is retained.
    # Force a deterministic failure if the all-numeric importer returns early.
    for name in ("trial", "committed", "_params", "_transverse_k", "targets"):
        getattr(runtime, name).fill(np.nan)
    runtime.enabled.fill(False)
    runtime._read_transverse_objects_bulk([])
    assert_native_trial(runtime.trial, native, include_energy=False)
    assert runtime._transverse_k[0] == target.k
    assert runtime.enabled.tolist() == [True]
    assert np.isfinite(runtime._params).all()
