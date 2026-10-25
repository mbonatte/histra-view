# User-selected implementation order, 2026-10-15

1. Improve performance. Preserve original routine logic and bit-exact unit
   tests; global analyses may have small library-level rounding differences
   when the physical response is preserved. Profile actual costs and validate
   complete response histories before recommending a faster configuration.
2. Investigate equilibrium diagnostics. Compare residual assembly and Work
   acceptance with original C# routines, locate the dominant generalized DOFs,
   distinguish force/moment units and explain the measured discrepancy before
   changing diagnostics or acceptance policies.
3. Prepare v1.6.0. The user selected this version for the performance/equilibrium
   milestone. Build and verify distribution artifacts, release notes and
   benchmark provenance for the validated scope.
4. Validate broader masonry behavior. Prioritize unloading/reloading,
   orthotropy, elastic interfaces and zero-friction branches. Request a new
   native reference model if the existing collection does not cover a case.
5. Finish modal parity. Use the existing 20-mode native reference to resolve
   remaining arithmetic differences, retaining native-backed routine tests.
6. Prepare the following release after the broader masonry and modal work.
   Its version will be selected at that milestone.

The current static references regenerate from geometry and check available
outputs through their final committed steps. Their existing exact evidence
remains a separate baseline for performance candidates. See the
[parity diagnostics guide](../guides/csharp-parity-diagnostics.md) and
[snapshot performance profile](../benchmarks/newton-snapshot-reuse-performance.md).
