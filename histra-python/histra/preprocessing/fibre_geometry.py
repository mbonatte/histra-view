"""Interface spring-cell geometry and C# ``Quad.GetFiberProperties`` kernels.

The scalar functions in this module are exact test oracles and fallbacks; the
real multi-cell production path is the Numba/NumPy batch family
(``_interface_cells_nb``, ``_polygon_areas_3d_nb``, ``_fiber_stiffness_batch_nb``).

Numerical notes that must survive any refactor of this module:

* ``_bilinear_nb`` preserves the legacy scalar evaluation order.
  Precomputing the four shape-function weights changes floating-point rounding
  because ``vertex * ((1 +/- u) * (1 +/- v) / 4)`` is not bitwise identical to
  ``vertex * (1 +/- u) * (1 +/- v) / 4``. Cell areas feed spring stiffnesses.
* Interface polygons are Microsoft.Xna.Framework.Vector3 values in C#, so the
  compiled cell construction starts in the local plane, retains single
  precision through the global transformation, and then selected results
  are promoted to double.
* The compiled inverse bilinear returns error codes (degenerate mapping,
  zero fibre length, degenerate projection, zero area) that the scalar
  reference raises as :class:`ModelPreparationError`; both paths must agree on
  which cells fail.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

try:
    from numba import njit
except Exception:  # pragma: no cover - scalar fallback remains available
    njit = None

from histra.elements.interface import Interface
from histra.elements.quad import Quad
from histra.model.model import Model
from histra.preprocessing.afference import (
    _bilinear,
    _inverse_bilinear,
)
from histra.preprocessing.contact_geometry import (
    _cross3,
    _norm3,
    _polygon_area_3d,
    _quad_vint,
    _unit,
    _v,
)
from histra.preprocessing.errors import ModelPreparationError
from histra.preprocessing.csharp_fibre_geometry import _csharp_stiffness


def _cell_vertices(intf: Interface, index: int) -> list[np.ndarray]:
    """C# Interface.GetSpringCoordinate: local Vector2 cells, then global."""
    f = np.float32
    row, col = divmod(index, intf.ncol)
    vertices = np.asarray([(p.x, p.y) for p in intf.vint2d], dtype=np.float32)
    axes = np.asarray([intf.reference_e1, intf.reference_e2, intf.reference_e3], dtype=np.float32).T
    origin = np.asarray(_v(intf.reference_origin), dtype=np.float32)
    result = []
    for c, r in ((col, row), (col+1, row), (col+1, row+1), (col, row+1)):
        u = f(f(f(c)*f(2))/f(intf.ncol)-f(1))
        v = f(f(f(r)*f(2))/f(intf.nrow)-f(1))
        terms = [
            f(f(f(vertices[k]*f(f(1)+f(su)*u))*f(f(1)+f(sv)*v))/f(4))
            for k, (su, sv) in enumerate(((-1,-1),(1,-1),(1,1),(-1,1)))
        ]
        local = f(f(f(terms[0]+terms[1])+terms[2])+terms[3])
        # Operations.MatrixPerVector3 includes the zero local-Y term and
        # adds translation last; do not interpolate translated vertices.
        point = f(f(f(axes[:,0]*local[0]+axes[:,1]*f(0))+axes[:,2]*local[1])+origin)
        result.append(point)
    return result


if njit is not None:
    @njit(cache=True, inline="always")
    def _dot3_nb(a, b):
        return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

    @njit(cache=True, inline="always")
    def _norm3_nb(a):
        return math.sqrt(a[0]*a[0] + a[1]*a[1] + a[2]*a[2])

    @njit(cache=True, inline="always")
    def _cross3_nb(a, b, out):
        out[0] = a[1]*b[2] - a[2]*b[1]
        out[1] = a[2]*b[0] - a[0]*b[2]
        out[2] = a[0]*b[1] - a[1]*b[0]

    @njit(cache=True, inline="always")
    def _bilinear_nb(vertices, u, v, out):
        # Preserve the scalar/C# evaluation order exactly.  Precomputing the
        # four shape-function weights changes floating-point rounding because
        # ``vertex * ((1 +/- u) * (1 +/- v) / 4)`` is not bitwise identical
        # to ``vertex * (1 +/- u) * (1 +/- v) / 4``.  Cell areas feed spring
        # stiffnesses, so keep the authoritative operation sequence here.
        for j in range(3):
            term0 = vertices[0,j]*(1.0-u)*(1.0-v)/4.0
            term1 = vertices[1,j]*(1.0+u)*(1.0-v)/4.0
            term2 = vertices[2,j]*(1.0+u)*(1.0+v)/4.0
            term3 = vertices[3,j]*(1.0-u)*(1.0+v)/4.0
            out[j] = term0 + term1 + term2 + term3

    @njit(cache=True, nogil=True)
    def _interface_cells_nb(vertices, axes, origin, nrow, ncol):
        # Port Interface.GetAreaTrasvSpringIntrinsicCoordinates,
        # GetAreaTrasvSpringCoordinate and Operations.MatrixPerVector3.
        f = np.float32
        cells = np.empty((nrow*ncol, 4, 3), dtype=np.float32)
        local = np.empty(2, dtype=np.float32)
        for row in range(nrow):
            for col in range(ncol):
                index = row*ncol+col
                for corner in range(4):
                    c = col + (1 if corner == 1 or corner == 2 else 0)
                    r = row + (1 if corner == 2 or corner == 3 else 0)
                    u = f(f(f(c)*f(2))/f(ncol)-f(1))
                    v = f(f(f(r)*f(2))/f(nrow)-f(1))
                    for j in range(2):
                        t0 = f(f(f(vertices[0,j]*f(f(1)-u))*f(f(1)-v))/f(4))
                        t1 = f(f(f(vertices[1,j]*f(f(1)+u))*f(f(1)-v))/f(4))
                        t2 = f(f(f(vertices[2,j]*f(f(1)+u))*f(f(1)+v))/f(4))
                        t3 = f(f(f(vertices[3,j]*f(f(1)-u))*f(f(1)+v))/f(4))
                        local[j] = f(f(f(t0+t1)+t2)+t3)
                    for j in range(3):
                        cells[index,corner,j] = f(f(f(axes[j,0]*local[0]+axes[j,1]*f(0))+axes[j,2]*local[1])+origin[j])
        return cells

    @njit(cache=True, nogil=True)
    def _polygon_areas_3d_nb(cells):
        areas = np.empty(cells.shape[0], dtype=np.float64)
        for cell_index in range(cells.shape[0]):
            nx = 0.0
            ny = 0.0
            nz = 0.0
            for index in range(cells.shape[1]):
                following = (index + 1) % cells.shape[1]
                x0 = cells[cell_index, index, 0]
                y0 = cells[cell_index, index, 1]
                z0 = cells[cell_index, index, 2]
                x1 = cells[cell_index, following, 0]
                y1 = cells[cell_index, following, 1]
                z1 = cells[cell_index, following, 2]
                nx += y0 * z1 - z0 * y1
                ny += z0 * x1 - x0 * z1
                nz += x0 * y1 - y0 * x1
            areas[cell_index] = 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)
        return areas

    @njit(cache=True, inline="always")
    def _inverse_bilinear_nb(vertices, point):
        a = np.empty(3, dtype=np.float32)
        b = np.empty(3, dtype=np.float32)
        normal = np.empty(3, dtype=np.float32)
        for j in range(3):
            a[j] = vertices[1,j] - vertices[0,j]
            b[j] = vertices[3,j] - vertices[0,j]
        _cross3_nb(a, b, normal)
        drop = 0
        if abs(normal[1]) > abs(normal[drop]):
            drop = 1
        if abs(normal[2]) > abs(normal[drop]):
            drop = 2
        if drop == 0:
            k0, k1 = 1, 2
        elif drop == 1:
            k0, k1 = 0, 2
        else:
            k0, k1 = 0, 1
        u = 0.0
        v = 0.0
        mapped = np.empty(3, dtype=np.float32)
        du = np.empty(3, dtype=np.float32)
        dv = np.empty(3, dtype=np.float32)
        for _ in range(20):
            _bilinear_nb(vertices, u, v, mapped)
            for j in range(3):
                du[j] = (-vertices[0,j]*(1.0-v) + vertices[1,j]*(1.0-v) + vertices[2,j]*(1.0+v) - vertices[3,j]*(1.0+v))/4.0
                dv[j] = (-vertices[0,j]*(1.0-u) - vertices[1,j]*(1.0+u) + vertices[2,j]*(1.0+u) + vertices[3,j]*(1.0-u))/4.0
            j00, j01 = du[k0], dv[k0]
            j10, j11 = du[k1], dv[k1]
            r0 = point[k0] - mapped[k0]
            r1 = point[k1] - mapped[k1]
            det = j00*j11 - j01*j10
            if abs(det) <= 1.0e-30:
                return 0.0, 0.0, -1
            delta_u = (j11*r0 - j01*r1) / det
            delta_v = (-j10*r0 + j00*r1) / det
            u += delta_u
            v += delta_v
            if max(abs(delta_u), abs(delta_v)) < 1.0e-10:
                break
        return u, v, 0

    # Use the source-owning kernel directly: a cached wrapper can retain an
    # older imported stiffness implementation after numerical corrections.
    from histra.preprocessing.csharp_fibre_geometry import (
        _csharp_fibre_stiffness_batch_nb as _fiber_stiffness_batch_nb,
    )
else:
    _fiber_stiffness_batch_nb = None


def _interface_cells(intf: Interface) -> np.ndarray:
    nrow = int(intf.nrow)
    ncol = int(intf.ncol)
    if nrow <= 0 or ncol <= 0:
        raise ModelPreparationError(
            f"Interface {intf.key} has invalid spring grid "
            f"Nrow={nrow}, Ncol={ncol}."
        )
    vertices = np.asarray([(p.x, p.y) for p in intf.vint2d], dtype=np.float32)
    axes = np.asarray([intf.reference_e1, intf.reference_e2, intf.reference_e3], dtype=np.float32).T
    origin = np.asarray(_v(intf.reference_origin), dtype=np.float32)
    if njit is not None:
        return _interface_cells_nb(vertices, axes, origin, nrow, ncol)
    return np.asarray(
        [_cell_vertices(intf, index) for index in range(nrow * ncol)],
        dtype=np.float32,
    )


def _polygon_areas_3d(cells: np.ndarray) -> np.ndarray:
    cells = np.asarray(cells, dtype=np.float64)
    if njit is not None:
        return _polygon_areas_3d_nb(cells)
    return np.asarray([_polygon_area_3d(cell) for cell in cells], dtype=np.float64)


def _fiber_stiffness_batch(model: Model, quad: Quad, intf: Interface,
                            cells: np.ndarray, E: float, face: int) -> np.ndarray:
    if _fiber_stiffness_batch_nb is None:
        return np.asarray([
            _fiber_stiffness(model, quad, intf, cell, E, face) for cell in cells
        ], dtype=float)
    vints = _quad_vint(model, quad)
    opposite = {0:2,1:3,2:0,3:1,4:5,5:4}[face]
    far_face = vints[opposite]
    # C# Quad.GetFiberProperties reverses the opposite broad face explicitly:
    # face 4 uses VInt[5, 3..0], and face 5 uses VInt[4, 3..0].
    if face >= 4:
        far_face = tuple(reversed(far_face))
    output = np.zeros((len(cells),3), dtype=np.float64)
    errors = np.zeros(len(cells), dtype=np.int32)
    _fiber_stiffness_batch_nb(
        np.asarray(vints[face], dtype=np.float32),
        np.asarray(far_face, dtype=np.float32),
        np.asarray(cells, dtype=np.float32), float(E),
        np.asarray(intf.reference_e2, dtype=np.float32), output, errors,
    )
    if np.any(errors):
        index = int(np.flatnonzero(errors)[0])
        raise ModelPreparationError(
            f"Quad {quad.key}, Interface {intf.key}: compiled fibre geometry error {errors[index]} at cell {index}."
        )
    return output

def _fiber_stiffness(model: Model, quad: Quad, intf: Interface, cell: Sequence[np.ndarray],
                     E: float, face: int) -> tuple[float, float, float]:
    """Scalar entry point for the source-verified C# fibre geometry port."""
    vints = _quad_vint(model, quad)
    opposite = {0:2,1:3,2:0,3:1,4:5,5:4}[face]
    far_face = vints[opposite]
    if face >= 4:
        far_face = tuple(reversed(far_face))
    scalar = getattr(_csharp_stiffness, "py_func", _csharp_stiffness)
    result = scalar(np.asarray(vints[face], dtype=np.float32),
                    np.asarray(far_face, dtype=np.float32),
                    np.asarray(cell, dtype=np.float32), float(E),
                    np.asarray(intf.reference_e2, dtype=np.float32))
    if not all(math.isfinite(value) for value in result) or result[1] <= 0 or result[2] <= 0:
        raise ModelPreparationError(f"Quad {quad.key}, Interface {intf.key}: degenerate fibre geometry.")
    return tuple(map(float, result))
