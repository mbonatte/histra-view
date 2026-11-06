# Supplied output-projection reference

- `model.hrx`: source HRX, including reference-only serialized C# state.
- `model.Results`: authoritative C# SQLite output used by regression tests.

Fresh Python preparation regenerates the computational model before solving.
`histra/tests/test_benchmark_alignment.py` compares the first analysis-1 load step
with `QuadStates`; output-projection and native-results tests also use this pair.

Historical parser/assembly snapshots and old audit metrics are not current files
in this directory. A redundant `model.zip` was removed: its two members matched
the distinct retained `histra/model-live/` reference pair byte for byte.
