# Article Models release gate

The tracked canonical harness is `histra.tools.article_models_benchmark`. Its
registry contains all 14 files/variants and maps them to the physical specimen,
published figure, Table 1 capacity, master point, and displacement direction.
The source paper is `docs/references/articles/Bonatte et al. - A discrete
macro-element method for structural assessment of masonry arch bridges.pdf`.

Run the complete gate with no more than four workers:

```console
python -m histra.tools.article_models_benchmark \
  --models-dir my_model/Article_Models_Benchmark \
  --model all --run-mode both --max-workers 4 \
  --output-dir release-evidence/article-models
```

`authored` preserves the C# numerical path and marks independently unsafe rows.
`strict` selects ForceMoment with the measured Standard Bisection strategy,
uses a consistent ArcLength line-search projection, never loosens the authored
tolerance, and rejects an unsafe candidate without committing it. The command exits nonzero unless all
dependency chains, stored rows, response tolerances, and terminal spring-phase
distributions pass. Use `--allow-incomplete` only to collect diagnostics.
An interrupted diagnostic run can add `--resume`; release-candidate evidence
must use a clean output directory so every checkpoint comes from the exact
candidate under review.

The harness records SHA-256 hashes, byte sizes, platform/package versions,
backend, analysis settings, runtime, terminal outcomes, unsafe counts, exact
row errors, live-load curve metrics, and spring-phase counts. It obtains terminal
steps independently from reaction, displacement, and spring tables, so sparse
C# output rows are not mistaken for missing solver steps.

## Original plot data contract

The preferred original-data input is the supplied workbook export
`release-evidence/article-source-data/Original_article_data.csv`, accompanied
by `Graphs_HISTRA.ipynb`. The harness reads its variable-width two-level header
directly; it does not round or hand-transcribe curves into derived CSVs. The
reviewable figure-to-series selection, notebook cell, one radial-displacement
projection for Figure 22, and the deliberate 17-point plot trim for the Bridge
5.1 original strip series are declared in `ARTICLE_SOURCE_SERIES` in the
canonical harness. Its validation report records SHA-256 hashes, counts, and
the exact provenance for every selected series.

As an alternative, one UTF-8 CSV per figure may be supplied, named
`figure_09.csv` through `figure_25.csv` for Figures 9, 12, 13, 15, 17, 20, 22,
24, and 25. Required columns are `series`, `displacement_mm`, `load_kn`, and
`provenance`; Figure 22 may additionally use `location=arch|pier`. Values
transcribed from an image are not treated as original source data. In this
legacy per-figure mode, supply `table_01.csv` with `specimen`, `capacity_kn`,
and `provenance`. In workbook-export mode, Table 1 is anchored to the supplied
Bonatte paper and its file hash. Missing, non-finite, duplicate, or malformed
source rows fail closed before a release run. Use `--source-data-dir` only when
these files live somewhere else.

## Deterministic C# trace request

For the earliest divergent analysis/step, return a JSONL trace from the exact C#
binary that produced the `.Results` file. Each Newton/line-search record must
include analysis key/name, step, iteration, load factor, control displacement,
selected convergence value, sparse K (shape, index base, row/column/value), B,
X, residual before/after solve, line-search eta and bracket values, and backend
name/version. At the pre-step and committed boundary include input hashes,
global displacement, reaction sums, and spring identity/state using
`ParentType, ParentKey, SpringPurpose, IdLocal` plus phase, U, F, tangent,
yield/ultimate points, contact area, normal force, unloading phases, and plastic
indicators. Never relax acceptance tolerances to compensate for backend drift.

The supplied `.Results` SQLite database is still valuable when an instrumented
C# executable is unavailable: it records committed public-step reactions,
model-point displacements, temporary spring states, and final complete spring
states. It does **not** contain the Newton matrices, residuals, load factors,
or line-search trials listed above, so it cannot support a numerical-backend
waiver or reconstruct an iteration trace.
