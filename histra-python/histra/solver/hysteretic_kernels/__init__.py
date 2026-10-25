"""Compiled hysteretic kernel ownership for the nonlinear batch runtime.

Kernels are grouped by element family and split out of
:mod:`histra.solver.hysteretic_batch` one commit at a time. The package exists
so each kernel family can own its constants and compiled code while the batch
runtime keeps a stable compatibility facade.
"""

from histra.solver.hysteretic_kernels.interface_coulomb import (
    _advance_interface_coulomb_targets,
    _assemble_full_interface_forces,
    _commit_elastic_sliding_batch,
    _commit_initial_coulomb_batch,
    _evaluate_elastic_sliding_batch,
    _evaluate_initial_coulomb_batch,
)
from histra.solver.hysteretic_kernels.kinematics import (
    _map_and_prepare_interface_kinematics,
    _map_global_to_local,
    _prepare_interface_kinematics,
    _prepare_quad_kinematics,
)
from histra.solver.hysteretic_kernels.quad_takeda import (
    _commit_quad_takeda_batch,
    _evaluate_quad_takeda_batch,
)
from histra.solver.hysteretic_kernels.scatter import (
    _batch_interface_resultants,
    _eval_pdelta_interfaces_kernel,
    _refresh_global_resisting_force,
    _refresh_global_resisting_force_by_dof,
    _refresh_max_u_cache,
    _scatter_local_forces,
)
from histra.solver.hysteretic_kernels.transverse import (
    _advance_and_evaluate_simple_linear_batch,
    _advance_evaluate_and_finish_simple_linear_batch,
    _advance_transverse_targets,
    _evaluate_linear_batch,
    _evaluate_simple_linear_batch,
    _finish_transverse_batch,
)

__all__ = [
    "_map_and_prepare_interface_kinematics",
    "_map_global_to_local",
    "_prepare_interface_kinematics",
    "_prepare_quad_kinematics",
    "_refresh_global_resisting_force",
    "_refresh_global_resisting_force_by_dof",
    "_refresh_max_u_cache",
    "_scatter_local_forces",
    "_batch_interface_resultants",
    "_eval_pdelta_interfaces_kernel",
    "_advance_and_evaluate_simple_linear_batch",
    "_advance_evaluate_and_finish_simple_linear_batch",
    "_advance_interface_coulomb_targets",
    "_advance_transverse_targets",
    "_assemble_full_interface_forces",
    "_commit_elastic_sliding_batch",
    "_commit_initial_coulomb_batch",
    "_commit_quad_takeda_batch",
    "_evaluate_elastic_sliding_batch",
    "_evaluate_initial_coulomb_batch",
    "_evaluate_linear_batch",
    "_evaluate_quad_takeda_batch",
    "_evaluate_simple_linear_batch",
    "_finish_transverse_batch",
]
