# C# HiStrA `.Results` database export

Native SQLite output is available alongside `.histra` and split JSON/NPZ/HDF5
exports. Enable native capture **before** running an analysis:

```python
from histra import AnalysisSession, load_model, compare_csharp_results

session = AnalysisSession(load_model("bridge.hrx"), capture_csharp_results=True)
session.run_to("LiveLoad_1")
path = session.export_csharp_results("results/bridge.Results")
```

The default analysis policy still applies; configure the appropriate equilibrium
and solver strategy policies for your model as explained in the analysis guides.
Enabling capture does not change constitutive formulas, convergence settings or
the compiled execution requirement.

`session.export_analysis(..., format="results")` exports one captured analysis;
`session.export_session(..., format="results")` writes one database containing
the latest execution of every analysis. Both return `{"results": path}` entries
in their existing return mappings. `format="csharp"` and `format="result"` are
aliases. Native exports require `tier="all"`. `.Results` is the native suffix;
the `.Result` spelling is accepted too. The existing default export formats are
unchanged.

## Exactness contract

The exporter uses the SQL schema from C# `ModelLibrary/SQLite/Create.sql`, bound
by a source fingerprint and comparisons with the checked-in native databases.
It writes native column names, SQLite affinities, native spring identity enums,
local DOF ordering and native units. Values are bound directly to SQLite without
text formatting or conversion through the float32 viewer arrays. Fields left
NULL by the C# serializer remain NULL; they are not replaced with Python-only
state or zeros. In particular, `SpringStates.E`, `Ed` and `Eel` remain NULL even
though Python separately tracks spring energy.

These are different claims:

- **Serialization parity:** given the same captured records, preserve their
  stored values and schema. Native fixture records round-trip with every stored
  numeric bit and NULL intact. Spring mappings are checked against persisted
  native constitutive records.
- **Solver parity:** a new Python run can produce numerically different values
  from C#, including differences due to sparse backends and nonlinear branches.
  Matching the file format cannot make those values bit-identical.
- **Whole-file identity:** SQLite page allocation, transaction history and native
  parallel insertion order affect file bytes and surrogate `Id` values. The
  exporter does not promise identical file hashes, even for equal physical data.

To demand exact stored-value equality with a particular C# reference before
publishing an export:

```python
path = session.export_csharp_results(
    "results/bridge.Results",
    reference_path="reference/bridge.Results",
)
```

A schema or value mismatch raises `ResultsStateError` and preserves the previous
destination. The comparison has **zero tolerance**, including the binary64
representation of every returned REAL. It compares all tables and records in
both files, so the reference must contain exactly the selected analyses.
For independent checking:

```python
counts = compare_csharp_results(path, "reference/bridge.Results")
```

Native interface insertion is parallel, making surrogate `Id` assignment
unstable. The default comparison excludes only that column; every physical
identity, analysis, combination, step and state field participates. Add
`include_row_ids=True` to require identical IDs too. This is a database-content
comparison, not a file-byte comparison. Older native databases without the
`SpringStatesTmp` table have a different schema and fail strict comparison.

## Capture and supported scope

Capture currently supports the existing static masonry Quad/Interface solver
with Hysteretic, Coulomb03 and LinearElastic springs, inactive NodeC DOFs and
fully fixed explicit restraints. Active NodeC states and other explicit
restraint types fail closed because their full native state is not retained by
this implementation. Modal capture is rejected before solving; other unsupported
mechanics remain subject to the existing solver capability checks. This is not
universal C# application feature support. Opening the generated file in the
Windows C# graphical application still requires separate integration validation.

Capture runs at step 0 and after committed constitutive updates, before
integrator domain changes. It honors `analysis.step_save` for public records,
including `QuadStates`, `InterfaceStates`, `NodeCStates`, `RestraintStates`,
`DisplModelPoints`, reactions/energies and `SpringStatesTmp`. Full `SpringStates`
and zero-based `DynamicVectorsState` are saved at the last captured committed
state. The latter retains C#'s explicit combination-1 convention. Aliased spring
slots are serialized separately as C# does. Failed trial states are never saved;
if an analysis stops early, the exported state is its last captured committed
state (or its initial state). Analysis outcome metadata remains in the Python
execution and `.histra` summaries; the native schema has no corresponding table.

Static model-point velocities, accelerations, dynamic-vector velocities and
`ReactionSumStates.Et/Ei/Evd` are zero, matching C# static output. Fixed-restraint
translations are zero by their fully fixed DOF invariant. No source HRX is
embedded: distribute the matching HRX separately, as with C# output. Existing
typed readers in `histra.io.results_reader`, such as `read_analysis_metadata`,
`read_quad_states` and `read_spring_states`, can read the database.

Native state capture retains a dictionary record for every saved spring at every
saved step; this can consume substantial memory. It is disabled by default.
The lightweight `.histra` viewer export is still available and does not enable
native capture. Old NPZ/`.histra` files and uncaptured executions cannot be
converted into complete native output because they lack per-step constitutive
history and some native double-precision state. Export rejects these inputs
instead of fabricating missing values.

Writing uses a sibling temporary database, SQLite integrity verification and
atomic replacement. Optional reference comparison happens before publication.
