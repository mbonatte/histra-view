"""Explicit native history-reset policy and atomic failure handling."""
from types import SimpleNamespace
import warnings

import pytest

from histra import AnalysisSession, load_model
from histra.io.results_reader import ResultsStateError
from histra.solver.backend_api import ConcreteInterfaceMutation, PythonAnalysisRequest, run_python_solver_job
from histra.solver.interface_material import SpringHistoryResetWarning, _transfer_groups
from histra.solver.model_manager import ModelManager
from histra.solver.restart import capture_committed_spring_state
from histra.springs.coulomb03 import SpringCoulomb03
from histra.springs.elastic import SpringElastic
from tools.benchmarks.build_material_modal_reference_models import CASES, DEFAULT_TEMPLATE, build_material_modal_model
from tools.benchmarks.masonry_spring_fingerprint import python_spring_rows


def _model_path(tmp_path):
    path = tmp_path / "wall.hrx"
    build_material_modal_model(DEFAULT_TEMPLATE, CASES[1]).write(path)
    return path


def _loaded_session(tmp_path):
    model = load_model(_model_path(tmp_path))
    ModelManager.prepare_model(model, force=True, use_cache=False)
    session = AnalysisSession(model, linear_solver_backend="superlu", strategy_policy="off")
    assert session.run(1).code == 0
    return session


@pytest.mark.parametrize("group,label", [("trasv_1", "transverse"), ("slid", "in-plane"), ("slid_out_plan", "out-of-plane")])
def test_all_spring_groups_guard_type_changes_and_reset_only_with_opt_in(group, label):
    source = SpringElastic(k=17.0, k_tang=17.0)
    source.set_trial_strain(0.03)
    source.commit()
    target = SpringCoulomb03(k=42.0)
    target.revert_to_start()
    old = SimpleNamespace(key=9, trasv_1=[], slid=[], slid_out_plan=[])
    new = SimpleNamespace(key=9, trasv_1=[], slid=[], slid_out_plan=[])
    setattr(old, group, [source])
    setattr(new, group, [target])
    virgin = capture_committed_spring_state(target)
    with pytest.raises(ResultsStateError, match="spring_type_change='csharp_reset'"):
        _transfer_groups(old, new, "reject")
    resets = _transfer_groups(old, new, "csharp_reset")
    assert capture_committed_spring_state(target) == virgin
    assert len(resets) == 1
    assert (resets[0].interface_key, resets[0].group, resets[0].id_local) == (9, label, 0)
    assert (resets[0].source_law, resets[0].target_law) == ("SpringElastic", "SpringCoulomb03")


@pytest.mark.parametrize("failure", ["warning_as_error", "backend_validation"])
def test_failed_compatibility_reset_restores_predecessor_and_quad_links(tmp_path, monkeypatch, failure):
    session = _loaded_session(tmp_path)
    before = python_spring_rows(session.model)
    links = [[list(edge) for edge in q.interface_keys] for q in session.model.collections.quads.values()]
    if failure == "backend_validation":
        def reject_backend(*args, **kwargs):
            raise RuntimeError("backend validation failed")
        monkeypatch.setattr("histra.solver.backend_coverage.inspect_solver_backend", reject_backend)
    with warnings.catch_warnings():
        warnings.simplefilter("error" if failure == "warning_as_error" else "ignore", SpringHistoryResetWarning)
        error = SpringHistoryResetWarning if failure == "warning_as_error" else RuntimeError
        with pytest.raises(error):
            session.change_interface_materials([4], 19, spring_type_change="csharp_reset")
    assert python_spring_rows(session.model) == before
    assert [[list(edge) for edge in q.interface_keys] for q in session.model.collections.quads.values()] == links
    assert session.model.collections.interfaces[4].material_key == 0
    assert not session.mutations
    assert session.current_analysis_key == 1 and session.usable


def test_no_op_and_invalid_policy_are_explicit(tmp_path):
    session = _loaded_session(tmp_path)
    report = session.change_interface_materials([], 19, spring_type_change="csharp_reset")
    assert report.spring_type_change == "csharp_reset" and not report.history_resets
    with pytest.raises(ValueError, match="spring_type_change"):
        session.change_interface_materials([], 19, spring_type_change="guess")
    with pytest.raises(ValueError, match="spring_type_change"):
        session.change_interface_materials([4], 19, spring_type_change="guess")
    assert session.model.collections.interfaces[4].material_key == 0


def test_compatibility_option_preserves_same_law_fibres_without_warning(tmp_path):
    session = _loaded_session(tmp_path)
    before = python_spring_rows(session.model)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report = session.change_interface_materials([4], 18, spring_type_change="csharp_reset")
    assert not caught
    assert not report.history_resets and report.preserve_committed_state
    # Exact complete-chain native tests cover the other spring families;
    # this portable check targets the transverse-law policy boundary.
    assert [s for s in python_spring_rows(session.model) if s[1]["SpringType"] == 8] == [s for s in before if s[1]["SpringType"] == 8]
    session.backend_coverage.require_compiled()


@pytest.mark.parametrize("policy", ["reject", "csharp_reset"])
def test_backend_job_exposes_the_policy_and_reset_report(tmp_path, policy):
    mutation = ConcreteInterfaceMutation((4,), 19, spring_type_change=policy)
    request = PythonAnalysisRequest("Cycle_B", None, 60.0)
    if policy == "reject":
        with pytest.raises(ResultsStateError, match="different laws"):
            run_python_solver_job(_model_path(tmp_path), [request], timeout_seconds=60,
                                  interface_mutations={"Cycle_B": mutation}, strategy_policy="off", equilibrium_policy="warn")
        return
    with pytest.warns(SpringHistoryResetWarning):
        result = run_python_solver_job(_model_path(tmp_path), [request], timeout_seconds=60,
                                      interface_mutations={"Cycle_B": mutation}, strategy_policy="off", equilibrium_policy="warn")
    report = result.analyses["Cycle_B"].mutation
    assert report.spring_type_change == "csharp_reset" and report.reset_spring_count == 81
    assert any("spring_type_change=csharp_reset" in line and "reset spring histories=81" in line for line in result.logs)
