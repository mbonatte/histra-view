# Data Model

## Root model

`Model` contains global metadata (`version`, `gdl`, wizard/lock flags) and one `Collections` object. `gdl` is the number of global degrees of freedom.

`Collections` owns keyed dictionaries:

| Collection | Value type | Role |
|---|---|---|
| `nodes` | `Node` | Geometric coordinates |
| `node_c` | `NodeC` | Constrained/master/slave node relationships |
| `quads` | `Quad` | Masonry macro-elements |
| `interfaces` | `Interface` | Connection/interface elements |
| `restraints` | `Restraint` | Support definitions |
| `load_combinations` | `LoadCombination` | Coefficient tables |
| `load_conditions` | `LoadCondition` | Action metadata and safety factors |
| `load_functions` | `LoadFunction` | Pseudo-time/load discretization settings |
| `analyses` | `Analysis` | Solver method and stopping settings |
| `materials` | `MasonryMaterial` | Density/weight and mechanical properties |

## Geometry and connectivity

`Node` stores a `Point`. `NodeC` links a node to master and slave elements and stores local displacement/load arrays. Elements reference node keys rather than direct node objects.

## Afference mapping

`AfferenceEntry(gdl, alfa)` maps a local element coordinate to a global degree of freedom. HRX `gdl` values are one-based; assembly subtracts one for NumPy indexing.

A local stiffness term `k[i,j]` is scattered as:

```text
K[gdl_a, gdl_b] += alfa_a · k[i,j] · alfa_b
```

This permits one local coordinate to contribute to multiple global coordinates and supports orientation/transformation coefficients.

## Quadrilateral element

`Quad` stores geometry, references, a local seven-component state, afference lists, interface keys, and a diagonal nonlinear spring. Its main responsibilities are:

- self-weight and local static-load calculation;
- stiffness calculation;
- local deformation extraction from the global correction;
- nonlinear spring update;
- resisting-force assembly;
- commit/revert and energy reporting.

## Interface element

`Interface` stores parent/face geometry, a two-dimensional spring grid, sliding and out-of-plane springs, local reference axes, afference, and `InterfaceState`. It computes several local stiffness blocks and distributes them globally.

## Constitutive springs

All springs derive from `Spring`. The base state includes stiffness, tangent stiffness, force, displacement, active flag, and phase. Nonlinear laws add committed and trial history.

| Spring | Intended behavior |
|---|---|
| `SpringElastic` | Linear elastic |
| `SpringCoulomb` | Basic friction parameters |
| `SpringCoulomb03` | Detailed contact/friction/Takeda-style hysteresis |
| `SpringHysteretic` | Configurable positive/negative backbone, pinching, damage, reversal rules |
| `SpringMultiLinear` | Piecewise force-deformation data |

The registry uses the XML `TypeOf` attribute to select a class.

## Loads and analyses

`LoadCombination` is a list of row/column coefficient items. `LoadCondition` stores action type and gamma factors. `LoadFunction` currently stores only discretization flags and value; the solver expects pseudo-time/multiplier items that are not represented (`ISSUE-09`).

`Analysis` selects:

- load combination and load function;
- LoadControl or ArcLength integration;
- Standard/Modified Newton and optional line-search method;
- convergence tolerance, iteration limit, and maximum displacement;
- P-Delta and ALS settings;
- a master displacement DOF.

## Mutable states

| State object | Main contents |
|---|---|
| `QuadState` | local displacement array, stiffness, load vector, scalar resisting force |
| `InterfaceState` | local displacement/velocity, force/moment arrays, local stiffness blocks |
| `IntegratorState` | step, load factor fields, displacement reference, and analysis metadata attached dynamically |
| Spring committed/trial fields | history-dependent constitutive variables |
| `LinearSystem` | current global sparse system and vectors |

## HRX loading

`load_model()` uses streaming end-event parsing. Entity constructors consume XML attributes/children, and the loader clears processed elements. This reduces memory use, but any child data needed by the parent must remain attached until the parent end event. The loader already special-cases nested interface references for this reason.

## Stored results

`results_reader.py` reads a sibling SQLite `.Results` database. It can list steps and return quadrilateral `U1..U7` values. `assembler.extract_displacements()` can project those values back to global DOFs or use the model's in-memory post-solve state.
