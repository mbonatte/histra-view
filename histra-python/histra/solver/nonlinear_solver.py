# nonlinear_solver.py - backward-compat stub, re-exports from histra.solver

from histra.solver import (
    IncrementalIntegrator, StaticIntegrator, LoadControl,
    ArcLength, ArcLengthLinear,
    SolutionAlgorithm, EquiSolnAlgo, NewtonRaphson, NewtonLineSearch,
    LineSearch, RegulaFalsiLineSearch,
    ModelManager, Program, ConvergenceTest,
    solve_static_nonlinear,
)
from histra.model.model import Model
