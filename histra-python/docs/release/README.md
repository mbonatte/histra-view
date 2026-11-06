# Release verification and publication

This is the current package-release workflow. The installed distribution version
comes from `pyproject.toml`; result-file schema versions are independent.
A package release qualifies its recorded tests and reference inputs, not every
possible structural model.

## Prepare

1. Inspect `git status`, the branch, the remote, existing tags and any unrelated
   work. Choose the requested package version and review the changelog scope.
2. Update `pyproject.toml`, the version assertion in
   `histra/tests/test_package_metadata.py`, the dated changelog entry and current
   status when appropriate. Do not relabel old benchmark measurements as new runs.
3. Run the repository checks:

   ```console
   make check
   .venv/bin/python -m pytest -q
   ```

   Review warnings and explain environment/opt-in skips. Run the affected native
   reference and benchmark checks when numerical behavior changes. A green suite
   does not remove the [equilibrium qualification requirements](../nonlinear_convergence_safety.md).

4. Review the final diff and commit the release source. Repository pre-commit
   hooks can fix whitespace; inspect and stage those fixes before retrying.

## Build and verify artifacts

Use a new output directory for each candidate so old versions are not uploaded
by wildcard accidentally. With release dependencies installed:

```console
python -m build --outdir dist/release-candidate
python -m twine check dist/release-candidate/*.whl dist/release-candidate/*.tar.gz
python -m histra.tools.release_manifest dist/release-candidate --output dist/release-candidate/SHA256SUMS
```

Verify that the archives contain every production module and exclude tests,
local models and generated runtime files. Compare packaged Python source with
the committed source tree.

Install the wheel, with its declared dependencies, in a fresh virtual environment
outside the checkout's import path. Confirm that `histra.__file__` points into
`site-packages`, `histra.__version__` matches distribution metadata, and the public
APIs import. Exercise affected features from that installed wheel, including
optional storage backends when their code changes.

Rebuild and revalidate if the source changes after packaging. Preserve the wheel,
source archive and final checksums together.

## Publish when requested

For this repository, hosted releases use GitHub tags and attached artifacts.
After verification, create the requested annotated version tag, push the release
commit and tag without rewriting existing references, and create the GitHub
release with reviewed notes, wheel, source archive and `SHA256SUMS` attached.
Verify the remote tag resolves to the intended commit and each asset is uploaded.

The repository has no automatic PyPI publication workflow. Publishing to another
index is a separate deployment choice. Keep credentials out of source, command
arguments and release notes.

## Historical records

The dated v1.6.0 preparation and critical-review files in this directory describe
that release's evidence and limitations. Original V1.0.0 plans, checklists and
review snapshots are retained under `docs/archive/releases/v1/`; their old
version, worktree, test-count and approval statements are historical.

[Current status](../STATUS.md), the [changelog](../../CHANGELOG.md), and identified
benchmark reports define the present feature and evidence boundary.
