# 3D Bridge new-format review — v2.0.0 re-check

**Status:** the format is ready and the viewer adapter is implemented in
`model-view/bridge_v2.py`, `model-view/server.py` and
`model-view/static/results.js`. The original review findings are retained below
for traceability.
**Date:** 2026-10-25
**Supersedes:** the earlier v1.0.0 review, which was removed during the data
refresh. This report is self-contained.
**Scope:** `3D_bridge/pdelta_*` (updated 2026-10-25), `3D_bridge/Bridge.hrx`,
`model-view/server.py`, `model-view/result_preview.py`, `model-view/static/`

All checks were read-only. No numerical analysis was rerun and no source files
were modified.

---

## 1. Verdict

The update resolves the earlier blocking issues:

- units are now explicitly native **cm / kN / kN·cm / MPa / rad**;
- the aggregate, per-case summary and NPZ files are versioned `2.0.0`;
- force quantities are separated into `reference_force_kN`, `total_force_kN`
  and `force_kN`, with `pushover_axis: "Z"`;
- file references are relative;
- complete interface topology, reference axes, stress/sliding offsets,
  per-Quad displacement and energy series are present;
- `Standard` cases are explicitly `curve_only`, and the `Vert` baseline now has
  a summary and fields;
- the exact old thrust-pair count (3,752) can be reproduced from
  `quad_interface_keys` plus `quad_face_interface_offsets`.

The remaining work is viewer integration plus a few small naming/alignment
caveats. The adapter is now implemented in `model-view/bridge_v2.py`,
`model-view/server.py` and `model-view/static/results.js`; the requirements
below remain the reference for later changes.

---

## 2. Resolution of the initial findings

| Initial finding | Status | Evidence |
| --- | --- | --- |
| Declared mm but actual cm | **Resolved** | `units.length = "cm"`, `units.displacement = "cm"`, `units.moment = "kN*cm"`. Coords still match HRX cm exactly. |
| Mixed force conventions | **Resolved** | `reference_force_kN`, `total_force_kN`, `force_kN = total_force_kN`; `pushover_axis = "Z"`. |
| No aggregate schema version | **Resolved** | Aggregate, session, summaries and NPZ all `2.0.0`. |
| Absolute file paths | **Resolved** | `files`, `baseline_case`, `summary.files` and session cases are relative. `metadata.model_file` is a relative filename. |
| Missing interface topology | **Resolved** | `quad_interface_keys`, face offsets/keys, `interface_node_keys/xyz/length/material`, `interface_e1/e3/origin`. |
| Missing stress/sliding cell metadata | **Resolved** | `transverse_offsets`/`sliding_offsets`; `interface_nrow/ncol/nspring` all 9/9/81; stress/force/area/valid arrays. |
| Orphan `Vert` baseline | **Resolved** | `pdelta_scour4_soft_Vert.summary.json` exists; aggregate `baseline_case` points to it. |
| Standard cases without fields | **Resolved by declaration** | Standard cases are `curve_only: true`; `files` are null. Their aggregate curves remain available. |
| No per-Quad deformation | **Resolved** | `fields/quad_displacements` `(N, 2520, 4, 3)`. |
| No energy series | **Resolved** | `elastic_energy`, `dissipated_energy` in every summary. |
| Pickle required | **Resolved** | The `.pkl` is optional; JSON + NPZ are sufficient. |

---

## 3. Verified v2.0.0 content

### 3.1 Identity and units

- `Bridge.hrx` SHA-256:
  `44b3d26087722b7755f5a46f95498ec13e328f4d8347e8e0efb3c07752d68c14`.
- All summaries declare the same `model_sha256`.
- `metadata.model_file` is now the relative original filename
  `Bridge_scour_3d_Distributed_PDelta.hrx`. The local file is `Bridge.hrx`;
  match by SHA-256, not filename.
- Units block:
  `length=cm`, `displacement=cm`, `force=kN`, `moment=kN*cm`,
  `stress=MPa`, `rotation=rad`.

### 3.2 Mesh and topology

For `Span2_Quarter`:

| Array | Shape | Verification |
| --- | ---: | --- |
| `mesh/node_keys` / `nodes_xyz` | `(3216,)`, `(3216,3)` | Match HRX to `~5e-12`; cm. |
| `mesh/quad_keys` / `quad_conn` | `(2520,)`, `(2520,4)` | Connectivity matches HRX exactly. |
| `mesh/quad_material_keys` | `(2520,)` | Match HRX material keys. |
| `mesh/quad_thickness` | `(2520,4)` | Match HRX exactly. |
| `mesh/quad_interface_keys` | `(2520,6)` | Six face keys, `-1` for unused. |
| `mesh/quad_face_interface_offsets` | `(15121,)` | Per-Quad, per-face offsets into the full face-to-interface list. |
| `mesh/quad_face_interface_keys` | `(13508,)` | Full face-to-interface list. |
| `mesh/interface_keys` / `interface_parents` | `(6762,)`, `(6762,2)` | Parent quads present. |
| `mesh/interface_node_keys` / `interface_node_xyz` | `(6762,2)`, `(6762,2,3)` | Length equals endpoint distance exactly; coords match HRX where the node is in the Quad mesh. |
| `mesh/interface_length` | `(6762,)` | Exactly `norm(node1-node0)`. |
| `mesh/interface_e1` / `interface_e3` / `interface_origin` | `(6762,3)` | Present; `dot(node1-node0, e1)` is positive for all interfaces, so node ordering matches `e1`. |
| `mesh/interface_nrow/ncol/nspring` | `(6762,)` | All are `9 / 9 / 81`. |
| `mesh/interface_restrained` | `(6762,)` | Present. |

**Exact thrust-pair reconstruction:** using the old rule “a pair exists only if
both opposite faces have exactly one interface” with
`quad_face_interface_offsets` reproduces **3,752** pairs, exactly the old
`Bridge.json` count. The raw `quad_interface_keys` alone gives 3,864 because
some faces have multiple interfaces; the offsets are required to apply the old
rule.

**Important:** 2,214 interfaces reference nodes with keys above 3,216 (up to
5,862). Those nodes are not in `mesh/node_keys`, but their coordinates are in
`mesh/interface_node_xyz` (available refs match HRX to `~5e-12`). A viewer
adapter must use `interface_node_xyz` (or extend the node map), otherwise about
one third of the interfaces will be dropped from thrust/interface views.

### 3.3 Steps and fields

| Case | Steps | Notes |
| --- | ---: | --- |
| `P_Delta_Vert` | 6 | Initial + 5 committed; baseline. |
| `P_Delta_Span1_Half` | 56 | Initial + 55 committed. |
| `P_Delta_Span1_ThreeQuarter` | 34 | Initial + 33 committed. |
| `P_Delta_Span2_Half` | 56 | Initial + 55 committed. |
| `P_Delta_Span2_Quarter` | 46 | Initial + 45 committed. |

For every P-Delta case:

- `steps/step_index` is contiguous from 0.
- `summary.curve.step` equals `steps/step_index`.
- `summary.curve.displacement_cm` equals `steps/displacement`.
- `summary.curve.displacement_mm` equals `displacement_cm × 10`.
- `summary.curve.load_factor` equals `steps/load_factor`.
- `summary.curve.force_kN` equals `summary.curve.total_force_kN`.
- `total_force_kN` equals `abs(reaction_z - reaction_z[0])` within `~1.1e-4 kN`.
- `summary.metrics.d_max_cm/mm` and `d_at_f_max_cm/mm` are consistent.
- final interface resultants/moments equal the final
  `springs/runtime_arrays/all_resultant_forces/all_bending_moments` exactly.
- all inspected numeric arrays are finite.

`elastic_energy` and `dissipated_energy` have a `null` initial value and finite
values thereafter. The existing viewer chart code filters non-finite points, so
this is compatible; consumers must not assume the initial energy is zero.

### 3.4 Stress and sliding arrays

| Array | Shape | Notes |
| --- | ---: | --- |
| `springs/transverse_force/phase/area/stress_valid/stress` | `(547722,)` | `6762 × 81`; offsets `(6763,)`, last `547722`. |
| `springs/sliding_force/phase/area/stress_valid/stress` | `(20286,)` | `6762 × 3`; offsets `(6763,)`, last `20286`. |
| `springs/runtime_arrays/all_resultant_forces/moments` | `(6762,3)` | Final step only. |
| `springs/runtime_arrays/quad_state` | `(2520,85)` | Final step only. |
| `springs/runtime_arrays/coulomb_state` | `(20190,38)` | Final step only; note this is not `6762 × 3`, so do not infer its layout from the sliding arrays. |

All `transverse_stress_valid` and `sliding_stress_valid` flags are true in the
inspected case.

### 3.5 Aggregate, session and per-case files

- `pdelta_soft_subgrade_phase4_results.json`:
  `schema_version = "2.0.0"`, units, metadata, `baseline_case`, `cases`,
  `summary`, `files`.
- `pdelta_soft_subgrade_phase4.session.json`:
  `schema_version = "2.0.0"`, units, model file/hash, `baseline_case`, and a
  nine-case list (five P-Delta + four Standard).
- Per-case summaries: `schema_version = "2.0.0"`, units, `pushover_axis`,
  metrics, curves, reactions, `files`, `curve_only`.
- All `files` entries that are non-null exist on disk and are relative.

---

## 4. Remaining caveats

### 4.1 The bridge source integration

**Resolved.** `model-view/server.py` now maps the bridge source to the v2
aggregate JSON and the viewer requests one analysis at a time. The old
`Bridge.json` is no longer required. `/api/results/bridge` returns schemaVersion
3 data, and the stress/interface endpoints use the v2 NPZ arrays.

### 4.2 Interface nodes outside the Quad node set

As noted in §3.2, 2,214 interfaces reference nodes above 3,216. The adapter
must use `interface_node_xyz` or merge those nodes into the map used by
`computeThrustLines`. Do not use `mesh/node_keys` alone.

### 4.3 `reference_force_kN` is not a reference load

In pushover cases it is the absolute vertical reaction (e.g. `1031 → 1265 kN`),
not a constant reference; in the `Vert` case it equals the total applied load
(`0 → 1031 kN`). The viewer should use `total_force_kN` (or `force_kN`) for the
pushover curve. Suggest renaming `reference_force_kN` to `reaction_z_kN` or
`base_reaction_kN`.

### 4.4 `P_Delta_Vert` aggregate arrays omit the initial step

The aggregate `cases.P_Delta_Vert` has 5 `disp_mm`/`force_kN` values starting at
`0.326 mm / 206 kN`; the summary curve has 6 values starting at `0`. The
`baseline_case` summary/fields are the authoritative 6-step source. Use the
baseline files if the initial state matters; otherwise document that aggregate
Vert arrays are committed-steps only.

### 4.5 Summary model filename vs local filename

Summary `metadata.model_file` is the original
`Bridge_scour_3d_Distributed_PDelta.hrx`; the local file is `Bridge.hrx`. The
hash matches. Resolve by SHA-256 or accept an alias; do not require the filename
to match.

### 4.6 Standard cases are curve-only by declaration

Aggregate `cases` include four `Standard_*` curves, but `curve_only: true` and
`files` are null. The summary table has Standard metrics, but no per-case
summary/fields files. The viewer should offer response curves for them and
disable deformed-shape/thrust/stress pages.

### 4.7 Pickle remains optional

The `.pkl` is small and duplicates model-point/foundation details. It is not
needed for the viewer. Avoid loading it; the JSON + NPZ are sufficient.

---

## 5. Adapter mapping (for the next agent)

If the viewer is adapted, use this mapping:

### Mesh

- Nodes: `mesh/nodes_xyz`, keys `mesh/node_keys`; cm.
- Quads: `mesh/quad_conn`, `mesh/quad_material_keys`, `mesh/quad_thickness`;
  merge normals/loads/restraints from `Bridge.hrx`.
- Materials: `Bridge.hrx` (`mesh.materials`).
- Interfaces: `interface_keys`, `interface_node_keys`, `interface_node_xyz`,
  `interface_length`, `interface_e1/e3/origin`, `interface_material_keys`,
  `interface_nrow/ncol/nspring`, `interface_restrained`.
- Thrust pairs: for each Quad, pair face 0↔2 and 1↔3 only when
  `quad_face_interface_offsets` shows exactly one interface on each face.
  This gives 3,752 pairs.

### Steps

- `interfaceOrder`: sorted `interface_keys`.
- `interfaceResultants`: `fields/interface_resultants` + `fields/interface_moments`
  (moments already `kN·cm`).
- `displacements`: `fields/node_displacements` in cm.
- `quadDisplacements`: `fields/quad_displacements`; encode for the existing
  `decodeQuadDisplacements` path if the viewer needs joint opening.
- `loadFactor`: `steps/load_factor`.
- `controlDisplacement`: `summary.curve.displacement_cm` (or
  `steps/displacement`).
- `maxDisplacement`: max norm of `fields/node_displacements` (cm).
- `appliedVerticalForce`: `summary.curve.total_force_kN`.
- `reactions`: `steps/reactions[:,0:3]`.
- `elasticEnergy` / `dissipatedEnergy`: summary curve, skipping the initial
  `null`.
- `step`: `steps/step_index`.

### Stress/interface views

- Use `transverse_offsets` / `sliding_offsets` with `nrow/ncol/nspring` to
  slice the arrays per interface.
- Use `transverse_stress_valid` / `sliding_stress_valid` to hide invalid cells.
- Final-step only; intermediate steps still have resultants but not spring
  stress histories.

### Curves and cases

- P-Delta cases: full fields + curves.
- Standard cases: curves only; no deformed shape/thrust/stress.
- `Vert`: baseline; use `baseline_case` summary/fields if initial state or
  full 6-step curve is needed.

---

## 6. Acceptance checklist

- [ ] `RESULT_SOURCES["bridge"]` points at the v2.0.0 aggregate JSON or a
      dedicated loader.
- [ ] Viewer catalog lists `3D Bridge` again.
- [ ] `GET /api/results/bridge` returns a valid schemaVersion 3 payload.
- [ ] Mesh loads from HRX + NPZ and matches HRX nodes/quads/materials.
- [ ] Interface node map includes `interface_node_xyz` nodes.
- [ ] Thrust pairs reproduce 3,752 with the single-face rule.
- [ ] Deformed shape uses `node_displacements` (cm) and, if supported,
      `quad_displacements`.
- [ ] Control displacement is shown in cm; metrics use `d_max_cm`/`d_max_mm`
      explicitly.
- [ ] Force curve uses `total_force_kN`, not `reference_force_kN`.
- [ ] Energies skip the initial `null` without treating it as zero.
- [ ] Standard cases are curve-only.
- [ ] Vert baseline resolves to the baseline summary/fields.
- [ ] Stress contours use offsets + 9×9 cells and valid flags.
- [ ] `metadata.model_file` is resolved by SHA-256 or alias, not exact name.
- [ ] No viewer code loads the `.pkl`.
- [ ] Tests cover all four P-Delta cases and the Vert baseline.

---

## 7. Open questions

1. Should `reference_force_kN` be renamed to `reaction_z_kN` /
   `base_reaction_kN`, or is its current meaning intentional?
2. Should aggregate `cases.P_Delta_Vert` include the initial step (6 values) to
   match the baseline summary?
3. Should Standard curves be exposed in the viewer, or hidden entirely?
4. Are stress contours and selected-interface spring details in scope for the
   first adapter pass, or can they remain disabled?
5. Does the viewer need per-Quad joint opening in the first pass, or is
   shared-node displacement enough?
