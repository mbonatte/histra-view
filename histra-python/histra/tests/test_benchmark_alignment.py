"""Focused comparison against the supplied C# SQLite result database."""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pytest

from histra.io.hr_loader import load_model
from histra.model.load import LoadFunction, LoadFunctionItem
from histra.solver.assembler import extract_displacements
from histra.solver.solve import solve_static_nonlinear
from histra.solver.state_snapshot import SolverStateSnapshot

pytestmark = pytest.mark.filterwarnings(
    "ignore::histra.solver.equilibrium.UnsafeEquilibriumWarning"
)

ROOT = Path(__file__).resolve().parents[1]
HRX = ROOT / "model-output" / "model.hrx"
RESULTS = ROOT / "model-output" / "model.Results"


def _single_csharp_step_analysis(model):
    analysis = copy.deepcopy(model.collections.analyses[1])
    analysis.load_function_key = 999
    analysis.load_function = LoadFunction(
        key=999,
        discr_val=0.2,
        items=[
            LoadFunctionItem(pseudo_time=0.0, multiplier=0.0),
            LoadFunctionItem(pseudo_time=0.2, multiplier=0.2),
        ],
    )
    model.collections.load_functions[999] = analysis.load_function
    return analysis


def test_first_nonlinear_step_matches_csharp_database():
    model = load_model(HRX)
    analysis = _single_csharp_step_analysis(model)
    code, steps = solve_static_nonlinear(model, analysis)
    assert code == 0
    assert len(steps) == 1
    assert steps[0]["status"] == "OK"

    python_u = steps[0]["u"]
    csharp_u = extract_displacements(
        model,
        results_path=str(RESULTS),
        analysis_key=1,
        combination=1,
        step=1,
    )
    relative_error = np.linalg.norm(python_u - csharp_u) / np.linalg.norm(csharp_u)
    assert relative_error < 5e-5
    assert np.max(np.abs(python_u - csharp_u)) < 3e-7

def test_newton_line_search_uses_only_the_step_checkpoint(monkeypatch):
    """Do not copy every spring history for each accepted Newton correction."""
    model = load_model(HRX)
    analysis = _single_csharp_step_analysis(model)
    analysis.method = "ModifiedRegulaFalsiLineSearch"

    captures = 0
    original_capture = SolverStateSnapshot.capture.__func__

    def counted_capture(cls, *args, **kwargs):
        nonlocal captures
        captures += 1
        return original_capture(cls, *args, **kwargs)

    monkeypatch.setattr(
        SolverStateSnapshot,
        "capture",
        classmethod(counted_capture),
    )

    code, steps = solve_static_nonlinear(model, analysis)
    assert code == 0
    assert len(steps) == 1
    assert captures == 1  # the pre-step rollback checkpoint in solve.py


def test_chained_analysis_restores_complete_csharp_state():
    from histra.solver.program import Program
    from histra.solver.restart import restore_committed_analysis_state
    from histra.types.linear_system import LinearSystem

    model = load_model(HRX)
    p = Program(gdl=model.gdl)
    p.u = np.zeros(model.gdl)
    p.v = np.zeros(model.gdl)
    ls = LinearSystem(model.gdl)
    summary = restore_committed_analysis_state(
        model, RESULTS, analysis_key=1, combination=1, u=p.u, v=p.v, ls=ls
    )
    assert summary.step == 5
    assert summary.dof_count == 126
    assert summary.quad_count == 18
    assert summary.interface_count == 29
    assert summary.spring_count == 2454
    assert np.max(np.abs(p.u)) > 0.0


def test_csharp_global_dynamic_vector_is_readable():
    from histra.io.results_reader import read_dynamic_vectors

    u, v, step = read_dynamic_vectors(RESULTS, analysis_key=1, size=126)
    assert step == 5
    assert u.shape == (126,)
    assert v.shape == (126,)
    assert np.all(np.isfinite(u))
    assert np.all(np.isfinite(v))
