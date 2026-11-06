"""C# float32 spring moment arms, compiled without reassociation or fastmath.

The scalar postprocessing helper remains the differential oracle. Preserve every
Single boundary and the four-corner accumulation order from CalcolaRisultanti.
"""
from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True, nogil=True)
def _spring_centroid(vertices, length, nrow, ncol, spring_index):
    f32 = np.float32
    ncol = max(int(ncol), 1)
    nrow = max(int(nrow), 1)
    id_row = spring_index // ncol + 1
    id_spring = spring_index + 1 - (id_row - 1) * ncol

    f_ncol = f32(ncol)
    f_nrow = f32(nrow)
    x0 = f32(f32(f32(f32(id_spring) - f32(1.0)) * f32(2.0)) / f_ncol - f32(1.0))
    y0 = f32(f32(f32(id_row - 1) * f32(2.0)) / f_nrow - f32(1.0))
    x1 = f32(f32(f32(id_spring) * f32(2.0)) / f_ncol - f32(1.0))
    y1 = f32(f32(f32(f32(id_row) - f32(1.0)) * f32(2.0)) / f_nrow - f32(1.0))
    x2 = x1
    y2 = f32(f32(f32(id_row) * f32(2.0)) / f_nrow - f32(1.0))
    x3 = x0
    y3 = y2
    corners = ((x0, y0), (x1, y1), (x2, y2), (x3, y3))

    v0x, v0y = f32(vertices[0, 0]), f32(vertices[0, 1])
    v1x, v1y = f32(vertices[1, 0]), f32(vertices[1, 1])
    v2x, v2y = f32(vertices[2, 0]), f32(vertices[2, 1])
    v3x, v3y = f32(vertices[3, 0]), f32(vertices[3, 1])
    origin_x = f32(f32(length) / f32(2.0))

    vec_x = f32(0.0)
    vec_y = f32(0.0)
    for vx, vy in corners:
        one_m_x = f32(f32(1.0) - vx)
        one_p_x = f32(f32(1.0) + vx)
        one_m_y = f32(f32(1.0) - vy)
        one_p_y = f32(f32(1.0) + vy)
        c0x = f32(f32(f32(v0x * one_m_x) * one_m_y) / f32(4.0))
        c0y = f32(f32(f32(v0y * one_m_x) * one_m_y) / f32(4.0))
        c1x = f32(f32(f32(v1x * one_p_x) * one_m_y) / f32(4.0))
        c1y = f32(f32(f32(v1y * one_p_x) * one_m_y) / f32(4.0))
        c2x = f32(f32(f32(v2x * one_p_x) * one_p_y) / f32(4.0))
        c2y = f32(f32(f32(v2y * one_p_x) * one_p_y) / f32(4.0))
        c3x = f32(f32(f32(v3x * one_m_x) * one_p_y) / f32(4.0))
        c3y = f32(f32(f32(v3y * one_m_x) * one_p_y) / f32(4.0))
        coord_x = f32(f32(f32(c0x + c1x) + c2x) + c3x)
        coord_y = f32(f32(f32(c0y + c1y) + c2y) + c3y)
        vec_x = f32(vec_x + f32(coord_x - origin_x))
        vec_y = f32(vec_y + coord_y)

    return f32(vec_x / f32(4.0)), f32(vec_y / f32(4.0))


@njit(cache=True, nogil=True)
def resultant_moment_arms(vertices, lengths, nrows, ncols, starts, stops, total):
    x = np.empty(total, dtype=np.float32)
    y = np.empty(total, dtype=np.float32)
    for record in range(starts.size):
        for index in range(starts[record], stops[record]):
            cx, cy = _spring_centroid(vertices[record], lengths[record],
                                      nrows[record], ncols[record], index - starts[record])
            x[index], y[index] = cx, cy
    return x, y
