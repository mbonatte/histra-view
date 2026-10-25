# `histra.model.load`

Defines load combinations, load conditions, load-function points/functions, and `Analysis`.

`Analysis` includes solver settings plus restart provenance:

- `initial_analysis_key`;
- `initial_combination_analysis_key`.

A negative initial-analysis key identifies a virgin analysis. A nonnegative key requires restoring the complete committed state of a prior result.

`LoadFunctionItem` records are stored separately in HRX and attached to their `LoadFunction` by the loader.
