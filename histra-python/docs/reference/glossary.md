# Glossary

| Term | Meaning in this codebase |
|---|---|
| **Afference** | Mapping from a local element coordinate to a global DOF using `AfferenceEntry(gdl, alfa)` |
| **`alfa`** | Stiffness-selection/scaling argument; `0` is used for initial/modified stiffness and nonzero is intended for tangent behavior |
| **ALS** | Automatic Load Stepping; subdivision of a failed LoadControl increment |
| **Committed state** | Last accepted element/spring history at a converged step |
| **Correction / `du` / `ls.x`** | Displacement increment solved during an equilibrium iteration |
| **CSC / COO** | SciPy sparse matrix formats; assembly uses COO triplets then converts to CSC |
| **DOF / GDL** | Degree of freedom; HRX uses one-based global identifiers |
| **External load `Fext`** | Accumulated applied load vector |
| **Integrator** | Object controlling step/load-factor progression and displacement updates |
| **Interface** | Connection element represented by distributed springs and local stiffness blocks |
| **`K`** | Global stiffness matrix; initial, secant, or tangent depending on formulation |
| **`lambda`** | ArcLength load factor |
| **Load function** | Pseudo-time versus load multiplier history and discretization |
| **Modified Newton** | Reuses an initial/fixed stiffness matrix across iterations |
| **P-Delta** | Second-order geometric effect; represented incompletely in this snapshot |
| **Predictor** | Initial displacement/load increment at the start of a step |
| **`Ptarget`** | Unscaled reference load pattern |
| **Quad** | Quadrilateral masonry macro-element with a nonlinear diagonal spring |
| **Residual / unbalance** | `F_external + F_PDelta - F_internal` stored in `ls.b` |
| **Standard Newton** | Rebuilds the current tangent stiffness each iteration |
| **Trial state** | Temporary element/spring history for the current Newton or line-search evaluation |
