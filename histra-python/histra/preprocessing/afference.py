"""Generalized-DOF afference mappings and inverse bilinear interpolation.

The Quad and Interface afference matrices translated from C#
``ModelManager.PrepareModel`` / ``AfferenceMatrix`` live here, together with the
float32 forward/inverse bilinear maps used by the shear-DOF warping
interpolation (C# ``Operations.GetValueFromIntrinsecSystem`` and
``GetIntrinsecCoordinates``).

Numerical notes that must survive any refactor of this module:

* the C# inverse is a bisection over projected polygon strips, not a Newton
  solve; the bisection reference is kept alongside the faster float32 Newton
  path that reproduces the converged serialized results;
* every float32 operation is explicit (``np.float32`` casts and helper
  rounding) because the shear-DOF afference coefficients are sensitive to
  reduction order;
* the Numba kernels mirror the scalar float32 reference operation by
  operation and are compared bit-exactly by ``uint32`` patterns in tests.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np

try:
    from numba import njit
except Exception:  # pragma: no cover - scalar fallback remains available
    njit = None

from histra.elements.interface_state import InterfaceState
from histra.elements.quad import Quad
from histra.model.model import Model
from histra.preprocessing.contact_geometry import (
    _cross3,
    _cross3_f32,
    _dot3_f32,
    _f32,
    _unit_f32,
    _v,
)
from histra.preprocessing.errors import ModelPreparationError
from histra.types.afference_entry import AfferenceEntry


@dataclass(frozen=True)
class _QuadAfferenceGeometry:
    centre: np.ndarray
    vertices: np.ndarray
    normal: np.ndarray
    warping_nodal: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
    node_tolerance: float = 1.0


def _assign_quad_afference(model: Model) -> None:
    assert model.collections is not None
    gdl = 1
    for quad in sorted(model.collections.quads.values(), key=lambda item: item.key):
        if quad.master_element_key not in (0, -1):
            raise ModelPreparationError(
                f"Quad {quad.key} is a slave of {quad.master_element_type} {quad.master_element_key}; "
                "slave-element constraints are not translated."
            )
        quad.aff = [[AfferenceEntry(gdl=gdl + i, alfa=1.0)] for i in range(7)]
        gdl += 7
    model.gdl = gdl - 1


def _warping_nodal_vectors(quad: Quad, normal: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    # Quad.GetDisplacementFromShearDOF builds these vectors with XNA Vector3
    # and Convert.ToSingle intermediates.
    e1 = np.asarray(quad.reference_e1, dtype=np.float32)
    e2 = (np.asarray(quad.reference_e2, dtype=np.float32) if normal is None
          else _cross3_f32(normal, e1))
    zero = np.zeros(3, dtype=np.float32)
    if abs(quad.sin[2]) <= 1.0e-12:
        node2 = zero.copy()
    else:
        scale_e1 = _f32(
            -float(quad.length[3]) * float(quad.sin[3])
            * float(quad.sin[1]) / float(quad.sin[2])
        )
        scale_e2 = _f32(
            -float(quad.length[3]) * float(quad.sin[3])
            * float(quad.cos[1]) / float(quad.sin[2])
        )
        node2 = np.asarray(
            [
                _f32(_f32(e1[i] * scale_e1) + _f32(e2[i] * scale_e2))
                for i in range(3)
            ],
            dtype=np.float32,
        )
    scale_e1 = _f32(-float(quad.length[3]) * float(quad.sin[0]))
    scale_e2 = _f32(float(quad.length[3]) * float(quad.cos[0]))
    node3 = np.asarray(
        [
            _f32(_f32(e1[i] * scale_e1) + _f32(e2[i] * scale_e2))
            for i in range(3)
        ],
        dtype=np.float32,
    )
    return zero.copy(), zero.copy(), node2, node3


def _quad_afference_geometry(model: Model, quad: Quad) -> _QuadAfferenceGeometry:
    assert model.collections is not None
    vertices = np.asarray(
        [_v(model.collections.nodes[key].point) for key in quad.node_keys],
        dtype=np.float32,
    )
    normal = _unit_f32(
        _cross3_f32(vertices[1] - vertices[0], vertices[2] - vertices[0]),
        label=f"Quad {quad.key} midsurface normal",
    )
    return _QuadAfferenceGeometry(
        centre=np.asarray(_v(quad.g), dtype=np.float32),
        vertices=vertices,
        normal=normal,
        warping_nodal=_warping_nodal_vectors(quad, normal),
        node_tolerance=float(getattr(model, "geometry_tolerance_node", 1.0)),
    )


def _warping_vector_from_geometry(
    geometry: _QuadAfferenceGeometry, point: np.ndarray
) -> np.ndarray:
    from histra.preprocessing.intrinsic_coordinates import native_projected_intrinsic

    u, v = native_projected_intrinsic(
        geometry.vertices, np.asarray(point, dtype=np.float32),
        np.float32(geometry.node_tolerance),
    )
    return _bilinear_f32(geometry.warping_nodal, u, v)
def _warping_vector_at_point(quad: Quad, point: np.ndarray, model: Model) -> np.ndarray:
    """C# ``GetDisplacementFromShearDOF`` for an arbitrary face point.

    C# projects the interface endpoint onto the Quad midsurface, solves its
    intrinsic coordinates and bilinearly interpolates the four nodal warping
    vectors. Restricting this operation to centre-line edges loses the offset
    lateral contacts created by the full surface-intersection algorithm.
    """
    return _warping_vector_from_geometry(
        _quad_afference_geometry(model, quad), point
    )


def _point_afference(
    model: Model, quad: Quad, point: np.ndarray, node_key: int,
    direction: np.ndarray, *, face: int,
    _geometry: _QuadAfferenceGeometry | None = None,
    _point_cache: dict[
        tuple[int, int], tuple[np.ndarray, np.ndarray | None]
    ] | None = None,
) -> list[AfferenceEntry]:
    geometry = (
        _quad_afference_geometry(model, quad)
        if _geometry is None
        else _geometry
    )
    cache_key = (int(quad.key), int(node_key))
    cached = None if _point_cache is None else _point_cache.get(cache_key)
    if cached is None:
        r = np.asarray(point, dtype=np.float32) - geometry.centre
        warping = None
    else:
        r, warping = cached

    if face <= 3 and warping is None:
        warping = _warping_vector_from_geometry(geometry, point)
    if _point_cache is not None:
        if cached is None or (cached[1] is None and warping is not None):
            _point_cache[cache_key] = (r, warping)

    direction_f = (
        direction
        if isinstance(direction, np.ndarray) and direction.dtype == np.float32
        else np.asarray(direction, dtype=np.float32)
    )
    dx, dy, dz = direction_f
    rx, ry, rz = float(r[0]), float(r[1]), float(r[2])
    shear = _f32(0.0) if face > 3 else _dot3_f32(warping, direction_f)
    coeff = (
        float(dx),
        float(dy),
        float(dz),
        float(_f32(_f32(ry * dz) - _f32(rz * dy))),
        float(_f32(_f32(rz * dx) - _f32(rx * dz))),
        float(_f32(_f32(rx * dy) - _f32(ry * dx))),
        shear,
    )
    out: list[AfferenceEntry] = []
    # C# Quad.PointAfference delegates to
    # AfferenceMatrix.SetFromCoefficients, which discards coefficients whose
    # absolute value is not greater than 1e-4.
    for local, value in enumerate(coeff):
        if abs(value) <= 1.0e-4:
            continue
        for entry in quad.aff[local]:
            out.append(
                AfferenceEntry(gdl=entry.gdl, alfa=float(value * entry.alfa))
            )
    return out


def _rotation_afference(quad: Quad, direction: np.ndarray) -> list[AfferenceEntry]:
    out: list[AfferenceEntry] = []
    for local in range(3, 6):
        value = float(np.float32(direction[local - 3]))
        # InterfacePoligonalOperations.ComputeAff applies the same 1e-4
        # directional cutoff before adding rotational afference terms.
        if abs(value) <= 1.0e-4:
            continue
        for entry in quad.aff[local]:
            out.append(AfferenceEntry(gdl=entry.gdl, alfa=value * entry.alfa))
    return out


def _assign_interface_afference(model: Model) -> None:
    assert model.collections is not None
    c = model.collections
    geometry_cache: dict[int, _QuadAfferenceGeometry] = {}
    point_cache: dict[
        tuple[int, int], tuple[np.ndarray, np.ndarray | None]
    ] = {}
    for intf in c.interfaces.values():
        intf.aff = [[] for _ in range(12)]
        e1 = np.asarray(intf.reference_e1, dtype=np.float32)
        e2 = np.asarray(intf.reference_e2, dtype=np.float32)
        e3 = np.asarray(intf.reference_e3, dtype=np.float32)
        points = [_v(c.nodes[k].point) for k in intf.node_keys]
        parents = [
            (intf.parent_type_element1, intf.parent_element_key1, 0),
            (intf.parent_type_element2, intf.parent_element_key2, 1),
        ]
        for typ, key, side in parents:
            if typ == "Restraint":
                continue
            if typ != "Quad":
                raise ModelPreparationError(
                    f"Interface {intf.key} has unsupported parent type {typ!r}."
                )
            quad = c.quads[key]
            geometry = geometry_cache.get(int(quad.key))
            if geometry is None:
                geometry = _quad_afference_geometry(model, quad)
                geometry_cache[int(quad.key)] = geometry
            parent_face = intf.face1 if side == 0 else intf.face2
            if side == 0:
                slots_e2 = (0, 1)
                slot_rot, slot_flex = 4, 6
                slots_e3 = (8, 9)
            else:
                slots_e2 = (3, 2)
                slot_rot, slot_flex = 5, 7
                slots_e3 = (10, 11)
            common = {
                "face": parent_face,
                "_geometry": geometry,
                "_point_cache": point_cache,
            }
            intf.aff[slots_e2[0]] = _point_afference(
                model, quad, points[0], intf.node_keys[0], e2, **common
            )
            intf.aff[slots_e2[1]] = _point_afference(
                model, quad, points[1], intf.node_keys[1], e2, **common
            )
            intf.aff[slot_rot] = _rotation_afference(quad, e1)
            intf.aff[slot_flex] = _point_afference(
                model, quad, points[1], intf.node_keys[1], e1, **common
            )
            intf.aff[slots_e3[0]] = _point_afference(
                model, quad, points[0], intf.node_keys[0], e3, **common
            )
            intf.aff[slots_e3[1]] = _point_afference(
                model, quad, points[1], intf.node_keys[1], e3, **common
            )
        intf.status = InterfaceState()
        intf.status.init_from_interface(intf)
        intf._perf_aff_pairs = None


def _bilinear(vertices: Sequence[np.ndarray], u: float, v: float) -> np.ndarray:
    return (
        vertices[0] * (1.0-u)*(1.0-v)/4.0
        + vertices[1] * (1.0+u)*(1.0-v)/4.0
        + vertices[2] * (1.0+u)*(1.0+v)/4.0
        + vertices[3] * (1.0-u)*(1.0+v)/4.0
    )


def _bilinear_f32(
    vertices: Sequence[np.ndarray], u: np.float32, v: np.float32
) -> np.ndarray:
    """C# ``Operations.GetValueFromIntrinsecSystem`` in single precision."""
    one = _f32(1.0)
    four = _f32(4.0)
    weights = (
        _f32(_f32(_f32(one-u) * _f32(one-v)) / four),
        _f32(_f32(_f32(one+u) * _f32(one-v)) / four),
        _f32(_f32(_f32(one+u) * _f32(one+v)) / four),
        _f32(_f32(_f32(one-u) * _f32(one+v)) / four),
    )
    out = np.zeros(3, dtype=np.float32)
    for vertex, weight in zip(vertices, weights):
        vertex_f = np.asarray(vertex, dtype=np.float32)
        for index in range(3):
            out[index] = _f32(out[index] + _f32(vertex_f[index] * weight))
    return out


def _inverse_bilinear_f32_bisection_reference(
    vertices: Sequence[np.ndarray], point: np.ndarray
) -> tuple[np.float32, np.float32]:
    """C# ``Operations.GetIntrinsecCoordinates`` compatibility path.

    Despite the method's purpose, the desktop code does not use a Newton
    inverse.  It projects the surface to a local 2-D system and bisects two
    polygon strips to a tolerance of 0.001.  Replacing it with an algebraically
    more accurate inverse changes the shear-DOF afference by up to 4e-3 in the
    bridge models.
    """
    vertices_f = tuple(np.asarray(vertex, dtype=np.float32) for vertex in vertices)
    point_f = np.asarray(point, dtype=np.float32)
    e1 = _unit_f32(vertices_f[1]-vertices_f[0], label="intrinsic e1")
    normal = _unit_f32(
        _cross3_f32(e1, vertices_f[3]-vertices_f[0]),
        label="intrinsic normal",
    )
    e2 = _cross3_f32(normal, e1)

    def project(value: np.ndarray) -> np.ndarray:
        delta = np.asarray(value-vertices_f[0], dtype=np.float32)
        return np.asarray(
            (_dot3_f32(delta, e1), _dot3_f32(delta, e2)),
            dtype=np.float32,
        )

    polygon = tuple(project(vertex) for vertex in vertices_f)
    target = project(point_f)
    tolerance_node = 1.0

    def align(value: np.ndarray, start: np.ndarray, end: np.ndarray) -> int:
        x, y = float(value[0]), float(value[1])
        x1, y1 = float(start[0]), float(start[1])
        x2, y2 = float(end[0]), float(end[1])
        if abs(x-x1) < tolerance_node and abs(y-y1) < tolerance_node:
            return 2
        if abs(x-x2) < tolerance_node and abs(y-y2) < tolerance_node:
            return 3
        dx, dy = x2-x1, y2-y1
        px, py = x-x1, y-y1
        length = math.sqrt(dx*dx+dy*dy)
        point_length = math.sqrt(px*px+py*py)
        if length == 0.0 or point_length == 0.0:
            return 0
        cosine = max(-1.0, min(1.0, (dx*px+dy*py)/(length*point_length)))
        distance = math.sqrt(max(0.0, 1.0-cosine*cosine))*point_length
        if not (-tolerance_node < distance < tolerance_node):
            return 0
        return 1 if cosine > 0.0 and point_length <= length else -1

    def inside(poly: Sequence[np.ndarray]) -> bool:
        previous = len(poly)-1
        flag = False
        for index, vertex in enumerate(poly):
            following = poly[(index+1) % len(poly)]
            if align(target, vertex, following) > 0:
                return True
            py = target[1]
            if (
                ((vertex[1] <= py < poly[previous][1])
                 or (poly[previous][1] <= py < vertex[1]))
                and target[0] < _f32(
                    _f32(poly[previous][0]-vertex[0])
                    * _f32(py-vertex[1])
                    / _f32(poly[previous][1]-vertex[1])
                    + vertex[0]
                )
            ):
                flag = not flag
            previous = index
        return flag

    if align(target, polygon[0], polygon[3]) > 0:
        u = _f32(-1.0)
    elif align(target, polygon[1], polygon[2]) > 0:
        u = _f32(1.0)
    else:
        u = _f32(0.0)
        lower = _f32(-1.0)
        upper = _f32(1.0)
        x5 = _f32((polygon[2][0]+polygon[3][0])/np.float32(2.0))
        y5 = _f32((polygon[2][1]+polygon[3][1])/np.float32(2.0))
        x6 = _f32((polygon[0][0]+polygon[1][0])/np.float32(2.0))
        y6 = _f32((polygon[0][1]+polygon[1][1])/np.float32(2.0))
        if inside(polygon):
            for _ in range(1000):
                if float(upper-lower) < 0.001:
                    break
                strip = (polygon[0], np.asarray((x6,y6),dtype=np.float32),
                         np.asarray((x5,y5),dtype=np.float32), polygon[3])
                if inside(strip):
                    upper = u
                    u = _f32((lower+u)/np.float32(2.0))
                else:
                    lower = u
                    u = _f32((upper+u)/np.float32(2.0))
                x6 = _f32(
                    _f32(polygon[0][0]*_f32(1.0-u))/np.float32(2.0)
                    + _f32(polygon[1][0]*_f32(1.0+u))/np.float32(2.0)
                )
                y6 = _f32(
                    _f32(polygon[0][1]*_f32(1.0-u))/np.float32(2.0)
                    + _f32(polygon[1][1]*_f32(1.0+u))/np.float32(2.0)
                )
                x5 = _f32(
                    _f32(polygon[2][0]*_f32(1.0+u))/np.float32(2.0)
                    + _f32(polygon[3][0]*_f32(1.0-u))/np.float32(2.0)
                )
                y5 = _f32(
                    _f32(polygon[2][1]*_f32(1.0+u))/np.float32(2.0)
                    + _f32(polygon[3][1]*_f32(1.0-u))/np.float32(2.0)
                )

    if align(target, polygon[0], polygon[1]) > 0:
        v = _f32(-1.0)
    elif align(target, polygon[3], polygon[2]) > 0:
        v = _f32(1.0)
    else:
        v = _f32(0.0)
        lower = _f32(-1.0)
        upper = _f32(1.0)
        x5 = _f32((polygon[2][0]+polygon[1][0])/np.float32(2.0))
        y5 = _f32((polygon[2][1]+polygon[1][1])/np.float32(2.0))
        x6 = _f32((polygon[0][0]+polygon[3][0])/np.float32(2.0))
        y6 = _f32((polygon[0][1]+polygon[3][1])/np.float32(2.0))
        if inside(polygon):
            for _ in range(1000):
                if float(upper-lower) < 0.001:
                    break
                strip = (polygon[0], polygon[1],
                         np.asarray((x5,y5),dtype=np.float32),
                         np.asarray((x6,y6),dtype=np.float32))
                if inside(strip):
                    upper = v
                    v = _f32((lower+v)/np.float32(2.0))
                else:
                    lower = v
                    v = _f32((upper+v)/np.float32(2.0))
                x6 = _f32(
                    _f32(polygon[0][0]*_f32(1.0-v))/np.float32(2.0)
                    + _f32(polygon[3][0]*_f32(1.0+v))/np.float32(2.0)
                )
                y6 = _f32(
                    _f32(polygon[0][1]*_f32(1.0-v))/np.float32(2.0)
                    + _f32(polygon[3][1]*_f32(1.0+v))/np.float32(2.0)
                )
                x5 = _f32(
                    _f32(polygon[1][0]*_f32(1.0-v))/np.float32(2.0)
                    + _f32(polygon[2][0]*_f32(1.0+v))/np.float32(2.0)
                )
                y5 = _f32(
                    _f32(polygon[1][1]*_f32(1.0-v))/np.float32(2.0)
                    + _f32(polygon[2][1]*_f32(1.0+v))/np.float32(2.0)
                )
    return u, v


def _inverse_bilinear_f32_python(
    vertices: Sequence[np.ndarray], point: np.ndarray
) -> tuple[np.float32, np.float32]:
    """Scalar reference for the float32 afference inverse.

    The desktop bisection is retained above as a literal reference, but its
    one-unit geometric edge tolerance depends on mutable application globals.
    On the supplied serialized model the converged intrinsic coordinates are
    reproduced more reliably by this float32 Newton solve.
    """
    vertices_f = tuple(np.asarray(vertex, dtype=np.float32) for vertex in vertices)
    point_f = np.asarray(point, dtype=np.float32)
    normal = _cross3_f32(vertices_f[1]-vertices_f[0], vertices_f[3]-vertices_f[0])
    drop = int(np.argmax(np.abs(normal)))
    keep0, keep1 = (1, 2) if drop == 0 else ((0, 2) if drop == 1 else (0, 1))
    target0, target1 = point_f[keep0], point_f[keep1]
    u = _f32(0.0)
    v = _f32(0.0)
    four = _f32(4.0)
    one = _f32(1.0)
    for _ in range(20):
        mapped = _bilinear_f32(vertices_f, u, v)
        du = np.asarray([
            _f32(
                _f32(
                    _f32(-vertices_f[0][i] * _f32(one-v))
                    + _f32(vertices_f[1][i] * _f32(one-v))
                )
                + _f32(
                    _f32(vertices_f[2][i] * _f32(one+v))
                    - _f32(vertices_f[3][i] * _f32(one+v))
                )
            ) / four
            for i in range(3)
        ], dtype=np.float32)
        dv = np.asarray([
            _f32(
                _f32(
                    _f32(-vertices_f[0][i] * _f32(one-u))
                    - _f32(vertices_f[1][i] * _f32(one+u))
                )
                + _f32(
                    _f32(vertices_f[2][i] * _f32(one+u))
                    + _f32(vertices_f[3][i] * _f32(one-u))
                )
            ) / four
            for i in range(3)
        ], dtype=np.float32)
        j00, j01 = du[keep0], dv[keep0]
        j10, j11 = du[keep1], dv[keep1]
        r0 = _f32(target0 - mapped[keep0])
        r1 = _f32(target1 - mapped[keep1])
        det = _f32(_f32(j00*j11) - _f32(j01*j10))
        if abs(float(det)) <= 1.0e-20:
            break
        step_u = _f32(_f32(_f32(r0*j11) - _f32(j01*r1)) / det)
        step_v = _f32(_f32(_f32(j00*r1) - _f32(r0*j10)) / det)
        u = _f32(u + step_u)
        v = _f32(v + step_v)
        if max(abs(float(step_u)), abs(float(step_v))) <= 1.0e-6:
            break
    return u, v


if njit is not None:
    @njit(cache=True, inline="always")
    def _bilinear_component_f32_nb(vertices, u, v, component):
        """One component of ``_bilinear_f32`` with identical reductions."""
        one = np.float32(1.0)
        four = np.float32(4.0)
        weights = np.empty(4, dtype=np.float32)
        weights[0] = np.float32(
            np.float32(np.float32(one - u) * np.float32(one - v)) / four
        )
        weights[1] = np.float32(
            np.float32(np.float32(one + u) * np.float32(one - v)) / four
        )
        weights[2] = np.float32(
            np.float32(np.float32(one + u) * np.float32(one + v)) / four
        )
        weights[3] = np.float32(
            np.float32(np.float32(one - u) * np.float32(one + v)) / four
        )
        value = np.float32(0.0)
        for index in range(4):
            value = np.float32(
                value + np.float32(vertices[index, component] * weights[index])
            )
        return value

    @njit(cache=True, nogil=True)
    def _inverse_bilinear_f32_nb(vertices, point):
        """Compiled equivalent of ``_inverse_bilinear_f32_python``."""
        edge10 = np.empty(3, dtype=np.float32)
        edge30 = np.empty(3, dtype=np.float32)
        for index in range(3):
            edge10[index] = np.float32(vertices[1, index] - vertices[0, index])
            edge30[index] = np.float32(vertices[3, index] - vertices[0, index])
        normal = np.empty(3, dtype=np.float32)
        normal[0] = np.float32(
            np.float32(edge10[1] * edge30[2])
            - np.float32(edge10[2] * edge30[1])
        )
        normal[1] = np.float32(
            np.float32(edge10[2] * edge30[0])
            - np.float32(edge10[0] * edge30[2])
        )
        normal[2] = np.float32(
            np.float32(edge10[0] * edge30[1])
            - np.float32(edge10[1] * edge30[0])
        )
        drop = 0
        if abs(normal[1]) > abs(normal[drop]):
            drop = 1
        if abs(normal[2]) > abs(normal[drop]):
            drop = 2
        if drop == 0:
            keep0, keep1 = 1, 2
        elif drop == 1:
            keep0, keep1 = 0, 2
        else:
            keep0, keep1 = 0, 1

        target0 = point[keep0]
        target1 = point[keep1]
        u = np.float32(0.0)
        v = np.float32(0.0)
        one = np.float32(1.0)
        four = np.float32(4.0)
        for _ in range(20):
            mapped0 = _bilinear_component_f32_nb(vertices, u, v, keep0)
            mapped1 = _bilinear_component_f32_nb(vertices, u, v, keep1)
            one_minus_v = np.float32(one - v)
            one_plus_v = np.float32(one + v)
            one_minus_u = np.float32(one - u)
            one_plus_u = np.float32(one + u)

            du0 = np.float32(
                np.float32(
                    np.float32(-vertices[0, keep0] * one_minus_v)
                    + np.float32(vertices[1, keep0] * one_minus_v)
                )
                + np.float32(
                    np.float32(vertices[2, keep0] * one_plus_v)
                    - np.float32(vertices[3, keep0] * one_plus_v)
                )
            ) / four
            du1 = np.float32(
                np.float32(
                    np.float32(-vertices[0, keep1] * one_minus_v)
                    + np.float32(vertices[1, keep1] * one_minus_v)
                )
                + np.float32(
                    np.float32(vertices[2, keep1] * one_plus_v)
                    - np.float32(vertices[3, keep1] * one_plus_v)
                )
            ) / four
            dv0 = np.float32(
                np.float32(
                    np.float32(-vertices[0, keep0] * one_minus_u)
                    - np.float32(vertices[1, keep0] * one_plus_u)
                )
                + np.float32(
                    np.float32(vertices[2, keep0] * one_plus_u)
                    + np.float32(vertices[3, keep0] * one_minus_u)
                )
            ) / four
            dv1 = np.float32(
                np.float32(
                    np.float32(-vertices[0, keep1] * one_minus_u)
                    - np.float32(vertices[1, keep1] * one_plus_u)
                )
                + np.float32(
                    np.float32(vertices[2, keep1] * one_plus_u)
                    + np.float32(vertices[3, keep1] * one_minus_u)
                )
            ) / four

            r0 = np.float32(target0 - mapped0)
            r1 = np.float32(target1 - mapped1)
            det = np.float32(
                np.float32(du0 * dv1) - np.float32(dv0 * du1)
            )
            if abs(det) <= 1.0e-20:
                break
            step_u = np.float32(
                np.float32(np.float32(r0 * dv1) - np.float32(dv0 * r1)) / det
            )
            step_v = np.float32(
                np.float32(np.float32(du0 * r1) - np.float32(r0 * du1)) / det
            )
            u = np.float32(u + step_u)
            v = np.float32(v + step_v)
            if max(abs(float(step_u)), abs(float(step_v))) <= 1.0e-6:
                break
        return u, v
else:  # pragma: no cover - exercised when Numba is unavailable
    _inverse_bilinear_f32_nb = None


def _inverse_bilinear_f32(
    vertices: Sequence[np.ndarray], point: np.ndarray
) -> tuple[np.float32, np.float32]:
    """Stable float32 inverse used by the afference compatibility path."""
    vertices_f = np.asarray(vertices, dtype=np.float32)
    point_f = np.asarray(point, dtype=np.float32)
    if _inverse_bilinear_f32_nb is None:
        return _inverse_bilinear_f32_python(vertices_f, point_f)
    u, v = _inverse_bilinear_f32_nb(vertices_f, point_f)
    return np.float32(u), np.float32(v)


def _inverse_bilinear(vertices: Sequence[np.ndarray], point: np.ndarray) -> tuple[float, float]:
    # C# solves a 2x2 Newton system.  Avoiding np.linalg.lstsq for this tiny,
    # repeated system removes tens of thousands of LAPACK/Python crossings.
    normal = _cross3(vertices[1]-vertices[0], vertices[3]-vertices[0])
    drop = int(np.argmax(np.abs(normal)))
    keep0, keep1 = (1, 2) if drop == 0 else ((0, 2) if drop == 1 else (0, 1))
    target0 = float(point[keep0])
    target1 = float(point[keep1])
    u = v = 0.0
    for _ in range(20):
        mapped = _bilinear(vertices, u, v)
        du = (-vertices[0]*(1-v) + vertices[1]*(1-v) + vertices[2]*(1+v) - vertices[3]*(1+v))/4.0
        dv = (-vertices[0]*(1-u) - vertices[1]*(1+u) + vertices[2]*(1+u) + vertices[3]*(1-u))/4.0
        j00, j01 = float(du[keep0]), float(dv[keep0])
        j10, j11 = float(du[keep1]), float(dv[keep1])
        r0 = target0 - float(mapped[keep0])
        r1 = target1 - float(mapped[keep1])
        det = j00*j11 - j01*j10
        if abs(det) <= 1.0e-30:
            raise ModelPreparationError("Degenerate bilinear face mapping.")
        delta_u = (j11*r0 - j01*r1) / det
        delta_v = (-j10*r0 + j00*r1) / det
        u += delta_u
        v += delta_v
        if max(abs(delta_u), abs(delta_v)) < 1.0e-10:
            break
    return u, v
