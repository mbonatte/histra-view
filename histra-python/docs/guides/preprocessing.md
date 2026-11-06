# HRX computational-model preprocessing

The Python preprocessor implements the validated masonry subset required by the
committed bridge benchmarks.

## Fresh preparation boundary

Serialized HRX interfaces, springs and afferences are reference snapshots from
past C# runs. Regenerate them from the structural geometry before numerical or
modal solving:

```python
from histra import load_model
from histra.solver.model_manager import ModelManager

model = load_model("bridge.hrx")
ModelManager.prepare_model(model, force=True)
```

`AnalysisSession` and solver entry points with `auto_prepare=True` enforce the
required preparation boundary. Disabling automatic preparation does not make a
serialized model valid for solving; unsupported unprepared states fail closed.
The source HRX remains unchanged for differential auditing.

## Supported geometry

- four-node masonry Quad elements;
- full-edge Quad–Quad contacts;
- collinear partial-edge contacts;
- partition/T-junction overlaps where one long edge contacts multiple shorter
  edges;
- fixed line-Restraint contacts already associated with a Quad face.

## Generated computational objects

The preprocessing path creates the global DOF numbering, Quad diagonal springs,
Quad–Quad and Quad–Restraint interfaces, transverse hysteretic fibers, sliding
springs, out-of-plane springs, and afference matrices required by the nonlinear
solver.

## Failure behavior

Unsupported topologies raise an explicit preparation error. The preprocessor
does not silently create a partially connected model.

## Compatibility note

Preprocessing is path-sensitive. Benchmark reports under `docs/benchmarks/`
record the model-specific C# alignment evidence. Those measurements should not
be generalized to unsupported geometry.
