# Native simulation results (schema 2.1.0)

`ResultsWriter` exports the following numerical schema either inside a single
[`.histra` study bundle](histra-bundle-format.md) or as a summary JSON and
compressed NumPy dataset per analysis.
HDF5 is optional; requesting it without `h5py` produces NPZ with a warning.
The schema version is independent of the package version.

```python
from histra import AnalysisSession, SimulationResults, load_model

session = AnalysisSession(load_model("bridge.hrx"))
session.run_to("LiveLoad_1")
session.export_bundle("results/bridge.histra")
readers = SimulationResults.load_session("results/bridge.histra")
try:
    case = readers["LiveLoad_1"]
    displacement_mm, total_force_kN = case.get_pushover_curve()
    corners_cm = case.get_quad_displacement_field(step=-1)
    springs = case.get_interface_springs(int(case.mesh_interface_keys[0]))
finally:
    for case in readers.values():
        case.close()
```

## Units and curve semantics

All mesh coordinates, thicknesses, lengths, global displacement translations,
and projected translations are **cm**. Rotations in `fields/U` are radians;
that vector contains assembled generalized DOFs, not shared-node translations.
Interface resultants are kN and interface moments are kN·cm, in each interface's
local reference frame. Exported spring stress is MPa. Raw runtime state arrays
retain internal solver conventions; their force columns are kN, even where
internal variable names say “stress”. Spring stress is `10 * force / area_cm2`.

The summary declares these units under `metadata.units`. Dense datasets also
contain `metadata/schema_version` and JSON-encoded `metadata/units` scalars.
`steps/displacement` stays in cm. Summary curves contain both
`displacement_cm` and `displacement_mm`, and metrics contain both `d_max_cm` /
`d_max_mm` and `d_at_f_max_cm` / `d_at_f_max_mm`.

`pushover_axis` selects the largest absolute change from the initial reaction,
with ties preferring Z, X, then Y. If every change is at most 1e-4 kN,
`pushover_axis` is `resultant` and the force is the absolute reaction magnitude.

- `curve.total_force_kN` is the selected reaction change, or resultant fallback.
- `curve.reference_force_kN` is the absolute selected-axis reaction before
  baseline subtraction, or the absolute resultant for the fallback.
- `curve.load_factor` is the independent dimensionless solver load factor.
- `curve.force_kN` remains an alias for `total_force_kN`; `f_max_kN` uses it.

Control displacement remains the solver's recorded control value. It is not
rebased at each stage. Reaction changes are rebased at the first output state.
Only the initial state and committed steps enter the exported histories;
failed trial steps remain represented in execution outcome/status metrics.

Available elastic/dissipated energy values are exposed in summary curves in
kN·cm, with `null` for unavailable states (including initial snapshots).
Dense energy series are included only when every output state has a value.
An absent initial energy must not be interpreted as zero.

## Named model-point histories in summary JSON

Every newly captured static execution includes a `model_points` section in its
summary, including summary-only JSON and summaries embedded inside `.histra`.
It contains all defined supported Node/Quad monitoring points, independently of
which point controls the pushover curve or is active for that analysis.

`model_points.step` is identical to `curve.step`: initial state followed by
committed states, with failed trial steps excluded. Each entry in
`model_points.points` contains:

- `key`: the ModelPoint key (C# `ParentKey`), distinct from `element_key`;
- `name`, `description` and a plotting `label`, preserving HRX text when present;
- `element_type`, `element_key`, `id_vertex` and undeformed `coordinates_cm`;
- `active` and `control` flags for that analysis;
- `displacement_cm` and `displacement_mm`, each containing signed `ux`, `uy`,
  `uz` lists aligned with the shared step list;
- `available` and `error`, with null displacement data if a point cannot be
  projected. Missing/unsupported data is never replaced with a zero history.

Node points use the existing C# shared-node average. Quad points use C#'s centre
or specified corner projection. Histories are calculated from the original
in-memory displacement vectors, avoiding a second projection from rounded dense
exports. They retain absolute stage displacement, including the predecessor
initial state; no stage rebasing or absolute-value transform is applied.
Model-point labels, locations, analysis flags and histories are captured at the
analysis boundary, so later changes do not alter predecessor summaries. These
are static response histories, not modal mode-shape histories.

For example, plot a point's vertical movement using only its JSON summary:

```python
import json
import matplotlib.pyplot as plt

with open("bridge_Vert.summary.json", encoding="utf-8") as file:
    summary = json.load(file)
monitoring = summary["model_points"]
point = next(point for point in monitoring["points"] if point["key"] == 90)
if point["available"]:
    plt.plot(monitoring["step"], point["displacement_mm"]["uz"], label=point["label"])
    plt.xlabel("Step")
    plt.ylabel("Vertical displacement (mm)")
    plt.legend()
```

`SimulationResults.model_points` lists these point entries, and
`results.get_model_point_curve(90, component="uz", unit="mm")` returns
`(steps, displacement)` without loading dense arrays. Components are `ux`, `uy`
or `uz`; units are `cm` or `mm`. Lookup uses the ModelPoint key, so multiple
points on one element remain distinct. Older summaries return an empty list and
raise `KeyError` for missing curves. Packing an older summary into a bundle does
not create missing histories. Summary size grows with point and step counts.

## Topology and deformation

Topology arrays use ascending entity-key order. Dynamic interface arrays and
spring spans use the same interface order, regardless of runtime record order.
The shared-node mesh contains Quad-connected nodes. Auxiliary contact endpoints
are described separately by `mesh/interface_node_keys` and
`mesh/interface_node_xyz` `(N_interfaces, 2, 3)`.

Quad metadata includes material keys, four thicknesses and six face interface
keys. `mesh/quad_interface_keys` has shape `(N_quads, 6)` with `-1` for an empty
face and the first key for an active face. A face may contain **multiple**
partial-edge contacts; use the lossless CSR arrays
`mesh/quad_face_interface_offsets` `(6*N_quads+1,)` and
`mesh/quad_face_interface_keys` for general topology. Flatten faces in Quad
order, then native face order 0..5. C# `DrawCurvaPressioni` considers opposite
faces (0,2), (1,3), (4,5), only when each face has exactly one interface, and
also applies its displayed-element group filter.

Interface metadata includes endpoint keys, length, material key, reference e1
and e3, reference origin, nrow, ncol, actual transverse fibre count and the
restraint flag. `mesh/interface_nspring` is the **actual primary transverse
fibre count**. The model's internal `interface.nspring` is a legacy alias for
`ncol`; using it as a fibre count would truncate the grid. No model field is
changed by export.

`fields/node_displacements` contains the existing shared-node average.
`fields/quad_displacements` `(N_steps, N_quads, 4, 3)` preserves independent
corner translations using the existing C#-parity projection, including the
seventh Quad DOF. It is available even if shared-node projection is disabled.

## Stage-end constitutive state

`AnalysisSession.run` copies export topology and spring state at the analysis
boundary. Exporting a predecessor after running another stage or changing
interface materials uses that predecessor's snapshot. This adds retained
array storage per execution, without changing constitutive integration.

`springs/transverse_offsets` and `springs/sliding_offsets` are uint32 prefix
sums with `N_interfaces+1` entries. Each span slices the corresponding
`force`, `stress`, `phase`, `area` (cm²) and `stress_valid` arrays. A zero-area
sliding spring retains its force, with zero stress as a placeholder and
`stress_valid = 0`; consumers must mask that stress. Transverse values follow primary fibre
row-major order. Sliding values follow in-plane, out-of-plane 0, out-of-plane 1
slots when present. Aliased spring objects occupy repeated component slots;
the raw runtime Coulomb array still deduplicates them. These are **committed
stage-end snapshots**, not per-step spring histories.

Standalone executions without a captured export snapshot use the supplied
model's current runtime. Export these before advancing that model. Inactive
runtimes have no constitutive snapshot arrays; readers must check key presence.

## Strain, plastic demand and damage states

Schema 2.1 adds named response arrays to the committed stage-end snapshot.
They are included automatically in NPZ, HDF5 and `.histra` exports. They are
not additional per-step fibre histories. Existing displacement and interface
resultant histories keep their existing step dimensions. The native `.Results`
option retains its C# schema and saved-state conventions without extra columns.

Use prefixes `springs/transverse_`, `springs/sliding_` and `springs/quad_` with
the following names. Interface prefixes follow their existing CSR spans; Quad
arrays follow `mesh/quad_keys` order. There is one value per spring slot.

| Name | Type / units | C# definition |
|---|---|---|
| `displacement` | float64, cm | Committed spring `U` |
| `length` | float64, cm | Native spring `Length` |
| `initial_stiffness`, `tangent_stiffness` | float64, kN/cm | Initial and committed tangent stiffness |
| `spring_type` | uint8 | Native enum: LinearElastic=1, Hysteretic=8, Coulomb03=12 |
| `strain` | float32, dimensionless | `Spring.GetStrain()`: `U / Length` |
| `plastic_displacement` | float64, cm | Law-specific `GetUp()` |
| `plastic_strain` | float32, dimensionless | `GetStrainPlastic()` |
| `plastic_ratio` | float32 | Law-specific `GetUpOverUr()` |
| `plastic_ratio_is_normalized` | uint8 | Valid dimensionless demand; zero for the Hysteretic unlimited-displacement branch |
| `is_plastic`, `is_ruptured`, `is_slipping` | uint8 | Native current phase classification |

Each of `strain`, `plastic_displacement`, `plastic_strain` and `plastic_ratio`
has a matching `<name>_valid` uint8 array. Native undefined or overflowing getter
values become finite zero placeholders with validity zero. Consumers **must use
the masks**; a placeholder is not evidence of zero deformation. Input doubles
remain available to reconstruct the native expression where required.

A significant native limitation is preserved: `SetQuadTrasvSpring` leaves many
Hysteretic transverse fibres with `Length == 0`. Consequently, their dimensional
opening and plastic displacement can be valid while strain is undefined.
The exporter does not replace this length with interface length or change the
solver's spring definition. Sliding reference lengths and the diagonal spring
length retain their native definitions too.

For Hysteretic springs, `GetUp()` is the nonnegative excess of `abs(U)` above
`abs(Fy / K)`, choosing the positive/negative yield force by the sign of U.
For Coulomb03 it is signed `U - F / K`, with C#'s small plastic-displacement
threshold. Elastic spring plastic responses are zero. These display getters
are distinct from raw saved Coulomb plastic-history fields such as `Up1/Up2`.
Use of the original double inputs and final float32 conversion follows the C#
getter boundaries; formulas are tested against executed original C# getter bodies.

`plastic_ratio` is not bounded to [0,1]. Hysteretic springs with a directional
ultimate limit at least 100000 return plastic **displacement**, as C# does;
`plastic_ratio_is_normalized` distinguishes that branch. Signed Coulomb ratios
are preserved. `Interface.GetValueMap` separately clips negative plastic values
to zero for display; these arrays retain raw getter values for other consumers.

There is no universal scalar damage variable in these C# spring laws.
`phase` retains the exact native code: Elastic=0, Plastic_t=1, Plastic_c=2,
Unload_t=3, Unload_c=4, Reload_t=5, Reload_c=6, Rupture=7, RuptureTraz=8,
RuptureComp=9, Slip=10. `is_plastic` identifies phases 1/2, `is_ruptured` 7/8/9
and `is_slipping` 10. These describe the current state, not accumulated damage
or permanent plastic history. Input `damfc` coefficients are not a computed
damage percentage.

Sliding and Quad arrays also expose committed Coulomb03
`plastic_tension_indicator` and `plastic_compression_indicator`, with
`plastic_history_valid`. This validity is zero for laws without those native
history flags; it must not be interpreted as a history of no yielding.
Quad diagonal springs additionally have force, stress, phase, area and stress
validity arrays under their own prefix.

```python
fibres = results.get_interface_springs(interface_key, "transverse")
strain = fibres["strain"][fibres["strain_valid"].astype(bool)]
plastic_opening_cm = fibres["plastic_displacement"]
ruptured_now = fibres["is_ruptured"].astype(bool)
diagonals = results.get_quad_springs()  # all Quads, or pass one Quad key
```

`metadata/spring_response` and summary `metadata.spring_response` describe units,
validity handling and temporal scope. Existing schema 1/2.0 files remain readable;
missing new fields are not fabricated. Re-export from a newly captured execution
to obtain them; packing old arrays into `.histra` alone cannot add missing state.

## Portable sessions and compatibility

In the legacy split-file layout, `export_session` also creates `<bundle>.session.json` with schema version, units,
model filename/hash and every exported analysis's relative summary/fields path.
It copies the source HRX beside the manifest and refuses to overwrite a different
model with the same filename. A summary-only case has `curve_only: true` and a
null fields reference; baseline stages are indexed like every other stage.
The returned Python mapping of analysis names to created paths is preserved.
Rerunning an analysis exports its most recent execution.

Single-analysis manifests use the source model's basename; callers distributing
that pair separately should include the source HRX beside it. NPZ data can be
read without HRX or pickle. Optional application-specific metadata remains the
caller's responsibility, including any paths it embeds.

`SimulationResults.load` retains legacy schema 1 summary/array access and sibling
file discovery. Version 2 readers honor declared field references and reject
missing files or unsupported summary schema versions. Legacy `_mm` summary
values are returned as stored; old schema 1 exports affected by the unit bug
must be re-exported for corrected values. New topology helpers raise `KeyError`
when their arrays are absent in older files.

The external bridge aggregate, existing bridge bundles, viewer adapters and
viewer HTTP endpoints are application artifacts. This schema does not rewrite
those artifacts or synthesize missing Standard analyses. Re-export the desired
analyses and update the viewer to consume the session index and explicit units.

For C# application database output, see the [native SQLite export guide](csharp-results-export.md). It requires capture during solving and cannot be reconstructed from this compact viewer schema.
