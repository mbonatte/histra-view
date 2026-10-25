# Documentation and generated-artifact policy

## Document classes

### Maintained guide

Explains a current supported workflow. Must be reviewed when related code
changes.

### Reference

Explains stable data structures, terminology, or compatibility rules. Avoid
machine-specific measurements.

### Benchmark report

Records numerical evidence for one identified model and environment. It may
become old without becoming wrong.

### Archive

Preserves audit history, old patches, source inventories, stale metrics, and
superseded explanations. Archive files must not be linked as current guidance.

## Rules for current documentation

- Describe capabilities before benchmark numbers.
- Link to one canonical guide instead of duplicating the same procedure.
- Document the standalone runner with its module command:
  `python -m histra.tools.run_vert_live`.
- Do not say chained analyses require `.Results`; the in-memory session API is
  supported.
- Do not say preprocessing supports exact full edges only; collinear
  partial-edge contacts are implemented.
- Mark every unsupported path explicitly.
- Avoid exact test counts in maintained guides.

## Generated JSON

Committed metrics/results JSON should include:

- `schema_version`
- `generated_at`
- `source_commit`
- `generator`
- `benchmark_id`

Generated runtime output belongs in ignored output directories unless it is an
intentional benchmark fixture with provenance.
