"""Architecture checks for the nonlinear setup/step-execution split."""

import importlib


def test_solve_facade_reexports_split_helpers_by_identity():
    solve = importlib.import_module("histra.solver.solve")
    setup = importlib.import_module("histra.solver.nonlinear_setup")
    step = importlib.import_module("histra.solver.nonlinear_step")

    for name in ("_NonlinearSetup", "_set_initial_state", "_setup_nonlinear_analysis"):
        assert getattr(solve, name) is getattr(setup, name)
    for name in (
        "_als_loop",
        "_commit_state",
        "_execute_steps",
        "_is_load_control",
    ):
        assert getattr(solve, name) is getattr(step, name)


def test_setup_owner_has_no_reverse_dependency_on_solve():
    source = importlib.util.find_spec("histra.solver.nonlinear_setup").origin
    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()
    assert "histra.solver.solve" not in text


def test_step_owner_has_no_reverse_dependency_on_solve():
    source = importlib.util.find_spec("histra.solver.nonlinear_step").origin
    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()
    assert "histra.solver.solve" not in text
