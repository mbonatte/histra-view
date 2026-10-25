# Dhir constant load: ten-step reference

This earlier reopened-model run is superseded for current chain qualification by [the passing same-session 20-step Vert and ten-step constant-load benchmark](../benchmarks/dhir-vert20-udl10-native-parity.md). The missing history documented below now matches after rerunning Vert before constant load; the native omission itself remains verified.

## Result, 2026-10-14

The user changed only the constant-load step count and reran the locked model in the diagnostic application. The new C# trace is `trace-20261014-095659-968-10564.tsv`. The solver uses ten increments of 0.1, reaches load factor 1.0, and reports no failed attempts, adaptive reductions or rollback calls. Saved steps are initial state 0 and committed steps 1 through 10. All saved Vert state fields remain exactly equal to the original reference, excluding surrogate database IDs.

Python was run from fresh structural geometry, reapplying material 146 to the 148 foundation interfaces before solving Vert then TLM_Constant_UDL. It used the shared native UMFPACK backend and compiled element kernels. The comparison checks all 77,080 springs and every other available numeric state field at each saved step, with unchanged thresholds.

| Comparison across the ten constant-load commits | Result |
|---|---:|
| Maximum spring-force difference | 8.18546e-12 kN |
| Maximum spring-displacement difference | 1.16574e-15 |
| Phase differences | 0 |
| Reaction-vector differences | 0, exactly equal |
| Final global-displacement maximum difference | 2.44249e-15 |
| Final complete-history mismatches | 418 CmomMax values |

All available fields pass except those final CmomMax values. Native/Python iteration counts are also identical: 1, 7, 4, 5, 8, 10, 13, 15, 18, 21. The parity gate remains failed because this is not complete spring-history agreement. NULL per-spring E/Ed/Eel fields remain unavailable. The independent equilibrium audit remains separate from source Work-criterion/output parity.

## Positive-force history lost on native restart

All 418 differences belong to Quad diagonal springs. The new C# values are zero; Python retains their saved Vert positive-force maxima (maximum 903.0639672791579). Python's values differ from the original stored Vert history by at most 3.02e-13.

Two direct original-DLL tests establish the restoration omission. For Quad 2189, the original SQLite reader loads Vert CmomMax=903.0639672791579 correctly. SpringStateDBclass.SetSpring(ref Spring,false) leaves an incoming CmomMax=0 at zero and an incoming CmomMax=123 at 123. The method restores CmomMin but never assigns CmomMax. A direct native SerializeXmlWriter.WriteToString call also omits CmomMax from its XML, despite the live spring containing 123. Source inspection of SpringCoulomb03 and SpringStateDBclass agrees with both calls.

The new native trace has a different process ID from the previous run, and its restart snapshots show the zero history. Reopening the saved model creates springs without that unpersisted XML value; rerunning only constant load does not recover it from the Vert results because the native restoration setter omits it. This is a separate defect from the failed-step stale-U rollback. Smaller increments avoided rollback in this run but cannot restore omitted history.

Python's existing lossless restoration remains unchanged. A regression uses the actual saved native row and both native calls to protect deliberate preservation of the persisted maximum, rather than copying the omission. Full suite: 727 passed, 23 skipped, 857 subtests.

## Required clean reference

Rerun Vert followed by TLM_Constant_UDL in the same application session, retaining the ten-step constant load, tolerance and foundation materials. Unlocking is not required: selecting both analyses for rerun reconstructs Vert history in memory, and the immediately following constant load can retain it. Do not close and reopen the application between them. Save the model/results afterward so the complete-history gate can be checked again before advancing Python to pushover.

Evidence is preserved under the local dnSpy HiStrA `python-comparison-2026-10-13` audit directory:

- `dhir-native-ten-step-reference`: immutable input/result copies used in this check.
- `dhir-ten-step-native-inspection.json`: successful native calls, step counts and exact predecessor comparison.
- `dhir-ten-step-fresh-python/static/every-step`: every paired field and state, including the failed final gate.
- `dhir-ten-step-parity-summary.json` and `dhir-ten-step-history-inspection.json`: numeric summary and isolated missing history.
- `native-cmom-restore-oracle.json` and `native-cmom-serialized.xml`: original reader, restoration and writer evidence.

Input/result copy hashes remained unchanged during the Python run. No solver implementation or comparison cutoff was changed for this validation.
