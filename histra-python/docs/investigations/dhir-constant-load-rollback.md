# Dhir constant-load failed-step rollback

The later [ten-step comparison](dhir-constant-load-ten-step-parity.md) avoids this rollback branch and matches all response fields. It identifies a separate native history-restoration omission after reopening the saved model; full history parity remains gated on that value.

## Confirmed native behavior, 2026-10-14

The user reran the separate instrumented C# 2026.1.1 application: modal, Vert, then TLM_Constant_UDL. All 1,562,624 stored Vert/constant-load rows match the original C# reference exactly across all available state tables, excluding only surrogate database Id columns. Counts and bidirectional SQL EXCEPT comparisons agree, including NULL values. The diagnostic logging did not change those saved outputs. Vert has ten committed steps, constant load has four; each also has an initial step-zero record. The first constant-load step contains two successful internal substeps, not an extra saved committed step.

The first constant-load attempt uses multiplier increment 0.25. It reaches the configured 3,000-iteration limit (the diagnostic CurrentIter counter reports 3001), returns -2 with Work error 0.0267694989015141 against tolerance 0.002, and invokes StaticIntegrator.revertToLastCommit. C# then retries as two increments of 0.125, accepted after four and two iterations respectively.

## The rollback defect

For transverse spring 0 of interface 681, the original native log records:

| Quantity | Before failed attempt | Immediately before rollback | Immediately after rollback |
|---|---:|---:|---:|
| Stored spring U | 0.05217365161936875 | 0.04854681166456182 | 0.04854681166456182 |
| Committed Cstrain | 0.05217365161936875 | 0.05217365161936875 | 0.05217365161936875 |
| Trial Tstrain | 0.05217365161936875 | 0.04854681166456182 | 0.05217365161936875 |

The interface local displacement returns to its committed value, but base spring U remains from the rejected attempt. Source inspection agrees: StaticIntegrator restores its displacement vector and calls element rollback; Interface.revertToLastCommit restores local displacement and calls spring.RevertToLastCommit; SpringHysteretic.RevertToLastCommit restores trial history without restoring base U. Interface.UpdateDomain subsequently advances base U incrementally, so the failed-attempt offset enters the retry and survives later commits. This is an inconsistent rollback state, not a choice between equivalent numerical strategies.

The logged offset for spring 681 is 0.003626839954806934. The previously observed local-endpoint replay difference at the first commit is 0.0036268399548069694. Across all 36 logged transverse springs, the same rollback offsets explain the previously observed U discrepancies at each of the four saved constant-load commits; the maximum unexplained residual is 1.43e-15. This diagnostic uses saved local endpoints and does not independently qualify global Python outputs or all other spring families.

Native trace: `C:\Users\mbonatte\Documents\Histra\csharp-diagnostics-2026.1.1\app\parity-logs\trace-20261014-093225-258-18032.tsv`. Local reports: `diagnostic-output-comparison.json` and `rollback-offset-proof.json` in the diagnostic directory.

## Python boundary and next experiment

The new native unittest covers scalar SpringHysteretic rollback for all 36 logged transverse cases. It preserves the distinction between scalar spring lifecycle and the solver's full snapshot rollback policy. Current Python solver rollback restores its full state snapshot; that behavior has not been changed to reproduce the stale native U. Full suite: 726 passed, 23 skipped, 855 subtests.

Python's full first increment currently converges after eight iterations. Why its iteration path differs from C# before rollback remains open. Correcting or reproducing the stale-U behavior alone must not be claimed to resolve that separate discrepancy or full global parity.

Using eight constant-load increments instead of four, with the same tolerance, is a useful diagnostic: smaller increments may avoid the rejected attempt and therefore avoid this particular defect. It is not a repair, and another failed attempt can trigger the same problem. A looser tolerance can also avoid rollback by accepting earlier, but changes acceptance accuracy; no tolerance change is recommended as the first experiment. A successful log without rollback and the corresponding outputs would establish whether this workaround is effective on this model.

The user previously requested both full native parity and avoidance of copied bugs. The default/compatibility policy is unresolved pending clarification; no native rollback defect has been enabled in production. Pushover remains gated behind constant-load validation.
