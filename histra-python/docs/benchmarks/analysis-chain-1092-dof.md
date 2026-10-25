# Vert → scour_1 → LiveLoad_1 integration report

## Supplied benchmark

The C# package contains a locked 1,092-DOF model with 156 Quads, 365 interfaces
and a `.Results` database for:

1. `Vert` (analysis 1);
2. interface material change on keys 359–362 from the default parent-material
   definition (`MaterialKey=0`) to `Soil_removed` (material 147);
3. `scour_1` (analysis 23, predecessor 1);
4. `LiveLoad_1` (analysis 22, predecessor 23).

The final serialized HRX is post-mutation. The Python benchmark reconstructs
the original Vert model by rebuilding keys 359–362 with `MaterialKey=0`.

## C# behavior verified

`InterfaceOperations.ReSetInterfaces` rebuilds a modified interface using the
custom material key on both sides. `ModelManager.SetStatus` then restores the
predecessor database state onto those new definitions. Consequently, at the
scour boundary:

- committed displacement and force initially remain unchanged;
- the new spring stiffness/material definition is active;
- old phase, strength/history and plastic variables are preserved;
- the first scour update recomputes force using the new stiffness.

For interface 359, transverse spring 0:

| State | `k` | committed `U` | committed `F` |
|---|---:|---:|---:|
| Python after Vert | 9000.0 | -6.751096e-4 | -6.075987 |
| Immediately after mutation | 2.777778e-2 | -6.751096e-4 | -6.075987 |
| After scour step 1 | 2.777778e-2 | -6.751096e-4 | -1.875304e-5 |
| C# scour step 1 | — | -6.751095e-4 | -1.875307e-5 |

## Numerical results

| Analysis | Committed steps | Python status | Max relative displacement error | Max absolute DOF error | Max reaction-component error |
|---|---:|---:|---:|---:|---:|
| Vert | 5 | completed | 1.285e-8 | 2.743e-10 | 7.629e-6 |
| scour_1 | 5 | completed | 1.510e-8 | 1.446e-9 | 1.526e-5 |
| LiveLoad_1 | 38 | configured stop at attempted step 39 | 2.036e-4 | 3.166e-4 | 3.121e-2 |

The Python sequence commits the same 5 + 5 + 38 steps and reaches the same
configured Live Load displacement-limit event at attempted step 39.

The Vert and scour material-boundary implementation matches C# well below the
`1e-4` displacement target. The Live Load difference is the existing
ArcLength/source-binary compatibility gap; it is not introduced by the new
material mutation or in-memory initialization.

## Runtime in the audit environment

Warm measured solver times were approximately:

- Vert: 0.69 s
- scour_1: 0.59 s
- LiveLoad_1 through attempted step 39: 5.41 s

No SQLite state write/read is used between analyses.

## Code added

- `histra.solver.interface_material`
  - atomic selective interface rebuild;
  - C#-compatible committed-state transfer;
  - compiled-runtime invalidation.
- `histra.solver.session`
  - HRX dependency resolution;
  - in-memory analysis state;
  - boundary mutation hook;
  - explicit predecessor validation.
- `rebuild_interface_springs(...)` in preprocessing.
- Committed spring capture/transfer helpers in restart handling.

## Validation

- Compile: pass
- Import: pass
- Default suite: 147 passed, 3 opt-in benchmarks skipped
- Full chain benchmark: pass when `HISTRA_RUN_CHAIN_BENCHMARK=1`
