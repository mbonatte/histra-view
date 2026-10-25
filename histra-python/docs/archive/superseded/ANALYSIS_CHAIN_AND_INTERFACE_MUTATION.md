# In-memory analysis chains and interface material mutation

## Scope

The solver now supports a C#-compatible analysis boundary in which selected
interfaces are rebuilt with a new `MasonryMaterial` and the next HRX analysis
starts from the previous committed nonlinear state without a `.Results`
database round trip.

The HRX analysis definitions remain authoritative for:

- analysis keys and names;
- `InitialAnalysisKey` dependencies;
- load combinations and load functions;
- integration and solution methods;
- convergence and termination settings.

The orchestration layer only decides which HRX target to run and which
interface-material mutation to apply before a particular analysis.

## Python API

```python
from histra.io.hr_loader import load_model
from histra.solver import AnalysisSession

model = load_model("model.hrx")
session = AnalysisSession(model, on_log=print)

# The HRX dependency chain for LiveLoad_1 is read from InitialAnalysisKey.
print([(a.key, a.name) for a in session.dependency_chain("LiveLoad_1")])

session.run("Vert")

# Rebuild only the affected foundation interfaces and transfer the committed
# Vert spring history to the new Soil_removed definitions.
session.change_interface_materials(
    interface_keys=[359, 360, 361, 362],
    material_key=147,
    preserve_committed_state=True,
)

session.run("scour_1")
session.run("LiveLoad_1")
```

A boundary callback can drive the complete HRX dependency chain:

```python
def before_analysis(session, analysis):
    if analysis.name == "scour_1":
        session.change_interface_materials(
            [359, 360, 361, 362],
            147,
            preserve_committed_state=True,
        )

results = session.run_to("LiveLoad_1", before_analysis=before_analysis)
```

## Material key semantics

- `material_key == 0`: rebuild the interface from the two parent element
  materials, matching the default C# path.
- `material_key != 0`: use that material law on both sides of the interface,
  matching `InterfaceOperations.ReSetInterfaces`.
- For a Restraint–Quad interface with a custom material, the transverse spring
  is cloned from the non-restraint side, matching the special C# branch.

## State-transfer semantics

The operation is not a virgin reset. It follows the C# order:

1. Capture the committed predecessor state.
2. Rebuild spring definitions from the new material.
3. Restore committed deformation, force, phase, extrema, plastic/slip history,
   unloading/reloading history, normal force and dissipated energy.
4. Preserve the committed `InterfaceState` and global displacement.
5. Invalidate all compiled constitutive arrays.
6. Rebuild the Numba runtime once when the next analysis starts.

The new immutable definition remains authoritative for stiffness, material
coefficients and envelope geometry. Persisted history fields such as `Fy`,
`Umax`, `Up`, phase and load indicators are transferred exactly as C# restores
`SpringStates`.

## Atomicity and rollback

A multi-interface mutation is atomic. If one interface is absent, changes
spring family, or cannot accept the predecessor state, every selected
interface is restored to its pre-mutation definition and state. The compiled
runtime is invalidated on both success and failure.

## Current boundary

This implementation handles material changes **between committed analyses**.
C# `StageDefinition` changes inside an individual LoadControl step are a
separate feature and are not silently treated as analysis-boundary mutations.
