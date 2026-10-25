"""Original ComputePDeltaLoads and AssemblePdeltaLoad from fresh geometry."""
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from histra import load_model
from histra.solver.model_manager import ModelManager
from tools.benchmarks.build_masonry_reference_models import DEFAULT_TEMPLATE, build_reference_model


@pytest.mark.parametrize("compiled", [True, False], ids=["compiled", "scalar"])
def test_original_pdelta_loads_with_translation_and_seismic_direction(tmp_path, subtests, compiled):
    fixture = Path(__file__).parent / "fixtures/csharp-pdelta-2026.1.1.json"
    cases = json.loads(fixture.read_text(encoding="utf-8-sig"))["cases"]
    path = tmp_path / "wall.hrx"
    build_reference_model(DEFAULT_TEMPLATE, "01_isotropic_reversal").write(path, encoding="utf-8")
    model = load_model(path)
    ModelManager.prepare_model(model, force=True, use_cache=False)
    runtime = ModelManager.prepare_hysteretic_batch(model, rebuild=True)
    assert runtime is not None
    analysis = model.collections.analyses[2]
    for case in cases:
        with subtests.test(seismic=case["is_seismic"], oblique=case["oblique"], translation=case["translation"], forces=case["interface_forces"]):
            analysis.is_seismic = case["is_seismic"]
            runtime._pdelta_line_load_plans.clear()
            runtime._pdelta_plan = None
            for row in case["quads"]:
                quad = model.collections.quads[row["key"]]
                quad.status.u[:] = row["u"]
                index = next(i for i, q in enumerate(runtime.quad_records) if q is quad)
                runtime._quad_local_u[index] = row["u"]
            forces = {row["key"]: np.asarray(row["force"], dtype=np.float32) for row in case["forces"]}
            for row in case["forces"]:
                key = row["key"]
                force = forces[key]
                interface = model.collections.interfaces[key]
                interface.reference_e1, interface.reference_e2, interface.reference_e3 = row["axes"]
                interface.status.forces = tuple(force)
                runtime._pdelta_saved_resultants[runtime._record_by_id[id(interface)]] = force
            if compiled:
                actual = ModelManager.compute_and_assemble_pdelta_load(model, analysis=analysis)
            else:
                # The fixture supplies original Interface.Status.Forces as the
                # input to this routine; resultant construction has its own tests.
                with patch.object(ModelManager, "hysteretic_batch_for", return_value=None):
                    actual = ModelManager.compute_and_assemble_pdelta_load(model, analysis=analysis)
            np.testing.assert_array_equal(actual, case["global"])
    ModelManager.clear_hysteretic_batch()
