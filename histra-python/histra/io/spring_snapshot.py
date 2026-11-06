"""Gather committed spring responses without hydrating dense fibre proxies."""
from __future__ import annotations

import numpy as np

from histra.io.spring_response import project_spring_response, ELASTIC, HYSTERETIC, COULOMB
from histra.springs.elastic import SpringElastic
from histra.springs.hysteretic import SpringHysteretic
from histra.springs.coulomb03 import SpringCoulomb03
from histra.solver.hysteretic_kernels import interface_coulomb as ic
from histra.solver.hysteretic_kernels import quad_takeda as qt


def _definition(spring):
    if isinstance(spring, SpringElastic):
        kind = ELASTIC
    elif isinstance(spring, SpringHysteretic):
        kind = HYSTERETIC
    elif isinstance(spring, SpringCoulomb03):
        kind = COULOMB
    else:
        raise ValueError(f'Unsupported spring response: {type(spring).__name__}')
    return (kind, spring.length, spring.k, *getattr(spring, 'fy', (0.0, 0.0)),
            *getattr(spring, 'ur', (0.0, 0.0)))


def _definitions(springs):
    return np.asarray([_definition(s) for s in springs], np.float64).reshape(-1, 7)


def _transverse_definitions(interfaces):
    chunks = []
    for interface in interfaces:
        group = interface.trasv_1
        if not getattr(group, 'is_batch_backed', False):
            chunks.append(_definitions(group))
            continue
        count = len(group)
        values = np.empty((count, 7), np.float64)
        values[:, 0], values[:, 1], values[:, 2] = HYSTERETIC, 0.0, group._k
        values[:, 3:5] = group._fy if group._fy is not None else group._params[:, [1, 6]]
        values[:, 5:7] = group._ur if group._ur is not None else group._params[:, [2, 8]]
        # Respect existing explicit proxy overrides; never create new proxies.
        for index, spring in group._cache.items():
            values[index] = _definition(spring)
        chunks.append(values)
    return np.concatenate(chunks) if chunks else np.empty((0, 7), np.float64)


def _project(arrays, kind, definitions, u, force, phase, tangent):
    fields = project_spring_response(u, force, definitions[:, 2], definitions[:, 3:5],
                                    definitions[:, 5:7], definitions[:, 1], definitions[:, 0], phase, tangent)
    arrays.update({f'springs/{kind}_{key}': value for key, value in fields.items()})


def add_spring_responses(runtime, interfaces, transverse, sliding, arrays):
    """CSR spans and Quad ordering follow the existing export snapshot."""
    committed = runtime.committed[transverse]
    _project(arrays, 'transverse', _transverse_definitions(interfaces), committed[:, 7],
             committed[:, 6], committed[:, 8], runtime.trial[transverse, 9])
    state = runtime.coulomb_state[sliding]
    definitions = _definitions(runtime.coulomb_springs[index] for index in sliding)
    definitions[:, 3:5] = state[:, [ic.CFY0, ic.CFY1]]
    _project(arrays, 'sliding', definitions, state[:, ic.CCSTRAIN], state[:, ic.CCSTRESS],
             state[:, ic.CCPHASE], state[:, ic.CKTANG_COMMITTED])
    _add_plastic_history(arrays, 'sliding', definitions[:, 0],
                         state[:, ic.CCPLASTIC_T], state[:, ic.CCPLASTIC_C])
    _add_quad_responses(runtime, arrays)


def _add_quad_responses(runtime, arrays):
    by_key = {quad.key: index for index, quad in enumerate(runtime.quad_records)}
    order = np.asarray([by_key[int(key)] for key in arrays['mesh/quad_keys']], np.intp)
    quads = [runtime.quad_records[index] for index in order]
    state = runtime.quad_state[order]
    definitions = _definitions(quad.spring for quad in quads)
    definitions[:, 3:5] = state[:, [qt.QFY0, qt.QFY1]]
    definitions[:, 5:7] = state[:, [qt.QUR0, qt.QUR1]]
    _project(arrays, 'quad', definitions, state[:, qt.QCSTRAIN], state[:, qt.QCSTRESS],
             state[:, qt.QPHASE], state[:, qt.QKTANG_COMMITTED])
    arrays['springs/quad_force'] = state[:, qt.QCSTRESS].astype(np.float32)
    arrays['springs/quad_phase'] = state[:, qt.QPHASE].astype(np.int8)
    area = np.asarray([quad.spring.area for quad in quads], np.float64)
    valid = np.isfinite(area) & (area > 0)
    stress = np.zeros_like(area)
    np.divide(10.0 * state[:, qt.QCSTRESS], area, out=stress, where=valid)
    arrays['springs/quad_area'] = area.astype(np.float32)
    arrays['springs/quad_stress'] = stress.astype(np.float32)
    arrays['springs/quad_stress_valid'] = valid.astype(np.uint8)
    _add_plastic_history(arrays, 'quad', definitions[:, 0],
                         state[:, qt.QCPLAST_T], state[:, qt.QCPLAST_C])


def _add_plastic_history(arrays, kind, spring_type, tension, compression):
    valid = spring_type == COULOMB
    arrays[f'springs/{kind}_plastic_history_valid'] = valid.astype(np.uint8)
    arrays[f'springs/{kind}_plastic_tension_indicator'] = (valid & tension.astype(bool)).astype(np.uint8)
    arrays[f'springs/{kind}_plastic_compression_indicator'] = (valid & compression.astype(bool)).astype(np.uint8)
