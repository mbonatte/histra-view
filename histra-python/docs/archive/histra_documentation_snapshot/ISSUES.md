# Issues Found

## Resolved

1. **Stale audit/model assumptions** — tests and reports referenced a different 2,142-DOF package. Corrected to the uploaded 126-DOF model.
2. **Wrong element update order** — Python updated quads before interfaces; C# does interfaces first.
3. **Missing normal-force path** — all Coulomb03 springs effectively received zero `dN`.
4. **Incomplete `Quad.ComputeDN`** — connected interface increments, stress, material, volume, and signs were incomplete.
5. **Wrong torsional branch** — Python assembled an inactive rotational-spring model instead of C# `TwoSprings`.
6. **Incomplete Coulomb rollback** — current normal stress and yield limits were not restored consistently.
7. **Partial solver rollback** — rejected/failed trials restored only fragments of global state.
8. **Incomplete restart** — no typed, strict restoration of complete final spring history.
9. **Stale path tests** — tests climbed above the actual package root.
10. **Silent load metadata fallbacks** — missing/unsupported coefficient paths could become zero or `None`.
11. **Legacy typed-reader break** — displacement extraction assumed raw tuples after typed readers were introduced.
12. **Snapshot extra-field leak** — fields created during a trial survived restore.

## Open

1. **Step-2 global path mismatch** — begins after an exact committed step 1, while constitutive laws match under exact C# inputs.
2. **No C# per-iteration trace** — database stores committed states only.
3. **Native solver mismatch cannot be directly tested** — supplied environment lacks a runnable original .NET/UMFPACK build.
4. **Intermediate restart is inherently incomplete** — `SpringStatesTmp` omits required history; Python correctly refuses lossless restart from it.
5. **Non-gravity applied-load object families are not implemented in this Python snapshot.**
