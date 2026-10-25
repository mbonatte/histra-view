"""Complete original P-Delta executions, including saved-force cache timing."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from histra import load_model, AnalysisSession
from histra.solver.model_manager import ModelManager
from histra.types.umfpack import find_umfpack_library
from tools.benchmarks.build_pdelta_reference_model import build_pdelta_reference_model
from tools.benchmarks.masonry_spring_fingerprint import fingerprint, python_spring_rows


@pytest.mark.parametrize("mode", ["EachStep", "EachIteration"])
@pytest.mark.parametrize("save", [1, 2])
def test_original_full_pdelta_chain_and_sparse_saving(tmp_path, monkeypatch, mode, save):
    if find_umfpack_library() is None:
        pytest.skip("Original native UMFPACK configuration required")
    monkeypatch.setenv("HISTRA_UMFPACK_ORDERING", "amd")
    fixture = Path(__file__).parent / "fixtures/csharp-pdelta-execution-2026.1.1.json"
    native = json.loads(fixture.read_text())["cases"][f"{mode}-save{save}"]
    path = tmp_path / "wall.hrx"
    build_pdelta_reference_model(mode, save).write(path, encoding="utf-8", xml_declaration=True)
    assert hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == native["input_lf_sha256"]
    expected = {(row["analysis"], row["step"]): row["tables"] for row in native["states"]}
    checked = set()
    model = load_model(path)
    ModelManager.prepare_model(model, force=True, use_cache=False)
    assert model.collections.analyses[2].step_save == save

    def committed(row, analysis):
        key = (analysis.key, row["step"])
        if key not in expected:
            return  # Native StepSave=2 has no ordinary row on odd steps.
        rows = python_spring_rows(model)
        for table, reference in expected[key].items():
            actual = fingerprint([item[0] for item in rows],
                                 [[item[1][field] for field in reference["fields"]] for item in rows])
            assert actual == {field: reference[field] for field in ("rows", "identities", "values")}, (key, table)
        checked.add(key)

    try:
        session = AnalysisSession(model, linear_solver_backend="umfpack", linear_solver_precision="accurate",
                                  umfpack_irstep=2, equilibrium_policy="warn", strategy_policy="off")
        for key in (1, 2):
            result = session.run(key, on_step_committed=committed)
            assert result.code == 0
            assert len(result.committed_steps) == native["committed_steps"][str(key)]
            state = next(row for row in native["native_execution"]["analyses"] if row["key"] == key)
            interval = save if key == 2 else 1
            assert state["step"] == len(result.committed_steps) // interval * interval
        assert checked == set(expected)
        runtime = ModelManager.hysteretic_batch_for(model)
        before = runtime._pdelta_saved_resultants.copy()
        state = runtime.snapshot()
        runtime._pdelta_saved_resultants[:] = 123.0
        runtime.restore(state)
        np.testing.assert_array_equal(runtime._pdelta_saved_resultants, before)
    finally:
        ModelManager.clear_hysteretic_batch()
