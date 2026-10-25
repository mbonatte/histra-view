# Native C# restart diagnostics

`Invoke-NativeAnalysisOracle.ps1` calls the original complete analysis routines
on fresh HRX geometry, creating a new Results database in a new output directory.
It refuses an existing output directory. Use `-AnalysisKeys '1,2'` for an ordered
chain and `-InstallDirectory` to select an isolated diagnostic assembly copy.
The source model and saved reference Results remain read-only.

The trace helper also accepts `HISTRA_PARITY_CAPTURE_DIR`. When set, each original
`Program.NewGraphError` entry writes complete binary Ap/Ai/Ax, residual and
increment arrays. Use a new capture directory for each process. The initial
error event precedes the Newton solve; the next event retains its solved matrix
and increment after residual evaluation. This permits locating differences
before constitutive updates. Without this variable, binary capture is disabled.
An isolated helper build reproduced all 4,251 rows of an original isotropic Vert
run exactly, excluding surrogate IDs.

This development tool adds calls to an independently compiled C# trace helper around twelve methods in the original HiStrA 2026.1.1 `SolverRuntime.dll`. It preserves the original solver instructions and branches, rather than rebuilding numerical methods from decompiled source. The installed application and reference models are not modified. Use only a separate application copy and separate model/results copies.

The helper always appends and immediately flushes TSV records, including successful runs, to `app/parity-logs/trace-<UTC>-<PID>.tsv`. It records restart and resisting-force baseline preparation; both load-step overloads; Newton convergence messages, errors and return codes; rollback; commits; and result-save calls. Step-zero result-save calls remain explicitly identifiable by their original arguments.

Before/after snapshots cover interfaces 272, 356, 681, 1806, 863 and 5818 and Quad 1111. Interfaces 272 and 356 additionally expose envelope coefficients and private committed/trial hysteretic history for the near-zero-force pushover phase investigation. They include interface local displacement, transverse/shear/out-of-plane spring U/F/history, diagonal state, and the distinction between base spring U and committed/trial strain. These are diagnostic samples selected from the current first-step discrepancy; complete committed outputs still come from the `.Results` database. Global vectors are abbreviated to sixteen entries to keep logging bounded.

Requirements: Windows, .NET Framework 4.8, .NET 10 SDK and dnSpy's dnlib assembly. Build from Windows PowerShell:

```powershell
.\Build-Diagnostic.ps1 -InstalledRoot 'C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1' -DiagnosticRoot 'C:\Users\mbonatte\Documents\Histra\csharp-diagnostics-2026.1.1' -DnlibPath 'C:\Users\mbonatte\Downloads\_Organized_Downloads\Software\dnSpy-net-win64\bin\dnlib.dll'
```

`Test-Diagnostic.ps1` calls the instrumented original assembly without an error, verifies flushed success and convergence messages, before/after commit and rollback records, and round-trip native spring U/Cstrain snapshots. This is a diagnostic smoke test, not an end-to-end structural validation of the instrumented GUI application. The next full model run must be compared with the original reference to establish that the logging does not alter its outputs.

The 2026-10-14 GUI rerun subsequently reproduced all 1,562,624 saved Vert/constant-load records exactly, excluding surrogate database IDs, and confirmed the failed-step spring-U rollback defect. See [the investigation](../../docs/investigations/dhir-constant-load-rollback.md). This qualifies that particular diagnostic rerun; other runs must still be checked independently.

The full installed-run reference is now compared through all 58 committed pushover steps, following modal with default masonry, foundation material 146 mutation, Vert (20 steps) and constant load (10 steps). The original step-23 phase discrepancy is resolved. See [the current comparison](../../docs/benchmarks/dhir-full-chain-native-parity-progress.md) and [modal validation](../../docs/benchmarks/dhir-modal-native-parity.md).
