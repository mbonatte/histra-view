# Computational model preprocessing

Python now contains the masonry Quad/fixed-Restraint subset of C#
`ModelManager.PrepareModel`. An unlocked HRX with geometry, materials,
restraints, and analyses can be converted in memory into the springs,
interfaces, DOFs, and afference matrices required by the nonlinear solver.

See the project-root `RAW_HRX_PREPROCESSING.md` and
`PREPROCESSING_FINAL_REPORT.md` for the supported topology, C# source mapping,
benchmark measurements, and remaining limitations.

## Public API

```python
from histra.io.hr_loader import load_model
from histra.solver.model_manager import ModelManager

model = load_model("model.HRX")
report = ModelManager.prepare_model(model)
```

`solve_static_nonlinear` calls this automatically when readiness validation
finds missing computational objects. Pass `auto_prepare=False` to disable that
behavior.

## Benchmark command

```bash
python -m histra.tools.benchmark_preprocessing \
  --reference histra/model-output/model.hrx \
  --raw /path/to/unlocked/model.HRX \
  --run-vert \
  --output preprocessing_metrics.json
```
