"""Initial current tangent exported from the original full nonlinear solver."""
import json
from pathlib import Path

import numpy as np
import pytest

from histra import load_model
from histra.solver.load_assembly import assemble_load_vector
from histra.solver.model_manager import ModelManager
from histra.solver.nonlinear_setup import _set_initial_state
from histra.types.linear_system import LinearSystem
from tools.benchmarks.build_masonry_reference_models import DEFAULT_TEMPLATE, build_reference_model


@pytest.mark.parametrize("materialize", [False, True], ids=["numeric-fibres", "spring-objects"])
def test_first_native_newton_matrix_preserves_virgin_envelope_tangent(tmp_path, materialize):
    fixture = Path(__file__).parent / "fixtures/csharp-wall-first-newton-2026.1.1.json"
    native = json.loads(fixture.read_text())["arrays"]
    path = tmp_path / "wall.hrx"
    build_reference_model(DEFAULT_TEMPLATE, "01_isotropic_reversal").write(path, encoding="utf-8")
    model = load_model(path)
    try:
        ModelManager.prepare_model(model, force=True, use_cache=False)
        if materialize:
            for interface in model.collections.interfaces.values():
                interface.trasv_1 = list(interface.trasv_1)
        ls = LinearSystem(model.gdl)
        _set_initial_state(model, np.zeros(model.gdl), np.zeros(model.gdl), ls)
        runtime = ModelManager.prepare_hysteretic_batch(model, rebuild=True)
        assert runtime is not None
        assert np.any(runtime.trial[:, 9] != runtime._transverse_k)
        ModelManager.compute_ktang(model, ls, 1.0)
        for name, actual in (("Ap", ls.k.indptr), ("Ai", ls.k.indices), ("Ax", ls.k.data)):
            np.testing.assert_array_equal(actual, native[name], err_msg=name)
        np.testing.assert_array_equal(0.1 * assemble_load_vector(model, 1, 1), native["b"])
        initial_tangent = runtime.trial[:, 9].copy()
        initial = runtime.snapshot()
        runtime.trial[0, 6] = 0.123
        runtime._interface_resultants_valid = False
        # Trial forces cannot implicitly replace C#'s saved-result force cache.
        np.testing.assert_array_equal(runtime._pdelta_saved_resultants, 0.0)
        ModelManager.refresh_saved_interface_forces(model)
        assert np.any(runtime._pdelta_saved_resultants != 0.0)
        runtime.restore(initial)
        np.testing.assert_array_equal(runtime._pdelta_saved_resultants, 0.0)
        assert all(interface.status.forces == (0.0, 0.0, 0.0) for interface in model.collections.interfaces.values())
        runtime.reset_to_initial_state()
        np.testing.assert_array_equal(runtime.trial[:, 9], initial_tangent)
    finally:
        ModelManager.clear_hysteretic_batch()
