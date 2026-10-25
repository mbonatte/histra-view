"""Pure polygon clipping and area calculation utilities for contact preprocessing.

Extracted from contact_geometry to isolate 2D/3D computational geometry operations
(Sutherland-Hodgman polygon clipping, Newell polygon area reduction) from mesh
topology generation.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

_CONTACT_DISTANCE_TOLERANCE = 2.0e-4


def _cross_2d(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float:
    return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def _polygon_area_2d(vertices: Sequence[Sequence[float]]) -> float:
    return 0.5 * sum(
        float(a[0]) * float(b[1]) - float(a[1]) * float(b[0])
        for a, b in zip(vertices, (*vertices[1:], vertices[0]))
    )


def _polygon_area_3d(points: Sequence[np.ndarray]) -> float:
    """Return a small polygon's area using Newell's exact reduction order."""
    nx = ny = nz = 0.0
    count = len(points)
    for index in range(count):
        current = points[index]
        following = points[(index + 1) % count]
        nx += (
            float(current[1]) * float(following[2])
            - float(current[2]) * float(following[1])
        )
        ny += (
            float(current[2]) * float(following[0])
            - float(current[0]) * float(following[2])
        )
        nz += (
            float(current[0]) * float(following[1])
            - float(current[1]) * float(following[0])
        )
    return 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)


def _line_intersection_2d(
    start: Sequence[float],
    end: Sequence[float],
    clip_start: Sequence[float],
    clip_end: Sequence[float],
) -> tuple[float, float]:
    dx, dy = float(end[0] - start[0]), float(end[1] - start[1])
    cx, cy = float(clip_end[0] - clip_start[0]), float(clip_end[1] - clip_start[1])
    denominator = dx * cy - dy * cx
    if abs(denominator) <= 1.0e-15:
        return (
            0.5 * (float(start[0]) + float(end[0])),
            0.5 * (float(start[1]) + float(end[1])),
        )
    t = (
        (float(clip_start[0]) - float(start[0])) * cy
        - (float(clip_start[1]) - float(start[1])) * cx
    ) / denominator
    return (float(start[0]) + t * dx, float(start[1]) + t * dy)


def _clean_clipped_polygon(
    vertices: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    deduplicated: list[tuple[float, float]] = []
    for point in vertices:
        if not deduplicated or (
            (point[0] - deduplicated[-1][0]) ** 2
            + (point[1] - deduplicated[-1][1]) ** 2
        ) > 1.0e-14:
            deduplicated.append(point)
    if len(deduplicated) > 1 and (
        (deduplicated[0][0] - deduplicated[-1][0]) ** 2
        + (deduplicated[0][1] - deduplicated[-1][1]) ** 2
    ) <= 1.0e-14:
        deduplicated.pop()

    changed = True
    while changed and len(deduplicated) > 3:
        changed = False
        cleaned: list[tuple[float, float]] = []
        count = len(deduplicated)
        for index, point in enumerate(deduplicated):
            if (
                abs(
                    _cross_2d(
                        deduplicated[index - 1],
                        point,
                        deduplicated[(index + 1) % count],
                    )
                )
                <= 1.0e-8
            ):
                changed = True
            else:
                cleaned.append(point)
        if not cleaned:
            break
        deduplicated = cleaned
    return deduplicated


def _clip_convex_quad_2d(
    subject: list[tuple[float, float]],
    clipper: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clipping while preserving parent-1 vertex order."""
    clip = list(clipper)
    # Fast 4-vertex polygon orientation check
    if len(clip) == 4:
        c0, c1, c2, c3 = clip[0], clip[1], clip[2], clip[3]
        if (
            (c0[0] * c1[1] - c0[1] * c1[0])
            + (c1[0] * c2[1] - c1[1] * c2[0])
            + (c2[0] * c3[1] - c2[1] * c3[0])
            + (c3[0] * c0[1] - c3[1] * c0[0])
        ) < 0.0:
            clip = [c3, c2, c1, c0]
    elif _polygon_area_2d(clip) < 0.0:
        clip.reverse()

    output = list(subject)
    n_clip = len(clip)
    for i in range(n_clip):
        clip_start = clip[i]
        clip_end = clip[(i + 1) % n_clip]
        cx, cy = clip_start[0], clip_start[1]
        edx = clip_end[0] - cx
        edy = clip_end[1] - cy

        input_vertices = output
        output = []
        if not input_vertices:
            break
        start = input_vertices[-1]
        start_inside = (
            edx * (start[1] - cy) - edy * (start[0] - cx)
        ) >= -_CONTACT_DISTANCE_TOLERANCE
        for end in input_vertices:
            end_inside = (
                edx * (end[1] - cy) - edy * (end[0] - cx)
            ) >= -_CONTACT_DISTANCE_TOLERANCE
            if end_inside:
                if not start_inside:
                    dx = end[0] - start[0]
                    dy = end[1] - start[1]
                    denom = dx * edy - dy * edx
                    if abs(denom) <= 1.0e-15:
                        output.append(
                            (0.5 * (start[0] + end[0]), 0.5 * (start[1] + end[1]))
                        )
                    else:
                        t = ((cx - start[0]) * edy - (cy - start[1]) * edx) / denom
                        output.append((start[0] + t * dx, start[1] + t * dy))
                output.append(end)
            elif start_inside:
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                denom = dx * edy - dy * edx
                if abs(denom) <= 1.0e-15:
                    output.append(
                        (0.5 * (start[0] + end[0]), 0.5 * (start[1] + end[1]))
                    )
                else:
                    t = ((cx - start[0]) * edy - (cy - start[1]) * edx) / denom
                    output.append((start[0] + t * dx, start[1] + t * dy))
            start, start_inside = end, end_inside
    return _clean_clipped_polygon(output)
