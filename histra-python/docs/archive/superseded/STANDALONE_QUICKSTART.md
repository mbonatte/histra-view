# Run an unrun HRX model entirely in Python

This workflow does **not** read a C# `.Results` database. It loads an
unrun `.HRX`, executes the gravity analysis (`Vert`), keeps the complete
committed constitutive state in memory, and then runs the chained Live Load
analysis.

Both already locked/solver-ready HRXs and the supported unlocked masonry
Quad/Restraint HRXs are accepted. When `IsLocked=false`, `GDL=0`, or generated
springs/interfaces are absent, Python automatically runs the translated C#
`ModelManager.PrepareModel` stage before starting Vert.

## Geometry-only or unlocked HRX files

For the supported topology, the command generates in memory:

- seven generalized DOFs per Quad;
- Quad diagonal springs;
- exact full-edge Quad–Quad interfaces;
- fixed Quad–Restraint interfaces;
- transverse, in-plane sliding, and out-of-plane sliding springs;
- Quad and Interface afference matrices.

Partial polygon contacts, other computational element families, slave/partition
models, and unsupported restraint behavior fail explicitly. See
`RAW_HRX_PREPROCESSING.md` for the exact supported subset and validation data.

## Install

From the directory containing `run_vert_live.py` and the `histra/` folder:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

```bash
python run_vert_live.py /path/to/model.HRX --output-dir python-results
```

The command automatically selects an analysis named exactly `Vert` and prefers
an analysis named exactly `LiveLoad_1`. If the model contains several Live Load
analyses, select one by key or exact name:

```bash
python run_vert_live.py /path/to/model.HRX \
  --live-analysis LiveLoad_1 \
  --output-dir python-results
```

or:

```bash
python run_vert_live.py /path/to/model.HRX \
  --vert-analysis 1 \
  --live-analysis 22 \
  --output-dir python-results
```

No `.Results` argument is used or required.

## Files to compare

The easiest files for a software comparison are:

- `vert_final_node_displacements.csv`
- `live_load_final_node_displacements.csv`
- `vert_steps.csv`
- `live_load_steps.csv`

### Node displacement columns

- `ux`: global X-direction displacement
- `uy`: global Y-direction displacement
- `uz`: global Z-direction displacement
- `x`, `y`, `z`: original node coordinates
- `deformed_x`, `deformed_y`, `deformed_z`: coordinate plus displacement
- `displacement_magnitude`: `sqrt(ux^2 + uy^2 + uz^2)`

The values use the length unit of the HRX model. The HRX format used by this
package does not expose a reliable unit label, so the CSV deliberately does not
invent one.

### Reaction columns

- `histra_reaction_sum_x/y/z`: direct equivalents of HiStrA `ReactionSum`
  `R1/R2/R3`; use these for comparison with the software.
- `total_support_reaction_x/y/z`: the opposite sign, representing the
  conventional support force acting on the structure.
- `incremental_support_reaction_x/y/z`: support reaction relative to step 0 of
  that analysis. In the Live Load file, this subtracts the final Vert reaction
  and therefore isolates the reaction added by Live Load.
- The corresponding `*_magnitude` column is the vector magnitude.

Reaction values use the force unit of the HRX model.

### Convergence and displacement columns

- `convergence_result_code`: positive means that step converged; a negative value
  describes the stopped/uncommitted trial step. It is not the command's process
  exit code.
- `monitored_displacement`: graph/control output selected by the analysis.
- `max_element_displacement`: largest model element displacement, used by the
  `maxU` termination criterion. It can differ from the monitored displacement.

## Meaning of step 0

- Vert step 0 is the virgin, unloaded state.
- Live Load step 0 is the final committed Vert state.

Therefore `live_load_steps.csv` contains both the total gravity-plus-live
reaction and the incremental Live Load contribution.

## Long runs and stopping conditions

`solver.log` is updated while the analysis runs. The completed Vert output is
written before Live Load starts. ArcLength Live Load analyses can take much
longer than Vert.

A negative internal completion code is not automatically a convergence failure.
For the supplied benchmark, code `-3` at attempted step 88 is the configured
maximum-displacement stop after 87 valid committed steps. `run_summary.json`
classifies this as `completed_at_configured_displacement_limit` when the model's
`maxU` has actually been reached.

## Unsupported cases

The command fails explicitly for unsupported P-Delta paths or unsupported load
types. A Live Load analysis must identify the selected Vert analysis through
its `InitialAnalysisKey`; otherwise the command stops rather than chaining the
wrong analyses.

## Performance backend

Install the supplied requirements so that Numba is available:

```bash
python -m pip install -r requirements.txt
```

The solver automatically compiles and batches compatible transverse hysteretic
springs. `solver.log` and `run_summary.json` report either
`numba_compiled_batch` or `scalar_python`.

The first process may spend a few seconds compiling kernels. Numba caches them
for subsequent processes. For the supplied benchmark, the measured full
`Vert -> LiveLoad_1` runtime changed from 267.46 seconds to 15.83 seconds with an
empty JIT cache and 13.10 seconds with a warm cache on the audit machine.

To force the slower scalar path for diagnosis:

```bash
HISTRA_DISABLE_COMPILED_SPRINGS=1 python run_vert_live.py model.HRX \
  --output-dir scalar-results
```

See `PERFORMANCE_PROFILE.md` for the full profile, correctness checks, and
measurement commands.

## Performance and Numba cache

The supported masonry model uses Numba-compiled preprocessing and nonlinear-domain kernels. The first run on a new Python/Numba/platform combination compiles these kernels and may be noticeably slower. Numba stores the generated machine code in its disk cache; later runs are substantially faster.

For a fair steady-state timing, run the same model twice and time the second run:

```bash
python run_vert_live.py model.HRX --output-dir warmup-results --quiet
python run_vert_live.py model.HRX --output-dir timed-results --quiet
```

The 560-DOF reference model measured approximately 21.3 seconds of solver phases with an empty cache and 6.1 seconds after caching on the audit environment.

To produce a profile for another model:

```bash
python -m cProfile -o model.prof \
  run_vert_live.py model.HRX --output-dir profile-results --quiet
python -m pstats model.prof
```

To diagnose the compiled backend against the scalar fallback:

```bash
HISTRA_DISABLE_COMPILED_SPRINGS=1 \
python run_vert_live.py model.HRX --output-dir scalar-results --quiet
```

### Split or nonconforming masonry edges

The current preprocessor supports collinear T-junctions where a long Quad edge is divided across shorter neighboring Quad edges. No manual mesh consolidation is required for this case. General non-collinear polygon intersections remain unsupported and are reported explicitly.

## HRX-defined chains with an interface material change

For analyses such as `Vert → scour_1 → LiveLoad_1`, use the in-memory session
API. It follows each analysis' `InitialAnalysisKey` and does not use a
`.Results` database between analyses.

```python
from histra.io.hr_loader import load_model
from histra.solver import AnalysisSession

model = load_model("model.hrx")
session = AnalysisSession(model, on_log=print)

session.run("Vert")
session.change_interface_materials(
    [359, 360, 361, 362],
    147,  # Soil_removed
    preserve_committed_state=True,
)
session.run("scour_1")
session.run("LiveLoad_1")
```

The HRX remains authoritative for methods, combinations, convergence settings,
predecessor keys and stopping criteria. See
`ANALYSIS_CHAIN_AND_INTERFACE_MUTATION.md` for the exact state-transfer rules.
