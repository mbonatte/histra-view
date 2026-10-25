# V1 supported features

V1 is deliberately limited to masonry models assembled from Quad and Interface
elements. A feature is production-supported only when capability preflight
accepts it and its release evidence is green.

| Area | Supported in V1 | Limitations |
|---|---|---|
| Model/input | HRX, locked or unlocked geometry, six-face Quad contacts, afference, restraints, masonry templates | Frame, Slab, Link, Joint, Solid, Truss, Vertex, InterfaceMF, NodeBC, fiber, concrete, and steel systems are outside V1. |
| Loading/state | Self-weight, `Force`/`LoadCombination` static distributions, line loads, staged dependencies, restart transfer, interface material changes | Static Modal/Triangular/Adaptive/ShearFloor pushover generators are rejected before solving. HRX `ForceImposed`/`ForceControl` are preserved; their Frame/non-rigid-restraint refresh behavior is outside V1. Unknown load-element types fail while loading. |
| Static integration | LoadControl, ArcLength, ArcLengthLinear; force and displacement control; C# ArcLength procedures plus explicit `ProjectedControlPoint` safe extension | Dynamic Newmark/HHT/Wilson paths are outside V1. Unknown constraint procedures fail before solving. |
| Nonlinear methods | Standard/Modified Newton; Standard/Modified Secant, Regula-Falsi, Bisection, Initial-Interpolated line search | Krylov, Broyden, BFGS, Accelerated Newton, and Periodic Newton are not constructible in the supplied C# factory and are rejected. |
| Convergence | ForceMoment, DispRotation, Work plus independent force/residual audit | C# `RelativeWork` is enum-only and is rejected. Work/DispRotation require strict audit for production. |
| Flexural curves | Elastic, linear hardening, linear softening, exponential tension, parabolic compression | Unknown curve enums fail before solving. |
| Shear/sliding | Linear, Coulomb, Cacovic; ductility, fracture energy, contact-area correction, orthotropic/mixed material interfaces | The supplied C# construction path ignores the stored `UnloadShear` Origin/Mixed selector: Interface sliding is Initial and Quad diagonal shear is Takeda. Python preserves that documented compatibility behavior. |
| Geometric nonlinearity | P-Delta EachStep and EachIteration | Must pass the model-specific strict release gate. |
| Modal | C#-compatible Quad mass integration, Subspace/Inverse iterations, Frequency/EigenVector criteria, mass normalization, participation, effective mass, mode-shape projection | The active C# Quad mass routine ignores its lumped/consistent boolean, which Python records explicitly. Unknown modal or mass enums fail before assembly; response-spectrum contributions and nonlinear dynamics are outside V1. |

Unsupported values produce `UnsupportedSolverCapability` before the analysis
starts. No unsupported enum is mapped to a nearby physical law.
