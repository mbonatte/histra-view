"""Exact modal scatter and coverage at the live initialization boundary."""

from types import SimpleNamespace as Namespace

import numpy as np
import pytest

from histra import AnalysisSession, load_solver_model
from histra.solver.assembler import _assemble_global_k_legacy
from histra.solver.backend_coverage import CompiledBackendRequiredError
from histra.solver.modal import solve_modal_analysis
from histra.solver.modal_assembly import assemble_modal_stiffness
from histra.solver.model_manager import ModelManager
from tools.benchmarks.build_material_modal_reference_models import (
    CASES,
    DEFAULT_TEMPLATE,
    build_material_modal_model,
)


def _prepared_model(tmp_path):
    path = tmp_path / "modal-performance.hrx"
    build_material_modal_model(DEFAULT_TEMPLATE, CASES[0]).write(
        path, encoding="utf-8", xml_declaration=True
    )
    model = load_solver_model(path)
    ModelManager.prepare_model(model, force=True, use_cache=False)
    return model


def _entry(dof, weight):
    return Namespace(gdl=dof, alfa=weight)


def _assert_csc_identical(left, right):
    assert left.shape == right.shape
    for field in ("indptr", "indices", "data"):
        a, b = getattr(left, field), getattr(right, field)
        assert a.dtype == b.dtype and a.tobytes() == b.tobytes(), field


@pytest.mark.parametrize(
    "sliding,out_of_plane", [(True, True), (False, True), (True, False), (False, False)]
)
def test_modal_scatter_preserves_full_coo_order_and_asymmetric_blocks(sliding, out_of_plane):
    rng = np.random.default_rng(1704)

    def compute(_alfa):
        pass

    afferences = [
        [_entry(i % 5 + 1, 0.7), _entry((i + 1) % 5 + 1, -0.3), _entry(0, 9.0), _entry(20, 8.0)]
        for i in range(12)
    ]
    interface = Namespace(
        dim_aff=[6, 2, 4],
        aff=afferences,
        compute_k=compute,
        slid=[object()] if sliding else [],
        slid_out_plan=[object(), object()] if out_of_plane else [],
        status=Namespace(
            k=rng.normal(size=(6, 6)),
            kslid=rng.normal(size=(2, 2)),
            kslid_out_plan=rng.normal(size=(4, 4)),
        ),
    )
    # Keep exact historical cutoffs, duplicate terms and cancellation order.
    interface.status.k[0, :4] = [1e-30, 1e-31, -1e-30, 0.0]
    quad = Namespace(
        aff=[[]] * 6 + [[_entry(1, 1.0), _entry(2, -0.5)]],
        status=Namespace(k=1e-30),
        compute_k=compute,
    )
    model = Namespace(
        gdl=5, collections=Namespace(quads={1: quad}, interfaces={2: interface, 1: interface})
    )
    _assert_csc_identical(
        assemble_modal_stiffness(model), _assemble_global_k_legacy(model, alfa=1.0)
    )


def test_modal_scatter_handles_empty_domain_and_missing_afferences():
    model = Namespace(gdl=3, collections=Namespace(quads={}, interfaces={}))
    _assert_csc_identical(assemble_modal_stiffness(model), _assemble_global_k_legacy(model))
    interface = Namespace(
        dim_aff=[1, 2, 0],
        aff=[[_entry(1, 1.0)]],
        status=Namespace(k=[[2.0]], kslid=[[1.0, -1.0], [-1.0, 1.0]], kslid_out_plan=[]),
        slid=[object()],
        slid_out_plan=[],
        compute_k=lambda alfa: None,
    )
    model.collections.interfaces[1] = interface
    _assert_csc_identical(
        assemble_modal_stiffness(model), _assemble_global_k_legacy(model, alfa=1.0)
    )
    interface.slid_out_plan = [object(), object()]
    _assert_csc_identical(
        assemble_modal_stiffness(model), _assemble_global_k_legacy(model, alfa=1.0)
    )


def test_virgin_modal_builds_once_after_initialization_and_reports_actual_backend(
    tmp_path, monkeypatch
):
    import histra.solver.modal as modal

    monkeypatch.setenv("HISTRA_LINEAR_SOLVER", "superlu")
    model = _prepared_model(tmp_path)
    original_initialize = modal._set_initial_state
    original_build = ModelManager.prepare_hysteretic_batch
    initialized = False
    builds = []

    def initialize(*args, **kwargs):
        nonlocal initialized
        original_initialize(*args, **kwargs)
        initialized = True

    def build(m, *, rebuild=False):
        previous = ModelManager.hysteretic_batch_for(m)
        result = original_build(m, rebuild=rebuild)
        if result is not None and result is not previous:
            builds.append(initialized)
        return result

    monkeypatch.setattr(modal, "_set_initial_state", initialize)
    monkeypatch.setattr(ModelManager, "prepare_hysteretic_batch", build)
    session = AnalysisSession(model, linear_solver_backend="umfpack")
    execution = session.run(3)
    assert execution.completed and builds == [True]
    assert session.backend_coverage.linear_solver_backend == "superlu"
    assert session.backend_coverage.unmanaged_quads == 0
    assert session.backend_coverage.unmanaged_interfaces == 0


def test_modal_rejects_failed_post_initialization_runtime_before_assembly(tmp_path, monkeypatch):
    import histra.solver.modal as modal

    model = _prepared_model(tmp_path)
    monkeypatch.setattr(ModelManager, "prepare_hysteretic_batch", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        modal, "assemble_modal_stiffness", lambda *args, **kwargs: pytest.fail("unsafe assembly")
    )
    with pytest.raises(CompiledBackendRequiredError, match="runtime_construction_failed"):
        solve_modal_analysis(model, model.collections.analyses[3])


def test_modal_diagnostic_scalar_is_explicit_and_matches_compiled_modes(tmp_path, monkeypatch):
    import histra.solver.modal as modal

    model = _prepared_model(tmp_path)
    analysis = model.collections.analyses[3]
    compiled = solve_modal_analysis(model, analysis)
    ModelManager.prepare_model(model, force=True, use_cache=False)
    monkeypatch.setattr(
        modal, "assemble_modal_stiffness", lambda *args, **kwargs: pytest.fail("compiled path")
    )
    reference = solve_modal_analysis(model, analysis, performance_policy="diagnostic-scalar")
    np.testing.assert_array_equal(compiled.frequencies, reference.frequencies)
    np.testing.assert_array_equal(compiled.mode_shapes, reference.mode_shapes)
    with pytest.raises(ValueError, match="performance_policy"):
        solve_modal_analysis(model, analysis, performance_policy="off")


def test_modal_scatter_cannot_silently_execute_without_numba(monkeypatch):
    import histra.solver.modal_assembly as assembly

    monkeypatch.setattr(assembly, "_scatter_blocks", None)
    model = Namespace(gdl=3, collections=Namespace(quads={}, interfaces={}))
    with pytest.raises(CompiledBackendRequiredError, match="requires Numba"):
        assembly.assemble_modal_stiffness(model)
