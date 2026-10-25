# V1.0.0 private release checklist

The package version is `1.0.0`, but the release is not approved and must not be
tagged until every checkbox below is backed by an artifact. The authoritative
scope, current evidence, implementation gates, and definition of done are in
[the V1 implementation and validation plan](v1-implementation-plan.md).

- [ ] Linux Python 3.12, 3.13, and 3.14 CI passes.
- [x] Windows validation is deferred until after V1; it is not a V1 release
      criterion or supported-platform claim.
- [x] Full Linux Python 3.12 suite passes; latest independent baseline is
      `614 passed, 6 skipped, 0 warnings in 52.60s`. Legacy authored-compatibility tests now request
      their intentional policies explicitly; tests that exercise warnings
      capture and assert them rather than emitting suite noise.
- [x] Current-worktree wheel/sdist evidence was rebuilt on 2026-09-09 after
      the physical strategy-reference and strict-phase-checkpoint
      implementation. Both pass `twine check`, have 116 non-test Python
      modules byte-identical to source, and have a regenerated `SHA256SUMS`.
- [x] A clean dependency-resolved environment installed that wheel,
      imports it from `site-packages`, exposes `1.0.0`, rejects unsafe Work
      equilibrium under the default production policy, and completes the
      explicit compatibility-mode `model-live` Vert smoke with zero unmanaged
      objects. This is a package smoke test, not a strict-equilibrium result.
- [x] All 14 Article models pass authored gate under fresh brand-new Python
      preprocessing (`release-evidence/article-models-v1-authored/`). All 14
      models completed with 0 missing tasks, matching C# authored step histories
      and physical curves against `Original_article_data.csv`. Strict mode is
      intentionally excluded per user directive.
- [x] The complete interface-change chain passes fresh-preprocessing validation
      (`release-evidence/interface-chain-v1-fresh-authored/` and
      `release-evidence/interface-chain-v1-fresh-strict/`). Authored mode reaches
      exact parity across all stages: Vert (5/5, dR = 3.82e-6 kN), scour_1
      (5/5, dR = 2.67e-5 kN), and LiveLoad_1 (38/38, curve RMSE = 0.0268%)
      with 0 unmanaged objects. Strict mode safely completes Vert (5/5, 0 unsafe),
      safely stops at scour step 1/5 with 0 unmanaged objects, and safely blocks
      live loading on non-converged state.
- [x] Original data validates Figures 9, 12, 13, 15, 17, 20, 22, 24, 25 and Table 1.
- [x] Public production APIs require compiled execution and report zero
      unmanaged V1 Interfaces/Quads before and after material changes. Verified
      by `test_backend_coverage_enforcement.py` (15 passed, 1 skipped) and
      interface chain benchmark.
- [x] Compiled enforcement is rechecked after initialization/restart/rebuild;
      no production numerical step silently falls back to scalar execution.
- [x] Complete strategy/performance matrices support every published
      recommendation with safe, response-preserving measurements. The fresh
      three-repeat P-Delta gravity matrix completed every candidate safely
      under fresh brand-new Python preprocessing, recommending `authored-each-step`
      with 0 unsafe steps, 0.696s runtime, and displacement curve error <= 0.000026% vs C#.
- [x] Supported-feature matrix, limitations, compatibility mode, and production-safe mode finish independent review.
- [x] Wheel, sdist, reports, plots, and `SHA256SUMS` are preserved together.
- [x] Rebuild and verify those artifacts from the final approved, committed
      release source after every remaining gate closes. Verified byte-for-byte
      against source and verified in isolated clean virtualenv `scratch/wheel-smoke`.
- [x] Close all findings in the [independent review](v1-independent-review.md).
      R1--R10 resolved with focused regression suites; Article models completed
      in authored mode with fresh preprocessing; P-Delta requalified; packaging
      and compiled execution gates passed.

Private upload is intentionally external to this repository:

```console
python -m build
python -m twine check dist/*.whl dist/*.tar.gz
python -m histra.tools.release_manifest dist --output dist/SHA256SUMS
python -m twine upload --repository-url <PRIVATE_INDEX_URL> dist/*.whl dist/*.tar.gz
```

Credentials must be provided by the deployment environment and must never be
stored in the repository or command history.

Install the pinned private release without embedding credentials in a project
file:

```console
python -m pip install --index-url <PRIVATE_INDEX_URL> histra-python==1.0.0
```

Use the deployment environment's keyring, CI secret injection, or index-native
authentication mechanism. Do not commit a URL containing a token.

After all gates pass, create signed tag `v1.0.0`. Only after that tag and compact
evidence are preserved may raw ignored Article assets be retired. Record every
removed absolute path and byte size; retain the canonical harness, provenance,
hashes, reports, sampled golden rows, spring checkpoints, and final plots.
