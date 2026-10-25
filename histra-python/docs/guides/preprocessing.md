# HRX computational-model preprocessing

The Python preprocessor implements the validated masonry subset required by the
committed bridge benchmarks.

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
