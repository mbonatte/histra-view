# Partial-edge PrepareModel correction

## Summary

The 680-Quad benchmark failed during the first virgin `Vert` step because the Python preprocessor omitted contacts at nonconforming masonry mesh junctions. The model contains long Quad faces that are divided across two shorter adjacent Quad faces. These T-junction contacts do not share the same endpoint-node pair, so the previous exact-edge lookup did not create an interface.

The nonlinear solver was not the root cause. Missing interfaces left parts of the structural model disconnected and produced an abnormally large first elastic predictor.

## C# path traced

The relevant original source is:

- `C#_Original/ModelManagement.ComputationalElementsOperations/InterfaceOperations.cs`
  - `GIQuadQuad`
  - `GIQuadQuadSerial`
  - `PrepareBuildInterface`
  - `BuildInterface`
- `C#_Original/Objects/Quad.cs`
  - `PointAfference`
  - `FindAff_p_v`
  - `GetDisplacementFromShearDOF`

C# does not require two contacting faces to have identical endpoint node keys. It computes the geometric intersection of the Quad face polygons, builds an interface over the overlap, and evaluates Quad afference at the resulting interface endpoints. An endpoint may lie inside a neighboring Quad edge rather than at one of its vertices.

## Defect in the previous Python port

The previous implementation used an exact unordered node-pair map:

```text
(edge node A, edge node B) -> attached Quad faces
```

That correctly handled conforming meshes, but it omitted a contact when a two-node long edge overlapped two separately meshed shorter edges.

For this benchmark, the omission was measurable before analysis:

| Computational object | Previous Python | C# locked model | Difference |
|---|---:|---:|---:|
| Quad–Quad interfaces | 1,237 | 1,249 | -12 |
| Total interfaces | 1,247 | 1,259 | -12 |
| Transverse springs | 61,103 | 61,691 | -588 |
| In-plane sliding springs | 1,247 | 1,259 | -12 |
| Out-of-plane springs | 2,494 | 2,518 | -24 |
| Total springs | 65,524 | 66,148 | -624 |

Each omitted partial interface contains 49 transverse springs. The 12 omitted contacts therefore account exactly for the 588 missing transverse springs.

## Correction

Python preprocessing now:

1. Retains the fast exact-node edge map for ordinary conforming contacts.
2. Collects unmatched lateral Quad edges.
3. Detects positive-length collinear overlap between unmatched edges.
4. Clips the first Quad lateral face to the overlap interval.
5. Reuses an existing geometric node at each overlap endpoint or creates a geometry-only node when necessary.
6. Creates the interface using the C#-observable parent/face ordering.
7. Computes `ncol` and `nspring` from the overlap length rather than the complete long-edge length.
8. Interpolates the Quad warping/shear afference vector at arbitrary edge points, matching C# `GetDisplacementFromShearDOF` behavior.

The generated geometry-only nodes do not receive structural DOFs. Structural afference remains attached to each parent Quad's seven generalized DOFs.

## Corrected generated model

| Computational object | Corrected Python | C# locked model |
|---|---:|---:|
| Global DOFs | 4,760 | 4,760 |
| Quads | 680 | 680 |
| Quad–Quad interfaces | 1,249 | 1,249 |
| Restraint interfaces | 10 | 10 |
| Total interfaces | 1,259 | 1,259 |
| Quad diagonal springs | 680 | 680 |
| Transverse springs | 61,691 | 61,691 |
| In-plane sliding springs | 1,259 | 1,259 |
| Out-of-plane springs | 2,518 | 2,518 |
| Total springs | 66,148 | 66,148 |

The generated interface topology and ordering match the locked C# model exactly.

## Numerical validation

### Initial model

- Interface topology: exact
- Afference entry count: 39,742 versus 39,742
- Afference global-DOF sequence: exact
- Afference coefficient relative L2 error: `1.538e-5`
- Initial global-stiffness relative L2 error: `1.360e-6`

All 12 newly generated partial interfaces have the same endpoint-node ordering and interface geometry as the C# model. Their `VInt3D` vectors match exactly in the comparison.

### Virgin Vert analysis

The corrected Python-generated model completes all five `Vert` steps:

| Step | Load factor | Iterations | Python ReactionSum Z | C# ReactionSum Z |
|---:|---:|---:|---:|---:|
| 1 | 0.2 | 5 | -180.21739864 | -180.21738815 |
| 2 | 0.4 | 6 | -360.43479729 | -360.43478966 |
| 3 | 0.6 | 21 | -540.65213394 | -540.65212250 |
| 4 | 0.8 | 8 | -720.86956024 | -720.86958313 |
| 5 | 1.0 | 19 | -901.08694458 | -901.08695984 |

Final committed global displacement comparison:

- Relative error: `2.908e-6`
- Maximum absolute DOF difference: `2.024e-7`
- Maximum absolute Z-reaction difference: `2.289e-5`

The complete Vert iteration sequence is identical to the software-prepared model: `[5, 6, 21, 8, 19]`.

### Chained Live Load smoke comparison

The first Live Load ArcLength step was run from both:

- the C#-locked computational model; and
- the same model regenerated by Python from raw geometry.

Both committed in 74 iterations.

- Generated-versus-locked displacement relative error: `2.096e-6`
- Maximum absolute DOF difference: `2.660e-7`
- Locked load multiplier: `20.6577517340`
- Generated load multiplier: `20.6577412401`

The complete Live Load history for this larger model was not rerun during this audit. The first chained step verifies that the corrected preprocessing enters the same initial ArcLength branch.

## Tests added

- T-junction generation where one long Quad edge touches two shorter Quad edges
- Exact contact length and parent/face ordering
- Complete interface afference creation for partial contacts
- Warping/shear interpolation at a non-vertex interface endpoint

Final suite:

```text
compileall: PASS
import: PASS
142 passed
2 opt-in benchmarks skipped
0 failed
```

## Current geometry scope

Supported:

- Exact complete shared edges
- Positive-length collinear partial-edge contacts on lateral Quad faces
- T-junctions where a long edge is split across multiple shorter edges
- Fixed line restraints already associated with Quad faces

Still rejected explicitly:

- Non-collinear polygonal face intersections
- Area-overlap contacts that are not reducible to a common collinear lateral edge
- Non-manifold contacts
- Unsupported element families and dynamic preprocessing

