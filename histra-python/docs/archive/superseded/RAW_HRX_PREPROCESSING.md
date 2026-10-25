# Raw HRX preprocessing

## Supported workflow

Python now implements the `ModelManager.PrepareModel` path needed by the
supplied masonry bridge models. An unlocked geometry HRX can therefore be
loaded with `IsLocked=false`, `GDL=0`, no generated interfaces, and no
serialized springs. Before the nonlinear solver allocates its vectors, Python
builds the computational model in memory.

The translated stage performs:

1. masonry constitutive-law extraction;
2. seven global generalized DOFs for each non-slave Quad;
3. one diagonal Coulomb spring for each Quad;
4. exact full-edge Quad–Quad contact detection;
5. Quad–Restraint contact generation for fixed line restraints;
6. transverse hysteretic fiber generation;
7. in-plane and out-of-plane Coulomb spring generation;
8. Quad and Interface afference matrices;
9. initial element status and stiffness preparation;
10. final solver-readiness validation.

The public entry points are:

```python
from histra.io.hr_loader import load_model
from histra.solver.model_manager import ModelManager

model = load_model("model.HRX")
report = ModelManager.prepare_model(model)
print(report)
```

Ordinary nonlinear solves call this automatically when the HRX is not already
solver-ready:

```python
from copy import deepcopy
from histra.solver.solve import solve_static_nonlinear

analysis = deepcopy(model.collections.analyses[1])
code, steps = solve_static_nonlinear(model, analysis, 1)
```

Use `auto_prepare=False` only when the caller wants an unlocked HRX to fail
rather than being prepared.

## C# source chain translated

The behavioral reference was the original C# source, principally:

- `SolverRuntime/SolverRuntime/ModelManager.cs`
  - `PrepareModel`
  - `ComputeAff`
- `ModelLibrary.ComputationalElements/MainPartition.cs`
  - `PrepareModel`
- `ConstitutiveLawOperations.ExtractInfoFromMaterials`
- `InterfaceOperations.GenerateInterfaces`
- Quad, Interface, `SpringHysteretic`, and `SpringCoulomb03` construction and
  ultimate-displacement methods
- `AfferenceMatrix.SetFromCoefficients`

The Python implementation is in:

- `histra/preprocessing/prepare_model.py`
- `histra/solver/model_manager.py`
- `histra/solver/solve.py`

## Validated topology

The current preprocessing port deliberately supports the topology present in
the supplied models:

- four-node masonry Quads;
- exact complete shared edges between two Quads;
- fixed line restraints associated with a Quad edge;
- one material per Quad;
- non-slave Quads with seven generalized DOFs;
- the masonry diagonal, transverse, sliding, and out-of-plane constitutive
  families used by the benchmarks.

Unsupported preprocessing features fail explicitly. They are not converted to
zero stiffness or silently omitted. Unsupported cases currently include:

- partial polygon intersections;
- non-manifold contacts where more than two Quads share an edge;
- Frame, Solid, Fiber, Vertex, InterfaceMF, and other computational families;
- slave-element/partition preprocessing;
- elastic or free restraint types not represented by the validated fixed-line
  path;
- dynamic matrix preparation.

## Numerical validation against the locked C# model

The existing C#-preprocessed `model-output/model.hrx` was loaded twice. Python
then deleted and regenerated one copy's computational data from the geometry
and material definitions.

Measured results:

- generated interfaces: 29, matching the C# order and topology exactly;
- generated springs: 18 Quad, 2,349 transverse, 29 in-plane sliding, and 58
  out-of-plane sliding;
- global DOFs: 126, exact;
- interface afference entries: 880, exact count;
- afference global-DOF sequence: exact;
- afference coefficient relative L2 error: `4.112e-8`;
- maximum afference coefficient absolute difference: `1.257e-5`;
- initial global-stiffness relative L2 error: `1.974e-7`.

The regeneration command is:

```bash
python -m histra.tools.benchmark_preprocessing \
  --reference histra/model-output/model.hrx \
  --raw /path/to/unlocked/model.HRX \
  --run-vert \
  --output preprocessing_metrics.json
```

## Uploaded `new_model.hrx`

The uploaded file starts with:

- `IsLocked=false`;
- `GDL=0`;
- 112 nodes;
- 80 masonry Quads;
- 6 fixed line restraints;
- no generated interfaces or springs.

Python now generates:

- 560 global DOFs;
- 80 Quad diagonal springs;
- 129 Quad–Quad interfaces;
- 6 Quad–Restraint interfaces;
- 10,935 transverse springs;
- 135 in-plane sliding springs;
- 270 out-of-plane sliding springs.

The resulting model passes solver-readiness validation. Its five-step `Vert`
analysis runs directly from the unlocked HRX and commits load factors 0.2,
0.4, 0.6, 0.8, and 1.0. In the audit environment, preprocessing took about
20.0 seconds and the five-step Vert solve about 2.0 seconds.

## Live Load data issue in `new_model.hrx`

The model's `LiveLoad_1` analysis uses custom load combination key 15. Its only
line load belongs to load condition 11 (`User_condition`), but combination 15
contains coefficients only for conditions 1 through 9. The solver therefore
raises:

```text
Load combination 15 has no row 1 coefficient for condition 11
```

This is model input data, not a preprocessing omission. The previously working
C#/Python Live Load benchmark contains the missing combination entry for
condition 11 with row-1 value `1.0`. Python does not silently invent that
coefficient. Add the coefficient in the authoring software, export the HRX
again, and run the standalone workflow.

## Persistence

The prepared computational model currently exists in memory for the duration
of the Python process. Python does not yet rewrite the source HRX with generated
interfaces and springs. Running the same unlocked HRX in a new process repeats
the preprocessing stage.

## Exact nonlinear-path alignment update

The 560-DOF software benchmark showed that topology and initial stiffness alone
were insufficient for path-dependent ArcLength compatibility. The Python port
now also preserves C# `Quad.cosAlfa`, the literal `SetNonLinearProperties`
search, diagonal orthotropy/ElastoPlastic branches, `System.Single` material
rounding, and the actual-`H` Coulomb combination rule.

After these corrections, a force-regenerated computational model commits the
same 38 Live Load steps and follows the same Python iteration sequence as the
C#-locked model. See `PREPROCESSING_EXACTNESS_REPORT.md`.

## Nonconforming Quad edge contacts

`PrepareModel` supports collinear partial-edge contacts on lateral Quad faces. This includes T-junctions where one long masonry edge touches two or more shorter edges. The generated interface uses the overlap length, and Quad afference is interpolated at interface endpoints that lie inside an edge rather than at a Quad vertex.

This behavior ports the relevant C# `GIQuadQuad`/`PrepareBuildInterface` and `Quad.GetDisplacementFromShearDOF` path. See `PARTIAL_EDGE_PREPROCESSING_REPORT.md` for the 680-Quad validation.

Non-collinear polygon intersection and non-manifold contacts remain unsupported and fail explicitly.
