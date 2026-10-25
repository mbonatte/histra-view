# Feature Support Status

| Feature | Status | Evidence/constraint |
|---|---|---|
| HRX parsing for supplied models | Supported | Both benchmark models load |
| Unlocked masonry HRX preprocessing | Supported for validated Quad/fixed-Restraint topology | Port of `ModelManager.PrepareModel`; creates DOFs, interfaces, springs, afference |
| Partial/general polygon preprocessing | Unsupported | Exact full-edge contacts only; fails explicitly |
| LoadControl | Supported for selected path | Vert executes five steps; parity after step 1 remains incomplete |
| ArcLength, selected model points | Supported for Live Load reference | 87 committed C# steps within 1e-4 |
| Chained Vert → Live Load restart | Supported | Complete state plus C# baseline-force behavior |
| Line loads on Quad | Supported for supplied benchmark | Total vertical resultant 2.88; step path accepted |
| Work convergence | Supported | C# combined-correction semantics reproduced |
| Hidden InitialInterpolated dispatch | Compatibility mode supported | Base no-op search used for reference parity |
| Quad/interface Coulomb coupling | Supported | Exact-state diagnostics match forces/phases |
| Hysteretic springs | Supported for benchmarks | Exact under C# displacement history |
| Complete trial/step rollback | Supported | Fingerprint and failure-path tests |
| Final C# database restart | Supported | Complete predecessor state restored losslessly |
| Intermediate database restart | Explicitly unsupported | Compact rows omit required history |
| Self-weight/gravity | Supported for Vert benchmark | Initial response exact |
| Sparse factorization reuse | Supported | Invalidated on matrix changes |
| P-Delta | Unsupported | Both selected analyses declare `None` |
| ALS | Rollback infrastructure tested | Not used by selected Live Load reference |
| Other load families | Incomplete | Unsupported cases must raise explicitly |
| Modal/dynamic analyses | Unsupported/incomplete | Outside selected benchmarks |
| C#-compatible result database writer | Unsupported | Reader/benchmark only |
