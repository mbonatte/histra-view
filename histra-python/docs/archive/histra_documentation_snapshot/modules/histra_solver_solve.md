# `histra.solver.solve`

Main static nonlinear orchestration.

Responsibilities:

1. validate supported analysis features;
2. create `Program` and `LinearSystem`;
3. initialize a virgin state when `InitialAnalysisKey < 0`;
4. reject chained restart until full result-state deserialization exists;
5. assemble reference load and initial/tangent stiffness;
6. execute LoadControl or ArcLength steps with Newton/line search;
7. run ALS or ArcLength retry paths where applicable;
8. commit or rollback element/spring state;
9. return the real exit code and per-step records.

`_set_initial_state` is the translated supported subset of C# `CommonOperations.SetInitial`.
