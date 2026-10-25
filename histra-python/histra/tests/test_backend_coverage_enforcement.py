"""Tests for Gate A: compiled production backend enforcement and zero-unmanaged reporting."""
from __future__ import annotations

from pathlib import Path

import pytest

from histra.io.hr_loader import load_model
from histra.solver import (
    AnalysisSession,
    CompiledBackendError,
    CompiledBackendRequiredError,
    SolverBackendCoverageReport,
    SuboptimalSolverStrategyWarning,
    UnsafeEquilibriumWarning,
    UnmanagedSolverObjectError,
    inspect_solver_backend,
    run_python_solver_job,
    solve_static_nonlinear,
    ModelManager,
)
from histra.solver.backend_api import PythonAnalysisRequest

MODEL_LIVE = Path(__file__).resolve().parents[1] / "model-live" / "model.hrx"
MODEL_BENCHMARK = Path(__file__).resolve().parents[1] / "model-benchmark" / "model.hrx"


def test_inspect_solver_backend_reports_complete_coverage(monkeypatch) -> None:
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    model = load_model(MODEL_LIVE)
    report = inspect_solver_backend(model)

    assert isinstance(report, SolverBackendCoverageReport)
    assert report.numba_available is True
    assert report.is_compiled_ready is True
    assert report.total_interfaces > 0
    assert report.unmanaged_interfaces == 0
    assert report.total_quads > 0
    assert report.unmanaged_quads == 0
    assert not report.interface_rejection_reasons
    assert not report.interface_coulomb_rejection_reasons
    assert not report.quad_rejection_reasons

    # require_compiled() must pass without raising
    report.require_compiled()


def test_backend_preflight_uses_requested_analysis_and_actual_sparse_backend(
    monkeypatch,
) -> None:
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    model = load_model(MODEL_LIVE)

    report = inspect_solver_backend(
        model, ["Vert"], linear_solver_backend="superlu"
    )

    assert report.requested_linear_solver_backend == "superlu"
    assert report.linear_solver_backend == "superlu"
    assert report.linear_solver_available is True
    assert report.analysis_names == ("1:Vert",)
    assert not report.analysis_resolution_errors
    report.require_compiled()


def test_backend_preflight_rejects_unknown_analysis_selector(monkeypatch) -> None:
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    model = load_model(MODEL_LIVE)

    report = inspect_solver_backend(model, ["does-not-exist"])

    assert report.analysis_names == ()
    assert report.analysis_resolution_errors == (
        "unknown analysis selector 'does-not-exist'",
    )
    assert report.is_compiled_ready is False
    with pytest.raises(CompiledBackendRequiredError, match="unknown analysis selector"):
        report.require_compiled()


def test_backend_preflight_rejects_unavailable_requested_umfpack(monkeypatch) -> None:
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    model = load_model(MODEL_LIVE)
    from histra.types.umfpack import find_umfpack_library

    if find_umfpack_library() is not None:
        pytest.skip("native UMFPACK is available in this environment")

    report = inspect_solver_backend(model, ["Vert"], linear_solver_backend="umfpack")

    assert report.linear_solver_backend == "umfpack"
    assert report.linear_solver_available is False
    assert report.is_compiled_ready is False
    with pytest.raises(CompiledBackendRequiredError, match="UMFPACK was requested"):
        report.require_compiled()


def test_nonlinear_preflight_receives_the_selected_sparse_backend(monkeypatch) -> None:
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    import histra.solver.backend_coverage as coverage_module

    model = load_model(MODEL_LIVE)
    original = coverage_module.inspect_solver_backend
    observed: list[str | None] = []

    def inspect_with_capture(*args, **kwargs):
        observed.append(kwargs.get("linear_solver_backend"))
        return original(*args, **kwargs)

    monkeypatch.setattr(
        coverage_module, "inspect_solver_backend", inspect_with_capture
    )
    code, _ = solve_static_nonlinear(
        model,
        model.collections.analyses[1],
        max_committed_steps=1,
        linear_solver_backend="superlu",
        performance_policy="compiled",
        equilibrium_policy="off",
    )

    assert code == 0
    # Setup preflights before and after the execution-boundary rebuild.
    assert observed == ["superlu", "superlu"]


def test_compiled_policy_fails_closed_when_numba_disabled(monkeypatch) -> None:
    monkeypatch.setenv("HISTRA_DISABLE_COMPILED_SPRINGS", "1")
    model = load_model(MODEL_LIVE)

    report = inspect_solver_backend(model)
    assert report.numba_available is False
    assert report.is_compiled_ready is False

    with pytest.raises(CompiledBackendRequiredError, match="unavailable or disabled"):
        report.require_compiled()

    session = AnalysisSession(model, performance_policy="compiled")
    with pytest.raises(CompiledBackendRequiredError, match="unavailable or disabled"):
        session.run("Vert")


def test_diagnostic_scalar_policy_permits_scalar_fallback_with_notice(monkeypatch) -> None:
    monkeypatch.setenv("HISTRA_DISABLE_COMPILED_SPRINGS", "1")
    model = load_model(MODEL_LIVE)
    logs: list[str] = []

    session = AnalysisSession(
        model,
        performance_policy="diagnostic-scalar",
        on_log=logs.append,
    )
    assert session.performance_policy == "diagnostic-scalar"
    assert any("PERFORMANCE POLICY NOTICE" in log for log in logs)

    # In diagnostic-scalar mode, execution does not raise CompiledBackendRequiredError
    # This diagnostic-policy test is intentionally exercising the two public
    # warnings; capture them so they are assertions rather than suite noise.
    with pytest.warns(UnsafeEquilibriumWarning), pytest.warns(
        SuboptimalSolverStrategyWarning
    ) as advisories:
        execution = session.run("Vert", max_committed_steps=1)
    assert execution is not None
    assert {"HISTRA-STRATEGY-001", "HISTRA-STRATEGY-004"} <= {
        str(item.message).split(":", 1)[0] for item in advisories
    }


def test_compiled_policy_fails_closed_on_unmanaged_interface(monkeypatch) -> None:
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    model = load_model(MODEL_LIVE)
    ModelManager.prepare_model(model)

    # Force one interface to have an unsupported spring
    interface = next(value for value in model.collections.interfaces.values() if value.trasv_1)
    interface.trasv_1[0].tensile_curve_type = "UnsupportedForTesting"

    report = inspect_solver_backend(model)
    assert report.is_compiled_ready is False
    assert report.unmanaged_interfaces >= 1

    with pytest.raises(UnmanagedSolverObjectError, match="unmanaged interface"):
        report.require_compiled()

    session = AnalysisSession(model, performance_policy="compiled")
    with pytest.raises(UnmanagedSolverObjectError, match="unmanaged interface"):
        session.run("Vert")


def test_compiled_backend_covers_parabolic_compression_in_benchmark_model(monkeypatch) -> None:
    """Parabolic masonry compression is a supported generic compiled law."""
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    from histra.solver.model_manager import ModelManager
    from histra.solver.hysteretic_kernels.transverse import (
        COMPRESSIVE_CURVE_TYPE_PARAM,
        COMPRESSIVE_PARABOLIC,
    )

    model = load_model(MODEL_BENCHMARK)
    for material in model.collections.materials.values():
        material.properties["CompressiveCurveType"] = "Parabolic"
        material.properties["CompressiveCurveTypeVertical"] = "Parabolic"

    ModelManager.clear_hysteretic_batch()
    try:
        ModelManager.prepare_model(model)
        report = inspect_solver_backend(model)
        assert report.is_compiled_ready is True
        assert report.unmanaged_interfaces == 0
        assert not report.interface_rejection_reasons

        runtime = ModelManager.prepare_hysteretic_batch(model)
        assert runtime is not None
        assert runtime._compact_simple_params is False
        assert runtime._simple_hysteretic is False
        assert (
            runtime.params[:, COMPRESSIVE_CURVE_TYPE_PARAM]
            == COMPRESSIVE_PARABOLIC
        ).all()
    finally:
        ModelManager.clear_hysteretic_batch()


def test_change_interface_materials_fails_closed_and_rolls_back_if_post_mutation_coverage_fails(monkeypatch) -> None:
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    model = load_model(MODEL_BENCHMARK)
    from histra.solver.model_manager import ModelManager

    ModelManager.prepare_model(model)
    session = AnalysisSession(model, performance_policy="compiled")

    first_key = next(iter(model.collections.interfaces.keys()))
    orig_mat = int(model.collections.interfaces[first_key].material_key)
    target_mat = 146 if 146 in model.collections.materials else orig_mat

    # Patch require_compiled to simulate post-mutation coverage check failure
    def _raise_on_require(self):
        raise CompiledBackendRequiredError("Injected post-mutation backend failure")

    monkeypatch.setattr(SolverBackendCoverageReport, "require_compiled", _raise_on_require)

    with pytest.raises(CompiledBackendRequiredError, match="Injected post-mutation backend failure"):
        session.change_interface_materials([first_key], target_mat)

    # Verify rollback: interface material restored, no mutations recorded, session still usable
    assert int(model.collections.interfaces[first_key].material_key) == orig_mat
    assert len(session.mutations) == 0
    assert session.usable is True


def test_nonlinear_setup_fails_closed_if_runtime_fails_at_execution_boundary(monkeypatch) -> None:
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    model = load_model(MODEL_LIVE)
    from histra.solver.model_manager import ModelManager

    original_prep = ModelManager.prepare_hysteretic_batch
    call_count = 0

    def _prep_patch(m, *, rebuild=False):
        nonlocal call_count
        call_count += 1
        if rebuild:
            # Simulate failure during execution boundary rebuild
            ModelManager.clear_hysteretic_batch()
            ModelManager._hysteretic_batch_error = "Injected runtime build failure on rebuild"
            return None
        return original_prep(m, rebuild=rebuild)

    monkeypatch.setattr(ModelManager, "prepare_hysteretic_batch", _prep_patch)

    analysis = model.collections.analyses[1]
    with pytest.raises(CompiledBackendRequiredError, match="runtime construction failed at execution boundary"):
        solve_static_nonlinear(
            model,
            analysis,
            combination=1,
            max_committed_steps=1,
            performance_policy="compiled",
        )


def test_mixed_runtime_reaction_projection_includes_unmanaged_restraints(monkeypatch) -> None:
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    model = load_model(MODEL_LIVE)
    from histra.postprocessing import compute_total_reaction
    from histra.solver.model_manager import ModelManager

    ModelManager.prepare_model(model)

    # Find a restrained interface
    restrained = [intf for intf in model.collections.interfaces.values() if intf.interfaccia_vincolata_computed()]
    assert len(restrained) > 0
    target_intf = restrained[0]

    # Force this restrained interface to be unmanaged by giving it an unsupported tensile type
    assert len(target_intf.trasv_1) > 0
    target_intf.trasv_1[0].tensile_curve_type = "DiagnosticUnsupportedSentinel"
    target_intf.trasv_1[0].get_force = lambda: 123.0

    # Build the runtime: target_intf is unmanaged, other interfaces are managed
    runtime = ModelManager.prepare_hysteretic_batch(model, rebuild=True)
    assert runtime is not None
    assert id(target_intf) not in runtime.interface_ids
    assert runtime.active is True

    rx = compute_total_reaction(model)
    # The reaction vector must include the unmanaged interface's contribution (non-zero)
    norm_rx = (rx.x**2 + rx.y**2 + rx.z**2)**0.5
    assert norm_rx > 0.0

    # It must match the scalar oracle when runtime is cleared
    ModelManager.clear_hysteretic_batch()
    rx_scalar = compute_total_reaction(model)
    assert abs(rx.x - rx_scalar.x) < 1e-6
    assert abs(rx.y - rx_scalar.y) < 1e-6
    assert abs(rx.z - rx_scalar.z) < 1e-6


def test_restore_committed_analysis_state_is_atomic(monkeypatch) -> None:
    import numpy as np
    from histra.solver.restart import restore_committed_analysis_state
    from histra.io.results_reader import ResultsStateError
    import histra.solver.restart as restart_mod

    results_path = Path(__file__).resolve().parents[1] / "model-output" / "model.Results"
    hrx_path = Path(__file__).resolve().parents[1] / "model-output" / "model.hrx"
    if not results_path.is_file() or not hrx_path.is_file():
        pytest.skip("Output test files not available")

    model = load_model(hrx_path)
    u = np.zeros(int(model.gdl))
    v = np.zeros(int(model.gdl))
    from histra.types.linear_system import LinearSystem
    ls = LinearSystem(int(model.gdl))

    # Monkeypatch read_spring_states to drop one returned spring identity
    orig_read = restart_mod.read_spring_states

    def _read_missing(*args, **kwargs):
        states = orig_read(*args, **kwargs)
        # Drop one identity
        key_to_drop = next(iter(states.keys()))
        del states[key_to_drop]
        return states

    monkeypatch.setattr(restart_mod, "read_spring_states", _read_missing)

    with pytest.raises(ResultsStateError, match="HRX/database spring mismatch"):
        restore_committed_analysis_state(model, results_path, 1, 1, u, v, ls)

    # u array must remain strictly zero, not partially mutated
    assert np.all(u == 0.0)
    assert np.all(v == 0.0)


def test_line_search_routing_respects_csharp_line_search_compatibility() -> None:
    from histra.solver.line_search import SecantLineSearch
    import numpy as np

    class DummyIntegrator:
        def __init__(self):
            self.update_called = False
            self.update_trial_called = False

        def update(self, model, p, an):
            self.update_called = True
            return 0

        def update_trial(self, model, p, an, delta_eta, direction):
            self.update_trial_called = True
            return 0

        def form_unbalance(self, p, model, an):
            pass

    class DummyLS:
        def __init__(self):
            self.b = np.zeros(3)

        def set_x_vector(self, x):
            pass

    class DummyAnalysis:
        def __init__(self, csharp_compat: bool):
            self.csharp_line_search_compatibility = csharp_compat

    class DummyProgram:
        diagnostics = None
        def check_cancelled(self):
            pass

    ls_tool = SecantLineSearch()
    ls_obj = DummyLS()
    direction = np.ones(3)

    # When csharp_line_search_compatibility is True:
    an_compat = DummyAnalysis(True)
    integ_compat = DummyIntegrator()
    ls_tool._trial(None, DummyProgram(), ls_obj, integ_compat, an_compat, direction, 0.5, 1.0)
    assert integ_compat.update_called is True
    assert integ_compat.update_trial_called is False

    # When csharp_line_search_compatibility is False:
    an_prod = DummyAnalysis(False)
    integ_prod = DummyIntegrator()
    ls_tool._trial(None, DummyProgram(), ls_obj, integ_prod, an_prod, direction, 0.5, 1.0)
    assert integ_prod.update_called is False
    assert integ_prod.update_trial_called is True


def test_run_python_solver_job_enforces_compiled_policy(monkeypatch) -> None:
    monkeypatch.setenv("HISTRA_DISABLE_COMPILED_SPRINGS", "1")

    with pytest.raises(CompiledBackendRequiredError, match="unavailable or disabled"):
        run_python_solver_job(
            MODEL_LIVE,
            [PythonAnalysisRequest(name="Vert", output_request=None, timeout_seconds=30.0)],
            timeout_seconds=60.0,
            performance_policy="compiled",
        )


def test_session_rejects_unknown_performance_policy() -> None:
    model = load_model(MODEL_LIVE)
    with pytest.raises(ValueError, match="Unknown performance_policy"):
        AnalysisSession(model, performance_policy="fastest_possible")
