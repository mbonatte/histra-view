"""Architecture checks for the extracted transverse kernel owner."""

import importlib.util

import histra.solver.hysteretic_kernels.transverse as transverse


def test_hysteretic_batch_facade_reexports_transverse_kernels_and_constants():
    batch = importlib.import_module("histra.solver.hysteretic_batch")
    names = (
        "ELASTIC",
        "PLASTIC_T",
        "PLASTIC_C",
        "UNLOAD_T",
        "UNLOAD_C",
        "RELOAD_T",
        "RELOAD_C",
        "RUPTURE",
        "RUPTURE_T",
        "RUPTURE_C",
        "TENSILE_LINEAR",
        "TENSILE_EXPONENTIAL",
        "TENSILE_CURVE_TYPE_PARAM",
        "TRANSVERSE_PARAM_SIZE",
        "_PARAM_NAMES",
        "SIMPLE_PARAM_NAMES",
        "SIMPLE_TENSILE_CURVE_TYPE_PARAM",
        "LINEAR_SIMPLE_TRANSVERSE_PARAM_SIZE",
        "SIMPLE_TRANSVERSE_PARAM_SIZE",
        "_pos_stress_typed",
        "_pos_tangent_typed",
        "_pos_rotlim_typed",
        "_evaluate_linear_batch",
        "_advance_transverse_targets",
        "_evaluate_simple_linear_batch",
        "_advance_and_evaluate_simple_linear_batch",
        "_advance_evaluate_and_finish_simple_linear_batch",
        "_finish_transverse_batch",
    )

    for name in names:
        assert getattr(batch, name) is getattr(transverse, name)


def test_transverse_owner_has_no_reverse_dependency_on_hysteretic_batch():
    source = importlib.util.find_spec(
        "histra.solver.hysteretic_kernels.transverse"
    ).origin
    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()
    assert "hysteretic_batch" not in text


def test_transverse_kernels_are_none_without_numba():
    # The owner and the facade must agree on the no-numba fallback so the
    # skipif markers and runtime guards stay consistent.
    assert transverse.njit is not None or (
        transverse._evaluate_linear_batch is None
        and transverse._evaluate_simple_linear_batch is None
        and transverse._finish_transverse_batch is None
    )
