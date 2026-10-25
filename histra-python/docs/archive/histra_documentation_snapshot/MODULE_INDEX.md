# Module Reference Index

Each Python source file has a matching Markdown reference generated from this snapshot.

| Source module | Lines | Main classes | Main functions | Documentation |
|---|---:|---|---|---|
| `histra/__init__.py` | 1 | — | — | [open](modules/histra___init__.md) |
| `histra/__main__.py` | 78 | — | `main` | [open](modules/histra___main__.md) |
| `histra/elements/__init__.py` | 11 | — | — | [open](modules/histra_elements___init__.md) |
| `histra/elements/interface.py` | 772 | `Interface` | — | [open](modules/histra_elements_interface.md) |
| `histra/elements/interface_state.py` | 60 | `InterfaceState` | `_list2d` | [open](modules/histra_elements_interface_state.md) |
| `histra/elements/quad.py` | 719 | `Quad` | — | [open](modules/histra_elements_quad.md) |
| `histra/elements/quad_state.py` | 11 | `QuadState` | — | [open](modules/histra_elements_quad_state.md) |
| `histra/io/__init__.py` | 2 | — | — | [open](modules/histra_io___init__.md) |
| `histra/io/hr_loader.py` | 214 | — | `load_model`, `_parse_load_combination`, `_safe_int` | [open](modules/histra_io_hr_loader.md) |
| `histra/io/results_reader.py` | 64 | — | `_connect`, `available_steps`, `read_quad_states`, `find_results_path` | [open](modules/histra_io_results_reader.md) |
| `histra/model/__init__.py` | 9 | — | — | [open](modules/histra_model___init__.md) |
| `histra/model/_types.py` | 6 | — | — | [open](modules/histra_model__types.md) |
| `histra/model/interface.py` | 5 | — | — | [open](modules/histra_model_interface.md) |
| `histra/model/load.py` | 113 | `LoadCombinationItem`, `LoadCombination`, `LoadCondition`, `LoadFunction`, `Analysis` | — | [open](modules/histra_model_load.md) |
| `histra/model/masonry_material.py` | 21 | `MasonryMaterial` | — | [open](modules/histra_model_masonry_material.md) |
| `histra/model/model.py` | 39 | `Collections`, `Model` | — | [open](modules/histra_model_model.md) |
| `histra/model/node.py` | 74 | `Node`, `SlaveElement`, `NodeC` | — | [open](modules/histra_model_node.md) |
| `histra/model/quad.py` | 5 | — | — | [open](modules/histra_model_quad.md) |
| `histra/model/restraint.py` | 25 | `Restraint` | — | [open](modules/histra_model_restraint.md) |
| `histra/model/spring.py` | 28 | — | — | [open](modules/histra_model_spring.md) |
| `histra/solver/__init__.py` | 31 | — | — | [open](modules/histra_solver___init__.md) |
| `histra/solver/arc_length.py` | 376 | `ArcLength`, `ArcLengthLinear` | — | [open](modules/histra_solver_arc_length.md) |
| `histra/solver/assembler.py` | 598 | — | `_intf_get_di`, `_intf_get_dj`, `_intf_get_dm`, `_intf_ecc_spring`, `_compute_interface_kfless`, `_compute_interface_kslid`, `_compute_interface_kslid_op`, `_assemble_afference`, `assemble_global_k`, `get_restrained_dofs`, `apply_boundary_conditions`, `_get_comb_coeff_gravity`, `_resolve_coefficient`, `generate_self_weight_loads`, `assemble_load_vector`, `extract_displacements` | [open](modules/histra_solver_assembler.md) |
| `histra/solver/incremental_integrator.py` | 292 | `IncrementalIntegrator`, `StaticIntegrator` | — | [open](modules/histra_solver_incremental_integrator.md) |
| `histra/solver/line_search.py` | 144 | `LineSearch`, `RegulaFalsiLineSearch` | — | [open](modules/histra_solver_line_search.md) |
| `histra/solver/load_control.py` | 199 | `LoadControl` | — | [open](modules/histra_solver_load_control.md) |
| `histra/solver/model_manager.py` | 199 | `ModelManager` | — | [open](modules/histra_solver_model_manager.md) |
| `histra/solver/newton_line_search.py` | 206 | `NewtonLineSearch` | `_new_line_search` | [open](modules/histra_solver_newton_line_search.md) |
| `histra/solver/newton_raphson.py` | 184 | `NewtonRaphson` | — | [open](modules/histra_solver_newton_raphson.md) |
| `histra/solver/nonlinear_solver.py` | 11 | — | — | [open](modules/histra_solver_nonlinear_solver.md) |
| `histra/solver/program.py` | 68 | `Program` | — | [open](modules/histra_solver_program.md) |
| `histra/solver/solution_algorithm.py` | 98 | `SolutionAlgorithm`, `EquiSolnAlgo` | `_new_line_search` | [open](modules/histra_solver_solution_algorithm.md) |
| `histra/solver/solve.py` | 383 | — | `solve_static_nonlinear`, `_is_load_control`, `_commit_state`, `_als_loop` | [open](modules/histra_solver_solve.md) |
| `histra/solver/solver.py` | 73 | — | `solve_linear`, `verify_solution`, `compute_residual` | [open](modules/histra_solver_solver.md) |
| `histra/springs/__init__.py` | 19 | — | — | [open](modules/histra_springs___init__.md) |
| `histra/springs/base.py` | 145 | `Spring` | — | [open](modules/histra_springs_base.md) |
| `histra/springs/coulomb.py` | 21 | `SpringCoulomb` | — | [open](modules/histra_springs_coulomb.md) |
| `histra/springs/coulomb03.py` | 1086 | `SpringCoulomb03` | — | [open](modules/histra_springs_coulomb03.md) |
| `histra/springs/elastic.py` | 14 | `SpringElastic` | — | [open](modules/histra_springs_elastic.md) |
| `histra/springs/hysteretic.py` | 808 | `SpringHysteretic` | — | [open](modules/histra_springs_hysteretic.md) |
| `histra/springs/multilinear.py` | 26 | `SpringMultiLinear` | — | [open](modules/histra_springs_multilinear.md) |
| `histra/springs/registry.py` | 22 | — | `_register_spring`, `spring_from_xml` | [open](modules/histra_springs_registry.md) |
| `histra/types/__init__.py` | 21 | — | — | [open](modules/histra_types___init__.md) |
| `histra/types/afference_entry.py` | 14 | `AfferenceEntry` | — | [open](modules/histra_types_afference_entry.md) |
| `histra/types/convergence_test.py` | 112 | `ConvergenceTest` | — | [open](modules/histra_types_convergence_test.md) |
| `histra/types/hysteretic_curve_types.py` | 16 | `HystereticTensileCurveTypeEnum`, `HystereticCompressiveCurveTypeEnum` | — | [open](modules/histra_types_hysteretic_curve_types.md) |
| `histra/types/integrator_state.py` | 21 | `IntegratorState` | — | [open](modules/histra_types_integrator_state.md) |
| `histra/types/linear_system.py` | 79 | `LinearSystem` | — | [open](modules/histra_types_linear_system.md) |
| `histra/types/phase_enum.py` | 17 | `PhaseEnum` | — | [open](modules/histra_types_phase_enum.md) |
| `histra/types/point.py` | 25 | `Point` | — | [open](modules/histra_types_point.md) |
| `histra/types/xml_utils.py` | 16 | — | `_attr` | [open](modules/histra_types_xml_utils.md) |
