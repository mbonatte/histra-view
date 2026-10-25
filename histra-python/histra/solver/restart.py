"""Restore a complete committed C# nonlinear state for chained analyses."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from histra.io.results_reader import (
    ResultsStateError,
    read_dynamic_vectors,
    read_interface_states,
    read_last_committed_step,
    read_quad_states,
    read_spring_states,
)
from histra.springs.coulomb03 import SpringCoulomb03
from histra.springs.elastic import SpringElastic
from histra.springs.hysteretic import SpringHysteretic


@dataclass(frozen=True)
class RestartSummary:
    analysis_key: int
    combination: int
    step: int
    dof_count: int
    quad_count: int
    interface_count: int
    spring_count: int


def _f(values: dict[str, Any] | Any, name: str, default: float = 0.0) -> float:
    value = values.get(name, default)
    return float(default if value is None else value)


def _i(values: dict[str, Any] | Any, name: str, default: int = 0) -> int:
    value = values.get(name, default)
    return int(default if value is None else value)


def _b(values: dict[str, Any] | Any, name: str, default: bool = False) -> bool:
    value = values.get(name, default)
    return bool(default if value is None else value)


def _spring_targets(model: Any):
    """Yield C# database identities and their live Python spring objects."""
    for key, intf in model.collections.interfaces.items():
        for local, spring in enumerate(intf.trasv_1):
            yield (102, int(key), 1, local), spring
        for local, spring in enumerate(intf.slid):
            yield (102, int(key), 11, local), spring
        for local, spring in enumerate(intf.slid_out_plan):
            yield (102, int(key), 21, local), spring
    for key, quad in model.collections.quads.items():
        yield (106, int(key), 30, 0), quad.spring


def _restore_common_spring(spring: Any, values: dict[str, Any]) -> None:
    spring.u = _f(values, "U")
    spring.f = _f(values, "F")
    spring.k_tang = _f(values, "K_tang", spring.k)
    spring.k_tang_committed = spring.k_tang
    spring.phase = _i(values, "Phase")
    spring.t_phase = spring.phase


def _restore_hysteretic(spring: SpringHysteretic, values: dict[str, Any]) -> None:
    _restore_common_spring(spring, values)
    spring.umax[:] = [_f(values, "Umax1"), _f(values, "Umax2")]
    spring.uy_corr[:] = [_f(values, "Uy1"), _f(values, "Uy2")]
    spring.fy[:] = [_f(values, "Fy1"), _f(values, "Fy2")]
    spring._crot_pu = _f(values, "Uu1")
    spring._crot_nu = _f(values, "Uu2")
    spring._cload_indicator = _i(values, "LoadIndicator")
    spring.f0 = _f(values, "F0")
    spring._cstrain = spring.u
    spring._cstress = spring.f
    spring.cenergy_d = _f(values, "Ed", 0.0)
    spring.revert_to_last_commit()


def _restore_coulomb(spring: SpringCoulomb03, values: dict[str, Any]) -> None:
    _restore_common_spring(spring, values)
    spring.umax[:] = [_f(values, "Umax1"), _f(values, "Umax2")]
    spring.fy[:] = [_f(values, "Fy1"), _f(values, "Fy2")]
    spring._crot_pu = _f(values, "Uu1")
    spring._crot_nu = _f(values, "Uu2")
    spring._cload_indicator = _i(values, "LoadIndicator")
    normal = _f(values, "N")
    spring._cstress_normal = normal
    spring._cstress_normal_prev = normal
    spring._ccontact_area = _f(values, "ContactArea", spring.area)
    # C# stores two Up slots for a scalar plastic/slip displacement in this law.
    # They are equal in the benchmark; reject lossy input rather than guessing.
    up1, up2 = _f(values, "Up1"), _f(values, "Up2")
    if abs(up1 - up2) > 1.0e-12:
        raise ResultsStateError(
            f"Coulomb03 restart has unequal Up1/Up2 ({up1}, {up2}); Python state is scalar"
        )
    spring._cup = up1
    spring._cmom_min = _f(values, "CmomMin")
    # The supplied C# SetSpring omits CmomMax during non-envelope restoration.
    # Python restores the persisted value because omitting it is demonstrably lossy.
    spring._cmom_max = _f(values, "CmomMax")
    spring._crot_lim_nu = _f(values, "CrotLimNu")
    spring._crot_lim_pu = _f(values, "CrotLimPu")
    spring._crot_yn = _f(values, "CrotYn")
    spring._crot_yp = _f(values, "CrotYp")
    spring._c_phase_unload_t = _i(values, "CPhaseUnload_t")
    spring._c_phase_unload_c = _i(values, "CPhaseUnload_c")
    spring.tangent_reload_c = _f(values, "TangentReload_c")
    spring.tangent_reload_t = _f(values, "TangentReload_t")
    spring._cplastic_tension_indicator = _b(values, "CplasticTensionIndicator")
    spring._cplastic_compression_indicator = _b(values, "CplasticCompressionIndicator")
    spring._cstrain = spring.u
    spring._cstress = spring.f
    spring.cenergy_d = _f(values, "Ed", 0.0)
    spring.dn = 0.0
    spring.revert_to_last_commit()


def _restore_elastic(spring: SpringElastic, values: dict[str, Any]) -> None:
    """Restore the committed/trial pair persisted for C# linear springs."""
    _restore_common_spring(spring, values)
    spring._cstrain = spring._tstrain = spring.u
    spring._cstress = spring._tstress = spring.f
    spring.revert_to_last_commit()



def capture_committed_spring_state(spring: Any) -> dict[str, Any]:
    """Capture the C# ``SpringStates`` fields from a live committed spring.

    This intentionally captures state/history only.  Immutable constitutive
    definitions (``k``, envelope points, material coefficients) belong to the
    target spring and are not copied during an interface-material mutation.
    """
    umax = getattr(spring, "umax", (0.0, 0.0))
    fy = getattr(spring, "fy", (0.0, 0.0))
    common: dict[str, Any] = {
        "U": float(getattr(spring, "_cstrain", spring.u)),
        "F": float(getattr(spring, "_cstress", spring.f)),
        "K_tang": float(getattr(spring, "k_tang_committed", spring.k_tang)),
        "Phase": int(spring.phase),
        "Umax1": float(umax[0]),
        "Umax2": float(umax[1]),
        "Fy1": float(fy[0]),
        "Fy2": float(fy[1]),
        "Uu1": float(getattr(spring, "_crot_pu", 0.0)),
        "Uu2": float(getattr(spring, "_crot_nu", 0.0)),
        "LoadIndicator": int(getattr(spring, "_cload_indicator", 0)),
        "Ed": float(getattr(spring, "cenergy_d", 0.0)),
    }
    if isinstance(spring, SpringHysteretic):
        common.update({
            "Uy1": float(spring.uy_corr[0]),
            "Uy2": float(spring.uy_corr[1]),
            "F0": float(spring.f0),
        })
        return common
    if isinstance(spring, SpringCoulomb03):
        common.update({
            "N": float(spring._cstress_normal),
            "ContactArea": float(spring._ccontact_area),
            "Up1": float(spring._cup),
            "Up2": float(spring._cup),
            "CmomMin": float(spring._cmom_min),
            "CmomMax": float(spring._cmom_max),
            "CrotLimNu": float(spring._crot_lim_nu),
            "CrotLimPu": float(spring._crot_lim_pu),
            "CrotYn": float(spring._crot_yn),
            "CrotYp": float(spring._crot_yp),
            "CPhaseUnload_t": int(spring._c_phase_unload_t),
            "CPhaseUnload_c": int(spring._c_phase_unload_c),
            "TangentReload_c": float(spring.tangent_reload_c),
            "TangentReload_t": float(spring.tangent_reload_t),
            "CplasticTensionIndicator": bool(spring._cplastic_tension_indicator),
            "CplasticCompressionIndicator": bool(spring._cplastic_compression_indicator),
        })
        return common
    if isinstance(spring, SpringElastic):
        return common
    raise ResultsStateError(
        f"Unsupported spring state capture type {type(spring).__name__}"
    )


def transfer_committed_spring_state(source: Any, target: Any) -> None:
    """Apply a source committed history to a newly defined target spring.

    For compatible laws this mirrors native ``SpringStateDBclass.SetSpring``.
    The guarded DB restart skips incompatible types before that call; the
    Elastic/Coulomb history-preserving Python policy below is distinct.
    Interface mutations guard type changes before invoking this helper.
    """
    values = capture_committed_spring_state(source)
    if isinstance(target, SpringHysteretic) and isinstance(source, SpringHysteretic):
        _restore_hysteretic(target, values)
        return
    if isinstance(target, SpringCoulomb03) and isinstance(source, SpringCoulomb03):
        _restore_coulomb(target, values)
        return
    # The low-level native SetSpring dispatches on the new type, but the full
    # dbOutputManager restart logs/skips mismatched types. These existing
    # Elastic/Coulomb transfers deliberately preserve history in Python;
    # they do not establish parity with that guarded native restart.
    if isinstance(target, SpringCoulomb03) and isinstance(source, SpringElastic):
        _restore_coulomb(target, values)
        return
    if isinstance(target, SpringElastic) and isinstance(
        source, (SpringElastic, SpringCoulomb03)
    ):
        _restore_elastic(target, values)
        return
    raise ResultsStateError(
        "Cannot transfer committed spring state across different laws: "
        f"{type(source).__name__} -> {type(target).__name__}"
    )


def restore_committed_analysis_state(
    model: Any,
    results_path: str | Path,
    analysis_key: int,
    combination: int,
    u: Any,
    v: Any,
    ls: Any,
    *,
    step: int | None = None,
) -> RestartSummary:
    """Restore global, local, and complete spring history at a committed step.

    Restart is accepted only when the C# database contains the final complete
    ``SpringStates`` record set.  Intermediate ``SpringStatesTmp`` is not enough
    to reproduce unloading/reloading history and therefore raises explicitly.
    """
    step = read_last_committed_step(results_path, analysis_key, combination) if step is None else int(step)
    db_u, db_v, vector_step = read_dynamic_vectors(
        results_path, analysis_key, combination, step, size=int(model.gdl)
    )
    if vector_step != step:
        raise ResultsStateError(
            f"Requested restart step {step}, but DynamicVectorsState is at {vector_step}"
        )
    qstates = read_quad_states(results_path, analysis_key, combination, step)
    istates = read_interface_states(results_path, analysis_key, combination, step)
    sstates = read_spring_states(
        results_path, analysis_key, combination, step, require_complete=True
    )

    missing_quads = set(model.collections.quads) - set(qstates)
    extra_quads = set(qstates) - set(model.collections.quads)
    missing_interfaces = set(model.collections.interfaces) - set(istates)
    extra_interfaces = set(istates) - set(model.collections.interfaces)
    if missing_quads or extra_quads or missing_interfaces or extra_interfaces:
        raise ResultsStateError(
            "HRX/database element mismatch: "
            f"missing_quads={sorted(missing_quads)}, extra_quads={sorted(extra_quads)}, "
            f"missing_interfaces={sorted(missing_interfaces)}, extra_interfaces={sorted(extra_interfaces)}"
        )

    targets = dict(_spring_targets(model))
    if set(targets) != set(sstates):
        missing = sorted(set(targets) - set(sstates))
        extra = sorted(set(sstates) - set(targets))
        raise ResultsStateError(
            f"HRX/database spring mismatch: missing={missing[:10]}, extra={extra[:10]}, "
            f"counts=({len(targets)},{len(sstates)})"
        )

    # Validate spring existence, types, and law fields before mutating model or arrays
    for identity, spring in targets.items():
        if spring is None:
            raise ResultsStateError(f"Database spring {identity} maps to None in HRX")
        if not isinstance(spring, (SpringHysteretic, SpringCoulomb03, SpringElastic)):
            raise ResultsStateError(
                f"Unsupported restart spring type {type(spring).__name__} for {identity}"
            )
        if isinstance(spring, SpringCoulomb03):
            values = sstates[identity].values
            up1, up2 = _f(values, "Up1"), _f(values, "Up2")
            if abs(up1 - up2) > 1.0e-12:
                raise ResultsStateError(
                    f"Coulomb03 restart has unequal Up1/Up2 ({up1}, {up2}); Python state is scalar"
                )

    u_orig = np.array(u, copy=True)
    v_orig = np.array(v, copy=True)
    q_backups = {
        key: (
            quad.status.u.copy(),
            float(quad.status.k),
            float(quad.status.f),
            float(quad.sigma_initial),
        )
        for key, quad in model.collections.quads.items()
    }
    i_backups = {
        key: (
            intf.status.u.copy(),
            list(intf.status.forces),
            list(intf.status.bending_moments),
            list(intf.status.v),
            list(intf.status.fd),
            list(intf.f),
        )
        for key, intf in model.collections.interfaces.items()
    }
    s_backups = {
        identity: capture_committed_spring_state(spring)
        for identity, spring in targets.items()
    }

    try:
        u[:] = db_u
        v[:] = db_v
        ls.set_zero_displacement()

        for key, record in qstates.items():
            quad = model.collections.quads[key]
            quad.status.u[:] = record.u
            quad.status.k = record.k
            quad.status.f = 0.0
            quad.sigma_initial = 0.0
        for key, record in istates.items():
            intf = model.collections.interfaces[key]
            intf.status.u[:] = record.u
            intf.status.forces = record.forces
            intf.status.bending_moments = record.bending_moments
            intf.status.v[:] = [0.0] * len(intf.status.v)
            intf.status.fd[:] = [0.0] * len(intf.status.fd)
            intf.f[:] = [0.0] * len(intf.f)

        for identity, spring in targets.items():
            values = dict(sstates[identity].values)
            if isinstance(spring, SpringHysteretic):
                _restore_hysteretic(spring, values)
            elif isinstance(spring, SpringCoulomb03):
                _restore_coulomb(spring, values)
            elif isinstance(spring, SpringElastic):
                _restore_elastic(spring, values)
    except Exception:
        u[:] = u_orig
        v[:] = v_orig
        for key, (qu, qk, qf, qsig) in q_backups.items():
            quad = model.collections.quads[key]
            quad.status.u[:] = qu
            quad.status.k = qk
            quad.status.f = qf
            quad.sigma_initial = qsig
        for key, (iu, iforces, ibm, iv, ifd, intff) in i_backups.items():
            intf = model.collections.interfaces[key]
            intf.status.u[:] = iu
            intf.status.forces = iforces
            intf.status.bending_moments = ibm
            intf.status.v[:] = iv
            intf.status.fd[:] = ifd
            intf.f[:] = intff
        for identity, spring in targets.items():
            vals = s_backups[identity]
            if isinstance(spring, SpringHysteretic):
                _restore_hysteretic(spring, vals)
            elif isinstance(spring, SpringCoulomb03):
                _restore_coulomb(spring, vals)
            elif isinstance(spring, SpringElastic):
                _restore_elastic(spring, vals)
        raise

    return RestartSummary(
        analysis_key=int(analysis_key),
        combination=int(combination),
        step=step,
        dof_count=len(db_u),
        quad_count=len(qstates),
        interface_count=len(istates),
        spring_count=len(sstates),
    )
