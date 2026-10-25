# Vert → scour_1 → LiveLoad_1 benchmark

This model was prepared and run by the C# software in the following order:

1. `Vert` with the foundation interfaces using their parent materials (`MaterialKey=0`).
2. Interfaces 359–362 changed to material 147 (`Soil_removed`).
3. `scour_1` chained from `Vert`.
4. `LiveLoad_1` chained from `scour_1`.

The serialized HRX is the final post-mutation model. Tests reconstruct the
pre-scour state by rebuilding interfaces 359–362 with `MaterialKey=0`.
