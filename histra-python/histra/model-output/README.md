# Supplied model and result files

- `model.hrx`: model definition plus serialized application/element state.
- `model.Results`: SQLite database containing C# result states. This is the authoritative numerical reference used by the audit.
- `results.json`: historical parser/assembly snapshot. It is **not** an independent nonlinear-solver result and contains stale metadata (`n_interfaces` and `K_nnz`).

The Python test `histra/tests/test_benchmark_alignment.py` compares the first analysis-1 load step with `QuadStates` in `model.Results`.
- `audit_metrics.json`: machine-readable inventory, test count, C# database row counts, and measured first-step comparison from the final audit.
