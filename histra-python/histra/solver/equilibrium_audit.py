"""Independent equilibrium safety audit for committed-step candidates.

The audit is deliberately separate from the selected C# convergence criterion:
a selected criterion (e.g. Work) may pass while the force balance or the
active-DOF residual remains unsafe. Never make a warning disappear by using
the selected criterion as the audit.

Policies: ``warn`` emits one :class:`UnsafeEquilibriumWarning`, ``error``
restores the pre-step snapshot and stops the analysis before committing the
unsafe step, ``off`` only marks ``equilibrium_checked=False``.
"""
from __future__ import annotations

import time
import warnings
from typing import Any

from histra.solver.equilibrium import (
    UNSAFE_EQUILIBRIUM_EXIT_CODE,
    UnsafeEquilibriumWarning,
    audit_static_equilibrium,
)


def run_equilibrium_audit(
    *,
    reaction,
    integrator,
    algorithm,
    analysis,
    step: int,
    p,
    ls,
    dof: int,
    n: int,
    initial_reaction,
    equilibrium_target_force,
    equilibrium_reference_load_factor: float,
    equilibrium_policy: str,
    equilibrium_force_absolute_tolerance: float,
    equilibrium_force_relative_tolerance: float,
    equilibrium_residual_tolerance: float,
    step_snapshot,
    diagnostic_writer,
    step_data: list,
    unsafe_equilibrium_steps: int,
    warned_unsafe_equilibrium: bool,
) -> tuple[dict[str, Any], int, bool, bool]:
    """Audit one trial step.

    Returns ``(equilibrium_fields, unsafe_count, warned, stop)``. ``stop`` is
    true when the ``error`` policy rejected the step: the caller must set
    ``final_code = UNSAFE_EQUILIBRIUM_EXIT_CODE`` and break without committing.
    The failure row is appended to ``step_data`` here, before any commit.
    """
    equilibrium_fields: dict[str, Any] = {
        "equilibrium_checked": equilibrium_policy != "off",
    }
    if equilibrium_policy != "off":
        audit = audit_static_equilibrium(
            reaction=reaction,
            reference_reaction=initial_reaction,
            target_force=equilibrium_target_force,
            load_factor_increment=(
                float(integrator.mult) - equilibrium_reference_load_factor
            ),
            residual=ls.b,
            force_absolute_tolerance=equilibrium_force_absolute_tolerance,
            force_relative_tolerance=equilibrium_force_relative_tolerance,
            residual_tolerance=equilibrium_residual_tolerance,
        )
        equilibrium_fields.update(audit.step_fields())
        if not audit.safe:
            unsafe_equilibrium_steps += 1
            message = audit.warning_message(
                analysis_name=str(getattr(analysis, "name", "")),
                step=step,
                criterion=str(algorithm.the_test.criterion),
                criterion_error=float(algorithm.the_test.get_error()),
            )
            p.log(f"################# {message} #################")
            if equilibrium_policy == "warn" and not warned_unsafe_equilibrium:
                warnings.warn(
                    message + " Further unsafe steps are logged and marked in step data.",
                    UnsafeEquilibriumWarning,
                    stacklevel=2,
                )
                warned_unsafe_equilibrium = True
            if equilibrium_policy == "error":
                failure_trial_u = p.u.copy()
                failure_load_factor = float(integrator.mult)
                failure_displacement = float(p.u[dof]) if 0 <= dof < n else 0.0
                failure_increment_norm = float(ls.get_x_norm())
                failure_max_u = float(p.max_u)
                failure_max_key = int(p.elem_max_u_key)
                failure_max_type = str(p.elem_max_u_type)
                restore_started = time.perf_counter()
                step_snapshot.restore()
                if diagnostic_writer is not None:
                    diagnostic_writer.add_timing(
                        "restore", time.perf_counter() - restore_started
                    )
                    diagnostic_writer.emit(
                        "restore", step=step, reason="unsafe_equilibrium"
                    )
                p.current_load_factor = integrator.mult
                step_data.append(
                    {
                        "step": step,
                        "status": "FAILED",
                        "exit_code": UNSAFE_EQUILIBRIUM_EXIT_CODE,
                        "u": p.u.copy(),
                        "trial_u": failure_trial_u,
                        "load_factor": failure_load_factor,
                        "displacement": failure_displacement,
                        "iterations": int(algorithm.the_test.current_iter),
                        "linear_solve_count": int(getattr(p.ls, "solve_count", 0)),
                        "factorization_count": int(getattr(p.ls, "factorization_count", 0)),
                        "convergence_criterion": str(algorithm.the_test.criterion),
                        "convergence_tolerance": float(algorithm.the_test.tolerance),
                        "convergence_error": float(algorithm.the_test.get_error()),
                        "residual_norm": audit.residual_norm,
                        "increment_norm": failure_increment_norm,
                        "max_element_displacement": failure_max_u,
                        "max_element_key": failure_max_key,
                        "max_element_type": failure_max_type,
                        "reaction_x": reaction.x,
                        "reaction_y": reaction.y,
                        "reaction_z": reaction.z,
                        "balancing_reaction_x": reaction.balancing_x,
                        "balancing_reaction_y": reaction.balancing_y,
                        "balancing_reaction_z": reaction.balancing_z,
                        **equilibrium_fields,
                    }
                )
                p.log(
                    f"Analysis stopped before committing step {step}: "
                    "independent equilibrium safety audit failed"
                )
                return (
                    equilibrium_fields,
                    unsafe_equilibrium_steps,
                    warned_unsafe_equilibrium,
                    True,
                )

    return equilibrium_fields, unsafe_equilibrium_steps, warned_unsafe_equilibrium, False
