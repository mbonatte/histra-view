from __future__ import annotations

import numpy as np

try:
    from numba import njit
except Exception:  # pragma: no cover
    njit = None


def _sum4_f32(
    a: np.float32,
    b: np.float32,
    c: np.float32,
    d: np.float32,
) -> np.float32:
    return np.float32(np.float32(np.float32(a + b) + c) + d)


if njit is not None:
    _sum4_f32_nb = njit(cache=True, inline="always")(_sum4_f32)
else:  # pragma: no cover
    _sum4_f32_nb = _sum4_f32


def _compute_static_load_area_scalar(
    node_coords: np.ndarray,
    nodal_forces: np.ndarray,
    centre: np.ndarray,
    reference_e1: np.ndarray,
    reference_e2: np.ndarray,
    length: np.ndarray,
    sin: np.ndarray,
    cos: np.ndarray,
) -> np.ndarray:
    """Scalar C#-parity implementation used when Numba is unavailable."""
    f32 = np.float32
    out = np.zeros(7, dtype=np.float64)
    gp = f32(f32(np.sqrt(3.0)) / f32(3.0))
    gauss = (gp, f32(-gp))

    transform = np.zeros((4, 3, 7), dtype=np.float32)
    for i in range(4):
        dx = f32(node_coords[i, 0] - centre[0])
        dy = f32(node_coords[i, 1] - centre[1])
        dz = f32(node_coords[i, 2] - centre[2])
        transform[i, 0, 0] = f32(1.0)
        transform[i, 1, 1] = f32(1.0)
        transform[i, 2, 2] = f32(1.0)
        transform[i, 0, 4] = dz
        transform[i, 0, 5] = f32(-dy)
        transform[i, 1, 3] = f32(-dz)
        transform[i, 1, 5] = dx
        transform[i, 2, 3] = dy
        transform[i, 2, 4] = f32(-dx)

    for component in range(3):
        transform[2, component, 6] = f32(
            -float(length[3])
            * float(sin[3])
            / float(sin[2])
            * (
                float(sin[1]) * float(reference_e1[component])
                + float(cos[1]) * float(reference_e2[component])
            )
        )
        transform[3, component, 6] = f32(
            -float(length[3])
            * (
                float(sin[0]) * float(reference_e1[component])
                - float(cos[0]) * float(reference_e2[component])
            )
        )

    length0 = f32(length[0])
    length1 = f32(length[1])
    length3 = f32(length[3])
    cos0 = f32(cos[0])
    cos1 = f32(cos[1])
    sin0 = f32(sin[0])
    sin1 = f32(sin[1])
    local = np.zeros((4, 2), dtype=np.float32)
    local[0, 0] = f32(f32(-length0) / f32(2.0))
    local[1, 0] = f32(length0 / f32(2.0))
    local[2, 0] = f32(f32(length0 / f32(2.0)) - f32(length1 * cos1))
    local[2, 1] = f32(length1 * sin1)
    local[3, 0] = f32(f32(-length0) / f32(2.0) + f32(length3 * cos0))
    local[3, 1] = f32(length3 * sin0)

    one = f32(1.0)
    four = f32(4.0)
    for xi in gauss:
        for eta in gauss:
            shape0 = f32(f32(one - xi) * f32(one - eta) / four)
            shape1 = f32(f32(one + xi) * f32(one - eta) / four)
            shape2 = f32(f32(one + xi) * f32(one + eta) / four)
            shape3 = f32(f32(one - xi) * f32(one + eta) / four)

            dxi0 = f32(-f32(one - eta) / four)
            dxi1 = f32(f32(one - eta) / four)
            dxi2 = f32(f32(one + eta) / four)
            dxi3 = f32(-f32(one + eta) / four)
            deta0 = f32(-f32(one - xi) / four)
            deta1 = f32(-f32(one + xi) / four)
            deta2 = f32(f32(one + xi) / four)
            deta3 = f32(f32(one - xi) / four)

            j11 = _sum4_f32_nb(
                f32(local[0, 0] * dxi0),
                f32(local[1, 0] * dxi1),
                f32(local[2, 0] * dxi2),
                f32(local[3, 0] * dxi3),
            )
            j12 = _sum4_f32_nb(
                f32(local[0, 0] * deta0),
                f32(local[1, 0] * deta1),
                f32(local[2, 0] * deta2),
                f32(local[3, 0] * deta3),
            )
            j21 = _sum4_f32_nb(
                f32(local[0, 1] * dxi0),
                f32(local[1, 1] * dxi1),
                f32(local[2, 1] * dxi2),
                f32(local[3, 1] * dxi3),
            )
            j22 = _sum4_f32_nb(
                f32(local[0, 1] * deta0),
                f32(local[1, 1] * deta1),
                f32(local[2, 1] * deta2),
                f32(local[3, 1] * deta3),
            )
            det_j = f32(f32(j11 * j22) - f32(j12 * j21))

            force_gp = np.empty(3, dtype=np.float32)
            transform_gp = np.empty((3, 7), dtype=np.float32)
            shapes = (shape0, shape1, shape2, shape3)
            for component in range(3):
                force_gp[component] = _sum4_f32_nb(
                    f32(shape0 * nodal_forces[0, component]),
                    f32(shape1 * nodal_forces[1, component]),
                    f32(shape2 * nodal_forces[2, component]),
                    f32(shape3 * nodal_forces[3, component]),
                )
            for row in range(3):
                for column in range(7):
                    transform_gp[row, column] = _sum4_f32_nb(
                        f32(transform[0, row, column] * shapes[0]),
                        f32(transform[1, row, column] * shapes[1]),
                        f32(transform[2, row, column] * shapes[2]),
                        f32(transform[3, row, column] * shapes[3]),
                    )
            for column in range(7):
                projection = f32(
                    f32(
                        f32(force_gp[0] * transform_gp[0, column])
                        + f32(force_gp[1] * transform_gp[1, column])
                    )
                    + f32(force_gp[2] * transform_gp[2, column])
                )
                out[column] += float(f32(projection * det_j))
    return out


if njit is not None:
    _compute_static_load_area_nb = njit(cache=True, nogil=True)(
        _compute_static_load_area_scalar
    )
else:  # pragma: no cover
    _compute_static_load_area_nb = None


def compute_static_load_area(
    node_coords: np.ndarray,
    nodal_forces: np.ndarray,
    centre: np.ndarray,
    reference_e1: np.ndarray,
    reference_e2: np.ndarray,
    length: np.ndarray,
    sin: np.ndarray,
    cos: np.ndarray,
) -> np.ndarray:
    """Integrate one Quad area load using exact C# float32 operation order."""
    arrays = (
        np.ascontiguousarray(node_coords, dtype=np.float32),
        np.ascontiguousarray(nodal_forces, dtype=np.float32),
        np.ascontiguousarray(centre, dtype=np.float32),
        np.ascontiguousarray(reference_e1, dtype=np.float32),
        np.ascontiguousarray(reference_e2, dtype=np.float32),
        np.ascontiguousarray(length, dtype=np.float64),
        np.ascontiguousarray(sin, dtype=np.float64),
        np.ascontiguousarray(cos, dtype=np.float64),
    )
    if _compute_static_load_area_nb is not None:
        return _compute_static_load_area_nb(*arrays)
    return _compute_static_load_area_scalar(*arrays)
