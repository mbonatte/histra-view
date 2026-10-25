# `histra.io.results_reader`

Reads selected state from the C# SQLite `.Results` database.

Functions:

- `available_steps`: lists stored quad-state steps;
- `read_quad_states`: returns local `U1..U7` by quad key;
- `read_dynamic_vectors`: returns global `U` and `V` from `DynamicVectorsState`, converting one-based database DOFs to zero-based arrays;
- `find_results_path`: locates a sibling `.Results` file.

This module does not yet restore the complete committed analysis state. Chained restart additionally needs interface and spring-history deserialization.
