"""Immutable compact topology and spring-state extraction for the batch runtime.

Owns the pieces that are built once per model and never mutate during Newton
corrections: the interface slice record, the inverted local-force afference
topology used by the force-by-DOF scatter, and the parameter/committed/trial
extraction helpers that copy Python spring state into dense rows.

Construction may use plain Python because it runs once per preparation; no
Python work may be added to each Newton correction. The extraction helpers are
also the scalar oracle for the compiled kernels' dense layouts.
"""
from __future__ import annotations

from dataclasses import dataclass
from operator import attrgetter
from typing import Any

import numpy as np

from histra.springs.hysteretic import SpringHysteretic
from histra.solver.hysteretic_kernels.transverse import (
    COMPRESSIVE_PARABOLIC,
    SIMPLE_PARAM_NAMES,
    TENSILE_EXPONENTIAL,
    TENSILE_LINEAR,
    TENSILE_ELASTIC,
    _PARAM_NAMES,
)
from histra.types.phase_enum import PhaseEnum


_PARAM_GETTER = attrgetter(*_PARAM_NAMES)

_SIMPLE_PARAM_GETTER = attrgetter(*SIMPLE_PARAM_NAMES)


@dataclass(frozen=True)
class _InterfaceSlice:
    interface: Any
    start: int
    stop: int


def _build_force_by_dof_topology(
    global_size: int,
    interface_offsets: np.ndarray,
    interface_gdls: np.ndarray,
    interface_coefficients: np.ndarray,
    quad_offsets: np.ndarray,
    quad_gdls: np.ndarray,
    quad_coefficients: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Invert immutable local-force afferences without reordering a DOF."""
    interface_force_size = int(interface_offsets.size - 1)
    counts = np.zeros(global_size, dtype=np.int32)

    for gdls in (interface_gdls, quad_gdls):
        for value in gdls:
            gdl = int(value)
            if 0 <= gdl < global_size:
                counts[gdl] += 1

    global_offsets = np.empty(global_size + 1, dtype=np.int32)
    global_offsets[0] = 0
    np.cumsum(counts, out=global_offsets[1:])
    force_indices = np.empty(int(global_offsets[-1]), dtype=np.int32)
    force_coefficients = np.empty(int(global_offsets[-1]), dtype=np.float64)
    cursors = global_offsets[:-1].copy()

    def append_topology(
        offsets: np.ndarray,
        gdls: np.ndarray,
        coefficients: np.ndarray,
        source_offset: int,
    ) -> None:
        for local_index in range(offsets.size - 1):
            for pair_index in range(int(offsets[local_index]), int(offsets[local_index + 1])):
                gdl = int(gdls[pair_index])
                if not 0 <= gdl < global_size:
                    continue
                destination = int(cursors[gdl])
                force_indices[destination] = source_offset + local_index
                force_coefficients[destination] = coefficients[pair_index]
                cursors[gdl] += 1

    append_topology(
        interface_offsets, interface_gdls, interface_coefficients, 0
    )
    append_topology(
        quad_offsets, quad_gdls, quad_coefficients, interface_force_size
    )
    return (
        global_offsets,
        force_indices,
        force_coefficients,
        interface_force_size,
    )

def _extract_spring_params(spring: Any, is_compact: bool) -> tuple:
    if isinstance(spring, SpringHysteretic):
        getter = _SIMPLE_PARAM_GETTER if is_compact else _PARAM_GETTER
        return getter(spring)
    else:
        k = float(spring.k)
        huge = 1e27
        if is_compact:
            return (
                huge, huge * k, huge, 0.0, 0.0, 0.0,
                -huge * k, -huge, 0.0, 0.0, 0.0, 0.0,
                k, k, 0.0, 0.0, 0.0, 0.0, k, k
            )
        else:
            return (
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                huge, huge * k, huge, 0.0, 0.0, 0.0,
                -huge * k, -huge, 0.0, 0.0, 0.0, 0.0,
                k, k, 0.0, 0.0, 0.0, 0.0, k, k,
                0.0, k
            )

def _extract_spring_committed(spring: Any) -> tuple:
    if isinstance(spring, SpringHysteretic):
        return (
            float(spring.umax[0]), float(spring.umax[1]), float(spring._crot_pu),
            float(spring._crot_nu), float(spring.cenergy_d),
            int(spring._cload_indicator), float(spring._cstress),
            float(spring._cstrain), int(spring.phase),
        )
    else:
        k = float(spring.k)
        u = float(spring.u)
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0, float(spring._cstress), float(spring._cstrain), int(PhaseEnum.Elastic))

def _extract_spring_trial(spring: Any) -> tuple:
    if isinstance(spring, SpringHysteretic):
        return (
            float(spring._trot_max), float(spring._trot_min), float(spring._trot_pu),
            float(spring._trot_nu), float(spring._tenergy_d),
            int(spring._tload_indicator), float(spring._tstress),
            float(spring._tstrain), int(spring.t_phase), float(spring.k_tang),
        )
    else:
        k = float(spring.k)
        u = float(spring.u)
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0, float(spring._tstress), float(spring._tstrain), int(PhaseEnum.Elastic), float(spring.k_tang))

def _extract_spring_target(spring: Any) -> float:
    if isinstance(spring, SpringHysteretic):
        return float(spring._tstrain)
    return float(spring.u)

def _extract_spring_curve_type(spring: Any) -> float:
    if not isinstance(spring, SpringHysteretic):
        return float(TENSILE_ELASTIC)
    if isinstance(spring, SpringHysteretic) and spring.tensile_curve_type == "Exponential":
        return float(TENSILE_EXPONENTIAL)
    return float(TENSILE_LINEAR)


def _extract_spring_compressive_curve_type(spring: Any) -> float:
    if isinstance(spring, SpringHysteretic) and spring.compressive_curve_type == "Parabolic":
        return float(COMPRESSIVE_PARABOLIC)
    return 0.0
