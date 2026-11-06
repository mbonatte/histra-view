"""Plot-ready histories of named model points, using C# output projections."""
from __future__ import annotations

import numpy as np

from histra.solver.output_projection import model_point_displacement, OutputProjectionError


def _coordinates(collections, point):
    kind = str(point.element_type).casefold().split('.')[-1]
    if kind == 'node':
        position = collections.nodes[int(point.element_key)].point
    elif kind == 'quad':
        quad = collections.quads[int(point.element_key)]
        vertex = int(point.id_vertex)
        if vertex == 0:
            position = quad.g
        elif 1 <= vertex <= len(quad.node_keys):
            position = collections.nodes[quad.node_keys[vertex - 1]].point
        else:
            raise OutputProjectionError(f'ModelPoint {point.key} has unsupported IdVertex={vertex}')
    else:
        raise OutputProjectionError(f'Unsupported ModelPoint element type: {point.element_type}')
    return [float(position.x), float(position.y), float(position.z)]


def _point_history(model, point, steps, analysis):
    name = str(getattr(point, 'name', '') or '')
    description = str(getattr(point, 'description', '') or '')
    active = getattr(analysis, 'active_model_points', {}) or {}
    record = dict(key=int(point.key), name=name, description=description,
                  label=name or description or f'Model point {point.key}',
                  element_key=int(point.element_key), element_type=str(point.element_type),
                  id_vertex=int(point.id_vertex), active=bool(active.get(int(point.key), False)),
                  control=int(getattr(analysis, 'master_point', -10)) == int(point.key))
    try:
        coordinates = _coordinates(model.collections, point)
        if not np.isfinite(coordinates).all():
            raise OutputProjectionError('Nonfinite model-point location')
        record['coordinates_cm'] = coordinates
        values = _displacements(model, point, steps)
        if not np.isfinite(values).all():
            raise OutputProjectionError('Nonfinite model-point displacement')
    except (OutputProjectionError, KeyError, IndexError) as exc:
        record.update(available=False, error=str(exc), displacement_cm=None, displacement_mm=None)
        record.setdefault('coordinates_cm', None)
        return record
    record.update(available=True, error=None)
    record['displacement_cm'] = {key: values[:, index].tolist() for index, key in enumerate(('ux', 'uy', 'uz'))}
    record['displacement_mm'] = {key: (values[:, index] * 10.0).tolist() for index, key in enumerate(('ux', 'uy', 'uz'))}
    return record


def _displacements(model, point, steps):
    values = []
    for step in steps:
        if np.asarray(step.u).shape != (int(model.gdl),):
            raise OutputProjectionError(f"Expected displacement vector length {model.gdl}")
        values.append(model_point_displacement(model.collections, point, step.u))
    return np.asarray(values, dtype=np.float64).reshape(-1, 3)


def build_model_point_summary(model, steps, analysis=None):
    """Include all defined points; active/control flags do not filter monitoring."""
    points = getattr(model.collections, 'model_points', {}) or {}
    steps = tuple(steps)
    return {
        'scope': 'initial_and_committed_steps',
        'axes': ['x', 'y', 'z'],
        'step': [int(step.step) for step in steps],
        'units': {'coordinates': 'cm', 'displacement_cm': 'cm', 'displacement_mm': 'mm'},
        'points': [_point_history(model, point, steps, analysis)
                   for _, point in sorted(points.items())],
    }
