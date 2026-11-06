# Repository maintenance and retention

`pyproject.toml` owns installable package metadata and dependency bounds.
`requirements.txt` delegates to that package definition; it must not introduce a
second, drifting dependency list. `scripts/setup.sh` owns environment setup, with
`bin/setup` retained as a compatibility symlink.

## Source and commands

- `histra/` is the installed implementation. Numerical facades and scalar
  reference paths can have indirect callers and native-parity tests; a low
  reference count does not establish that they are obsolete.
- `histra/tools/` contains installed manual commands. Their existence is checked
  against the [command catalog](../../tools/README.md), not just import counts.
- `tools/` contains checkout-only native reference generators and diagnostics.
  These remain necessary to reproduce fixture provenance, even when a normal
  test run only reads the generated fixture.
- `examples/` contains supplementary source examples outside the production
  numerical contract.

## Documentation

[Current status](../STATUS.md), [guides](../README.md) and
[architecture](architecture.md) describe present behavior. Dated benchmark and
audit reports retain their original measurement context. Superseded release
plans and architecture progress logs belong in `docs/archive/`, with a historical
banner and corrected navigation where applicable.

Do not mark an old incomplete qualification complete merely because a newer
package exists. Record the current limitations with links to identified evidence.
The [documentation policy](../DOCUMENTATION_POLICY.md) defines document classes
and generated JSON provenance.

## Numerical assets

The retained `histra/model-*/*.hrx`, `.Results` databases and native test fixtures
support differential regression and reproduction. Their size alone does not
justify deletion. Keep the original Article CSV, compact plotting-source
provenance, and reference paper required by benchmark validation.

A ZIP can be removed as redundant only after every member is matched byte for
byte to a retained file and its callers/references are checked. On 2026-10-25,
`histra/model-output/model.zip` was removed after both its `model.hrx` and
`model.Results` members matched the retained `histra/model-live/` pair by SHA-256.
The removed archive occupied 10,337,095 bytes; no reference data was lost.

Generated solve output belongs in ignored output directories. Local notebooks,
checkpoint directories, build products, virtual environments and scratch runs
are excluded from tracking. Avoid deleting ignored user experiments as part of
tracked repository cleanup.

## Audit practice

Before removing or moving a file, check imports, CLI entry points, tests,
documentation, fixture-generator metadata and historical provenance. Recheck
maintained relative links and documented module commands after reorganization.
Run focused checks for affected workflows, and the complete suite when changes
span multiple entry points. Publishing repository cleanup must not rewrite older
release tags or history.
