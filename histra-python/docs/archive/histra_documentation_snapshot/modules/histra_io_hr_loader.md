# `histra.io.hr_loader`

Streaming HRX parser.

Key behaviors:

- parses core nodes, constraints, quads, interfaces, restraints, loads, materials, and analyses;
- distinguishes top-level keyed interfaces from nested references;
- joins separate `LoadFunctionItem` records to their parent function;
- parses `InitialAnalysisKey` and `InitialCombinationAnalysisKey`;
- stores the absolute input path on `Model.source_path`;
- recovers `model.gdl` from afference only if the HRX header is zero.

Loading preserves serialized element state. Virgin-state reset occurs in the nonlinear solver, not in the parser.
