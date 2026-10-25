# `histra.model.model`

Defines the top-level `Model` and its `Collections` dictionaries.

Important fields:

- `gdl`: active generalized-DOF count stored in HRX;
- `source_path`: absolute source HRX path, used to locate related result data;
- `collections`: nodes, NodeCs, quads, interfaces, restraints, loads, analyses, and materials.

The model is mutable because element and spring state changes during analysis.
