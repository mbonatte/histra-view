# C# source inventory, audit correction and validation boundaries

Reviewed on 2026-10-17. This document supersedes the earlier claim that every
mapped routine had verified parity. Several cited C# method names did not exist;
a file/function census cannot establish numerical equivalence.

The [dated review record](review-2026-10-17.md) records the findings,
corrections, verification results and their limits.

## What the inventory actually establishes

The [generated inventory](csharp-python-source-inventory.json) enumerates the
Python files, classes and function definitions in the five named core packages.
It records source hashes and definition locations, including nested helpers.
Every file has status `inventory_only`. These are definition counts, not counts
of independently verified numerical routines.

The separate `native_contracts` section records a selected set of real C# source
files, declaration locations, hashes, Python consumers and native fixtures.
Its status is `native_fixture_cases_only`. The generator checks declaration and
evidence existence; it does not execute C# or prove semantic equivalence.
The registry is intentionally incomplete. Python-only buffer/coverage helpers
are not assigned invented C# methods.

Generate it from the repository with:

```text
python tools/benchmarks/build_source_audit_inventory.py --source-root <decompiled-source> --output docs/audit/csharp-python-source-inventory.json
```

Portable tests verify that the inventory matches the actual Python definitions
and that its referenced evidence is current. Original C# source must be available
to regenerate and validate the native declaration locations.

## Corrections backed by direct native execution

| Boundary | Original implementation and evidence | Established scope |
| --- | --- | --- |
| Masonry piecewise backbone | `Objects.SpringHysteretic` constructor, `SetInitial`, `setTrialStrain`, `Commit`; `Invoke-MasonrySpringStateOracle.ps1` | Three backbones, retaining all former monotonic strain samples and adding reversals. Scalar and compiled trials/commits compare exact stored bits, including force, tangent, phases and internal history. This is not the separate `SpringMultiLinearPlastic` class. |
| Material history transfer | `Objects.ElementStates.SpringStateDBclass.SetFromSpring` and `SetSpring(false)`; same oracle and fixture | Virgin, tensile-plastic and reversed states; repeated resets; scalar, numeric-only and cached-proxy paths. Old tangent, yield forces/coordinates and F0 are retained on new envelope definitions. |
| Numeric-only runtime import | Native initial/restored state from the same fixture; `test_numeric_fibre_runtime_import` | Dense import with no scalar-list entries, plus poisoned-buffer reimport. Compiled coverage is checked for the small constructed topology. A complete free-body or staged structural run is a separate validation. |
| Generic multilinear container | Python `SpringMultiLinear`; rejection tests | Serialized field storage only. Trial evaluation, force evaluation and commit reject use. The original `SpringMultiLinearPlastic` plastic law is not implemented or certified. |

Cumulative energy is an explicit exception to transfer equality: native
`SetFromSpring`/`SetSpring` omit that history, while Python deliberately preserves
it. Transfer tests check that Python retains the old energy and compare other
captured fields exactly. Their continuation cases have zero damage parameters;
they do not qualify damage-dependent behavior under this policy difference.

The fixture records the original ModelLibrary assembly hash, input hashes,
oracle-script hashes, generation time and parent source commit. Linux consumes
the saved native outputs. It does not execute the Windows assemblies.

The regression tests were also checked with deliberate in-process faults in
separate processes. A broken production constitutive update fails all three
backbone cases; a wrong target tangent fails all six numeric/cached transfer
cases; the old early return fails both numeric-import cases. These checks
establish sensitivity to the identified faults, not exhaustive fault coverage.
The [probe tool](../../tools/benchmarks/probe_native_test_sensitivity.py) and
[recorded results](../../release-evidence/audit-2026-10-17/sensitivity-backbone.json)
make the check reproducible; sibling JSON files record the other two scenarios.

## What existing tests do and do not establish

- `*_live.py` filenames do not mean live C# execution. Current tests use saved
  fixtures or embedded expectations; only the oracle scripts call C#.
- Gauss tests compare NumPy with the original table. Order 2 is exact; orders
  3 through 10 use the stated tolerance. This does not independently validate
  production mass integration. The table values were independently checked
  against the installed assembly during the review.
- Clipping tests mix identified native fixture cases with analytical geometry
  expectations. Rounded-coordinate comparisons are not bitwise vertex tests.
- Analytical convergence and adversarial regressions are useful contracts, but
  do not become independent C# observations merely by storing integer bits.
- Native routines and complete-analysis fixtures qualify their actual inputs and
  checked fields. Cross-platform library tolerances must stay separate from
  exact routine comparisons.
- The large Dhir and horizontal reports retain their recorded source boundaries.
  They have not been rerun after these material-transfer/import corrections.
  Missing native fields are unavailable measurements, not successful comparisons.

The three additional one-DOF Arc-Length parameter cases have now been captured
by the original `ArcLength.Update` driver and tied to its saved fixture.
All earlier native cases were retained unchanged. This does not cover the
multi-DOF adversarial cases listed below.

## Remaining validation register

| Priority | Missing validation | Acceptance evidence needed |
| --- | --- | --- |
| High | Successful repeated loaded material changes and wider elastic/frictional transitions | The [new GUI reference](../benchmarks/material-modal-gui-2026-10-17.md) matches 42 commits per case, available saved fields, iteration counts and failed return attempts. Default rejection and explicit native history reset are now tested; the elastic option also matches its loaded-B modal result. Successful return execution and broader frictional transitions remain unqualified. |
| High | Independent capture for every added embedded/adversarial expectation | Reproducible original-assembly drivers, assembly/input hashes and trial/commit/revert fields. In particular, extend multi-DOF Arc-Length complex-root/extreme-state coverage. Analytical expectations remain labelled as such meanwhile. |
| High | Wider native constitutive state space | Physically valid parameter sweeps for pinching, damage, beta, curve pairs, turn-off/on, unload/reload, geo-link loading flags and one-ULP branch boundaries. Compare scalar and compiled paths to the independent native routine, not just to one another; reject unsupported paths explicitly. |
| High | Intermediate private structural histories | Original C# committed-state tracing for private fields not saved at every step. Current Results checks cannot measure absent spring histories, NULL energies or absent full global vectors. |
| High | Current 14-model Article regression | Execute the existing release gate on the other computer that has those inputs. Older evidence is not a run of this source. No access is available here. |
| Medium | Contact/input precision beyond current fixtures | Fractional tolerances, oblique/near-coplanar faces, shared boundaries and admission thresholds from original geometry routines and fresh structural models. |
| Medium | General P-Delta geometry and reduction order | Multiple loads sharing DOFs, varied contact centres and result-save intervals beyond the four recorded EachStep/EachIteration chains. |
| Medium | Broader native nonlinear strategy execution | Negative-slope/recovery secant branches, adaptive retries, failure rollback and line-search failure paths. Keep corrected Python rollback policies explicit where C# has a known history-loss defect. |
| Medium | Broader modal parity | Rigid/near-zero modes, repeated/clustered eigenvalues, rotated restraints, load-derived mass and damaged-state models. Compare complete native available quantities and appropriate mode/subspace correspondence; preserve native partial-convergence counts. |
| Medium | Equilibrium qualification beyond Work acceptance | Additional ForceMoment-converged structural references and independent force/moment checks. Matching C# Work acceptance does not imply an independent equilibrium pass. |
| Release gate | Build and supported-platform matrix for the final source | Fresh wheel/sdist checks and Python 3.12/3.13/3.14 CI. A local Python 3.12 pass alone does not qualify all interpreter versions. |

Non-masonry material implementations remain outside the requested scope.
Unsupported inputs must be rejected explicitly rather than silently simulated.
