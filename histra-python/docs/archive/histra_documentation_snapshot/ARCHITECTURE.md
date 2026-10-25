# Architecture

## Model and I/O

- `io/hr_loader.py` parses the HRX into typed model collections.
- `io/results_reader.py` reads committed C# SQLite metadata, displacements, quads, interfaces, springs, and load multipliers.
- `solver/restart.py` maps complete final SQLite state back into Python global, element, and spring state.

## Elements and constitutive models

- `elements/quad.py` owns quad local displacement, stiffness, residual, normal stress, volume, self-weight, and `ComputeDN` behavior.
- `elements/interface.py` owns flexural, in-plane sliding, and out-of-plane spring groups. It computes transverse normal-force increments before updating Coulomb springs.
- `springs/hysteretic.py` implements transverse nonlinear response.
- `springs/coulomb03.py` implements normal-force-dependent friction, history, tangent, phase, commit, and revert.

## Assembly and orchestration

- `solver/assembler.py` assembles global stiffness, residual/load vectors, afference mappings, and the active C# `TwoSprings` torsional branch.
- `solver/model_manager.py` controls element update order, residual assembly, energy, and load generation.
- `solver/load_control.py` and `solver/arc_length.py` implement incremental integrators.
- `solver/newton_raphson.py` and `solver/newton_line_search.py` implement equilibrium algorithms.
- `solver/line_search.py` implements the translated line searches.
- `solver/solve.py` orchestrates initialization, optional restart, step creation, iteration, ALS/ArcLength retry, commit, termination, and metrics.
- `solver/state_snapshot.py` captures and restores complete reversible nonlinear state.

## Benchmark boundary

The selected benchmark exercises LoadControl, modified Newton stiffness, Regula-Falsi line search, Work convergence, self-weight, quads, interfaces, hysteretic springs, and Coulomb03 springs. It does not exercise P-Delta, ALS, or ArcLength.
