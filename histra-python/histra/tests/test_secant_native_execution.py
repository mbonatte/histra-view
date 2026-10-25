"""Original StaticNonLinearAnalysis.Execute, including real stiffness switches."""
import hashlib
import json
from pathlib import Path

import pytest

from histra import load_model, AnalysisSession
from histra.solver.model_manager import ModelManager
from histra.solver.newton_raphson import NewtonRaphson
from histra.types.umfpack import find_umfpack_library
from tools.benchmarks.build_secant_reference_model import build_secant_reference_model
from tools.benchmarks.masonry_spring_fingerprint import fingerprint, python_spring_rows


@pytest.mark.parametrize("name", ["current", "initial"])
def test_native_secant_choices_iterations_and_committed_states(tmp_path, monkeypatch, name):
    if find_umfpack_library() is None:
        pytest.skip("Original native UMFPACK configuration required")
    monkeypatch.setenv("HISTRA_UMFPACK_ORDERING", "amd")
    native = json.loads((Path(__file__).parent / "fixtures/csharp-secant-execution-2026.1.1.json").read_text())["cases"][name]
    path = tmp_path / "wall.hrx"
    build_secant_reference_model(native["ratio"]).write(path, encoding="utf-8", xml_declaration=True)
    assert hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == native["input_lf_sha256"]
    expected = {(row["analysis"], row["step"]): row["tables"] for row in native["states"]}
    model = load_model(path)
    ModelManager.prepare_model(model, force=True, use_cache=False)
    choices = []
    iterations = {}
    original = NewtonRaphson.solve_current_step

    def solve(self, p, ls, model, analysis, combination, step, alpha):
        choices.append((analysis.key, step, alpha))
        return original(self, p, ls, model, analysis, combination, step, alpha)

    monkeypatch.setattr(NewtonRaphson, "solve_current_step", solve)

    def committed(row, analysis):
        key = (analysis.key, row["step"])
        iterations[key] = row["iterations"]
        rows = python_spring_rows(model)
        for table, reference in expected[key].items():
            actual = fingerprint([item[0] for item in rows],
                                 [[item[1][field] for field in reference["fields"]] for item in rows])
            assert actual == {field: reference[field] for field in ("rows", "identities", "values")}, (key, table)

    try:
        session = AnalysisSession(model, linear_solver_backend="umfpack", linear_solver_precision="accurate",
                                  umfpack_irstep=2, equilibrium_policy="warn", strategy_policy="off")
        for analysis in (1, 2):
            result = session.run(analysis, on_step_committed=committed)
            assert result.code == 0
            state = next(row for row in native["native_execution"]["analyses"] if row["key"] == analysis)
            assert state["exit"] == "Converged" and len(result.committed_steps) == state["step"]
        assert set(iterations) == set(expected)
        assert choices == [(row["analysis"], row["step"], row["alpha"]) for row in native["calls"]]
        assert iterations == {(row["analysis"], row["step"]): row["iterations"] for row in native["calls"]}
    finally:
        ModelManager.clear_hysteretic_batch()
