# Porting Notes

## Origin and naming

Many docstrings and comments identify the code as a direct port of .NET/C# classes. Names such as `GDL`, `alfa`, `Ptarget`, `formUnbalance`, and `NewStep` preserve source terminology.

## Important language differences

### Value/reference behavior

C# `ref` or mutable holder patterns do not translate to Python immutable floats. `ModelManager.compute_energy(model, eel, ed)` demonstrates this mismatch: local additions cannot update caller variables.

### Method overloading

Python does not support C#-style overloads by repeated definition. Later methods replace earlier ones. This affects `ConvergenceTest.test` and duplicate `domain_changed` definitions.

### Static fields

C# static runtime fields were mapped to `ModelManager` class attributes. In Python this makes all analyses in the process share mutable arrays.

### Exceptions and sparse warnings

SciPy sparse solvers may issue warnings and return nonfinite arrays rather than throw the same exceptions as the original numerical library.

### Indexing

HRX/global DOF IDs are one-based. NumPy arrays are zero-based. Afference scattering consistently subtracts one, but every new path must preserve that convention.

### Enums and strings

Several source enums are represented as strings in parsed dataclasses and as integers in solver branches. Normalize at the boundary rather than comparing mixed representations throughout the code.

## Compatibility re-exports

These modules preserve old import paths:

- `histra.model._types`
- `histra.model.quad`
- `histra.model.interface`
- `histra.model.spring`
- `histra.solver.nonlinear_solver`

New implementation should live in the canonical package while compatibility modules only import and re-export.

## Recommended porting discipline

1. Create a behavioral test from the original runtime before changing a ported method.
2. Document source units, signs, and indexing assumptions.
3. Translate state ownership explicitly instead of mimicking static/ref semantics mechanically.
4. Use typed enums and dataclasses at XML boundaries.
5. Compare intermediate values, not only final displacements.
