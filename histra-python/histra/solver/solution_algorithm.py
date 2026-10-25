from __future__ import annotations

from typing import Any

import numpy as np

from histra.solver.incremental_integrator import IncrementalIntegrator, StaticIntegrator
from histra.solver.line_search import (
    BisectionLineSearch,
    LineSearch,
    RegulaFalsiLineSearch,
    SecantLineSearch,
)
from histra.types.convergence_test import ConvergenceTest
from histra.types.linear_system import LinearSystem


_NEWTON_METHODS = {"StandardNewtonRaphson", "ModifiedNewtonRaphson"}
_LINE_SEARCH_TYPES = {
    "StandardSecantLineSearch": SecantLineSearch,
    "StandardRegulaFalsiLineSearch": RegulaFalsiLineSearch,
    "StandardBisectionLineSearch": BisectionLineSearch,
    "ModifiedSecantLineSearch": SecantLineSearch,
    "ModifiedRegulaFalsiLineSearch": RegulaFalsiLineSearch,
    "ModifiedBisectionLineSearch": BisectionLineSearch,
}
_INITIAL_INTERPOLATED_METHODS = {
    "StandardInitialInterpolatedLineSearch",
    "ModifiedInitialInterpolatedLineSearch",
}
_BFGS_METHODS = {
    "BFGS",
    "QuasiNewton",
    "BFGSLineSearch",
    "StandardBFGS",
    "StandardBFGSLineSearch",
}
_LINE_SEARCH_METHODS = set(_LINE_SEARCH_TYPES) | _INITIAL_INTERPOLATED_METHODS


def _new_line_search(an: Any) -> LineSearch:
    method = str(getattr(an, "method", ""))
    if method in _LINE_SEARCH_TYPES:
        search: LineSearch = _LINE_SEARCH_TYPES[method]()
    elif method in _INITIAL_INTERPOLATED_METHODS:
        # C# ``InitialInterpolatedSearch`` hides ``search``/``newStep`` with
        # ``new virtual`` instead of overriding the base methods.  The solver
        # stores it through a ``LineSearch`` reference, so runtime dispatch is
        # the base no-op implementation.  Preserve that behavior for numerical
        # compatibility with committed C# ArcLength results.  The intended
        # algorithm remains available by constructing InitialInterpolatedLineSearch directly.
        search = LineSearch()
    elif method in _NEWTON_METHODS:
        search = LineSearch()
    elif method in _BFGS_METHODS:
        search = BisectionLineSearch()
    else:
        raise ValueError(f"Unsupported nonlinear solution method: {method}")

    search.tolerance = float(np.float32(getattr(an, "line_search_tolerance", 0.8)))
    search.max_eta = float(np.float32(getattr(an, "line_search_max_eta", 10.0)))
    search.min_eta = float(np.float32(getattr(an, "line_search_min_eta", 0.1)))
    search.max_iter = int(getattr(an, "line_search_max_iterations", 100))
    search.print_flag = 0
    return search


class SolutionAlgorithm:
    pass


class EquiSolnAlgo(SolutionAlgorithm):
    def __init__(self) -> None:
        self.the_integrator: IncrementalIntegrator | None = None
        self.the_test: ConvergenceTest | None = None
        self.the_line_search: LineSearch | None = None

    def solve_current_step(
        self,
        p: Any,
        ls: LinearSystem,
        model: Any,
        an: Any,
        combination: int,
        step: int,
        alfa: float,
    ) -> int:
        raise NotImplementedError

    @staticmethod
    def new_equi_soln_algo(an: Any, combination: int) -> "EquiSolnAlgo":
        from histra.solver.newton_line_search import NewtonLineSearch
        from histra.solver.newton_raphson import NewtonRaphson

        method = str(getattr(an, "method", "StandardNewtonRaphson"))
        if method in _NEWTON_METHODS:
            algo: EquiSolnAlgo = NewtonRaphson()
        elif method in _LINE_SEARCH_METHODS:
            algo = NewtonLineSearch()
        elif method in _BFGS_METHODS:
            from histra.solver.bfgs import BFGSSolnAlgo
            max_hist = int(getattr(an, "quasi_newton_history_size", 15))
            algo = BFGSSolnAlgo(max_history=max_hist)
        else:
            raise ValueError(f"Unsupported nonlinear solution method: {method}")

        algo.the_integrator = StaticIntegrator.new_static_integrator(an, combination)
        algo.the_line_search = _new_line_search(an)
        algo.the_test = ConvergenceTest(
            tolerance=float(getattr(an, "convergence_tolerance", 1e-6)),
            max_iter=int(getattr(an, "max_iterations", 20)),
            max_u=float(getattr(an, "max_u", 1e30)),
            criterion=str(getattr(an, "adaptive_convergence_criteria", "ForceMoment")),
            absolute=True,
        )
        return algo
