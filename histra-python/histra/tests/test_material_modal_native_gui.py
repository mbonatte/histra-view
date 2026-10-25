"""Actual GUI references, including native failure and unavailable stages."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from histra import AnalysisSession, load_model
from histra.io.results_reader import ResultsStateError
from histra.solver.model_manager import ModelManager
from histra.solver.interface_material import SpringHistoryResetWarning
from histra.types.umfpack import find_umfpack_library
from tools.benchmarks.build_material_modal_reference_models import (
    CASES, DEFAULT_TEMPLATE, build_material_modal_model,
)
from tools.benchmarks.masonry_spring_fingerprint import fingerprint, python_spring_rows


NATIVE = json.loads((Path(__file__).parent / "fixtures/csharp-material-modal-gui-2026.1.1.json").read_text())


def _session(tmp_path, monkeypatch, case):
    if find_umfpack_library() is None:
        pytest.skip("Original native UMFPACK configuration required")
    monkeypatch.setenv("HISTRA_UMFPACK_ORDERING", "amd")
    monkeypatch.setenv("HISTRA_LINEAR_SOLVER", "umfpack")
    monkeypatch.setenv("HISTRA_LINEAR_SOLVER_PRECISION", "accurate")
    path = tmp_path / f"{case}.hrx"
    build_material_modal_model(DEFAULT_TEMPLATE, case).write(path, encoding="utf-8", xml_declaration=True)
    assert hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == NATIVE["cases"][case]["input_lf_sha256"]
    model = load_model(path)
    ModelManager.prepare_model(model, force=True, use_cache=False)
    return AnalysisSession(model, linear_solver_backend="umfpack", linear_solver_precision="accurate",
                           umfpack_irstep=2, equilibrium_policy="warn", strategy_policy="off")


@pytest.mark.parametrize("case", CASES)
def test_loaded_material_change_every_native_spring_commit_and_return_failure(tmp_path, monkeypatch, case):
    session = _session(tmp_path, monkeypatch, case)
    expected = {(s["analysis"], s["step"]): s["tables"] for s in NATIVE["cases"][case]["states"]}
    reactions = {(s["AnalysisKey"], s["Step"]): s for s in NATIVE["cases"][case]["reaction_history"]}
    trace = NATIVE["cases"][case]["trace"]["analyses"]
    iterations = {(key, s["step"]): s["iterations"] for key, name in ((1, "Vert"), (2, "Cycle_B (1)")) for s in trace[name]}
    checked = set()

    def committed(row, analysis):
        key = analysis.key, row["step"]
        assert key in expected
        assert row["iterations"] == iterations[key]
        springs = python_spring_rows(session.model)
        for table, state in expected[key].items():
            actual = fingerprint([s[0] for s in springs], [[s[1][f] for f in state["fields"]] for s in springs])
            assert actual == {f: state[f] for f in ("rows", "identities", "values")}, (key, table)
        actual_reaction = dict(zip(
            ("R1", "R2", "R3", "Eel", "Ed"),
            (row["reaction_x"], row["reaction_y"], row["reaction_z"], row["elastic_energy"], row["dissipated_energy"]),
            strict=True,
        ))
        for field, value in actual_reaction.items():
            assert value == reactions[key][field], (key, field)
        checked.add(key)

    assert session.run(1, on_step_committed=committed).code == 0
    def change(material):
        if case == CASES[1]:
            with pytest.warns(SpringHistoryResetWarning, match="81 incompatible"):
                report = session.change_interface_materials([4], material, spring_type_change="csharp_reset")
            assert report.spring_type_change == "csharp_reset"
            assert report.reset_spring_count == 81
            assert {r.group for r in report.history_resets} == {"transverse"}
            assert [r.id_local for r in report.history_resets] == list(range(81))
            assert {r.interface_key for r in report.history_resets} == {4}
        else:
            report = session.change_interface_materials([4], material)
            assert report.reset_spring_count == 0

    change(19)
    assert session.run(2, on_step_committed=committed).code == 0
    change(18)
    result = session.run(6, on_step_committed=committed)
    assert result.code == -3
    assert not result.committed_steps
    assert checked == set(expected)
    native_state = NATIVE["cases"][case]["analysis_states"]["6"][0]
    assert native_state["Exit"] == "LargeDisplacement" and native_state["Step"] == "0"


@pytest.mark.parametrize("case,key", [(CASES[0], 3), (CASES[0], 4), (CASES[0], 5), (CASES[1], 3), (CASES[1], 4), (CASES[1], 5)])
def test_native_gui_modal_shapes_and_all_available_modal_values(tmp_path, monkeypatch, case, key):
    session = _session(tmp_path, monkeypatch, case)
    if key in (4, 5):
        assert session.run(1).code == 0
    if key == 5:
        if case == CASES[1]:
            with pytest.warns(SpringHistoryResetWarning):
                session.change_interface_materials([4], 19, spring_type_change="csharp_reset")
        else:
            session.change_interface_materials([4], 19)
        assert session.run(2).code == 0
    result = session.run(key).modal_result
    native = NATIVE["cases"][case]["modal"][str(key)]
    assert result.converged_modes == len(native)
    assert result.requested_modes == 6
    for mode, row in zip(result.modes, native, strict=True):
        actual = mode.as_modal_values_row(analysis_key=key)
        assert row["values"].keys() <= actual.keys()
        for field, value in row["values"].items():
            np.testing.assert_allclose(actual[field], value, rtol=1e-11, atol=1e-12, err_msg=field)
        np.testing.assert_allclose(mode.shape, row["shape"], rtol=1e-10, atol=1e-10)


def test_loaded_cross_law_change_is_explicitly_rejected_and_atomic(tmp_path, monkeypatch):
    # Original DB restart skips mismatched SpringType rows; direct SetSpring
    # would transfer them. Do not silently choose either policy for the user.
    session = _session(tmp_path, monkeypatch, CASES[1])
    assert session.run(1).code == 0
    before = python_spring_rows(session.model)
    with pytest.raises(ResultsStateError, match="different laws"):
        session.change_interface_materials([4], 19)
    assert python_spring_rows(session.model) == before
    assert session.model.collections.interfaces[4].material_key == 0
    assert session.usable
