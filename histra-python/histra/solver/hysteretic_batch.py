"""Compatibility facade for the hysteretic batch runtime.

Every name historically defined by this module now lives in
:mod:`histra.solver.hysteretic_runtime` (runtime, builder, thread helpers and
orchestrator kernel), :mod:`histra.solver.hysteretic_topology` (topology and
extraction) or :mod:`histra.solver.hysteretic_kernels` (compiled kernel
families). This module re-exports the complete historical surface by identity
so existing imports keep working; new production code imports the owners.
"""
from __future__ import annotations

from histra.solver.hysteretic_runtime import *  # noqa: F401,F403
from histra.solver.hysteretic_runtime import (  # noqa: F401
    _InterfaceSlice,
    _PARAM_GETTER,
    _PARAM_NAMES,
    _PHASE_BY_CODE,
    _SIMPLE_PARAM_GETTER,
    _TransverseParameterView,
    _advance_and_evaluate_simple_linear_batch,
    _advance_evaluate_and_finish_simple_linear_batch,
    _advance_interface_coulomb_targets,
    _advance_transverse_targets,
    _assemble_full_interface_forces,
    _batch_interface_resultants,
    _build_force_by_dof_topology,
    _commit_elastic_sliding_batch,
    _commit_initial_coulomb_batch,
    _commit_quad_takeda_batch,
    _eval_pdelta_interfaces_kernel,
    _eval_pdelta_line_loads_kernel,
    _evaluate_elastic_sliding_batch,
    _evaluate_initial_coulomb_batch,
    _evaluate_linear_batch,
    _evaluate_quad_takeda_batch,
    _evaluate_simple_linear_batch,
    _extract_spring_committed,
    _extract_spring_curve_type,
    _extract_spring_compressive_curve_type,
    _extract_spring_params,
    _extract_spring_target,
    _extract_spring_trial,
    _finish_transverse_batch,
    _force_general_hysteretic_batch,
    _managed_elastic_energy,
    _mirror_hysteretic_quad,
    _revert_hysteretic_quad,
    _map_and_prepare_interface_kinematics,
    _map_global_to_local,
    _phase_from_code,
    _pos_rotlim_typed,
    _pos_stress_typed,
    _pos_tangent_typed,
    _prepare_interface_kinematics,
    _prepare_quad_kinematics,
    _quad_interpolated_shear_energy,
    _quad_shear_ultimate_strain,
    _quad_tangent_reload_c,
    _quad_tangent_reload_t,
    _quad_tau_limit,
    _quad_yield_compression,
    _quad_yield_tension,
    _quad_revert_trial,
    _refresh_global_resisting_force,
    _refresh_global_resisting_force_by_dof,
    _refresh_max_u_cache,
    _scatter_local_forces,
    _update_domain_batch,
    _uses_simple_hysteretic_parameters,
    _VirtualManagedSequence,
    _VirtualSpringSequence,
)
