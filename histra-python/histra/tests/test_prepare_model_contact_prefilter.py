from __future__ import annotations

import numpy as np

from histra.preprocessing.contact_geometry import (
    _CONTACT_DISTANCE_TOLERANCE,
    _convex_quad_overlap_prefilter_batch,
    _coplanar_quad_intersection_prechecked,
)


def _plane_basis(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    normal = normal / np.linalg.norm(normal)
    seed = np.asarray((1.0, 0.0, 0.0)) if abs(normal[0]) < 0.8 else np.asarray((0.0, 1.0, 0.0))
    u = np.cross(normal, seed)
    u /= np.linalg.norm(u)
    return u, np.cross(normal, u)


def _rectangle(
    origin: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    width: float,
    height: float,
    angle: float,
    offset_u: float = 0.0,
    offset_v: float = 0.0,
) -> np.ndarray:
    cosine = np.cos(angle)
    sine = np.sin(angle)
    axis_u = cosine * u + sine * v
    axis_v = -sine * u + cosine * v
    centre = origin + offset_u * u + offset_v * v
    signs_u = np.asarray((-1.0, 1.0, 1.0, -1.0))
    signs_v = np.asarray((-1.0, -1.0, 1.0, 1.0))
    return (
        centre
        + signs_u[:, None] * (0.5 * width) * axis_u
        + signs_v[:, None] * (0.5 * height) * axis_v
    )


def test_convex_quad_numeric_prefilter_never_rejects_scalar_intersection() -> None:
    rng = np.random.default_rng(94821)
    count = 1500
    first = np.empty((count, 4, 3), dtype=np.float64)
    second = np.empty_like(first)
    normals = np.empty((count, 3), dtype=np.float64)

    for index in range(count):
        normal = rng.normal(size=3)
        normal /= np.linalg.norm(normal)
        u, v = _plane_basis(normal)
        origin = rng.normal(size=3)
        normals[index] = normal
        first[index] = _rectangle(
            origin, u, v,
            float(rng.uniform(0.1, 5.0)),
            float(rng.uniform(0.1, 5.0)),
            float(rng.uniform(-np.pi, np.pi)),
        )
        second[index] = _rectangle(
            origin, u, v,
            float(rng.uniform(0.1, 5.0)),
            float(rng.uniform(0.1, 5.0)),
            float(rng.uniform(-np.pi, np.pi)),
            float(rng.uniform(-6.0, 6.0)),
            float(rng.uniform(-6.0, 6.0)),
        )

    keep = _convex_quad_overlap_prefilter_batch(first, second, normals)
    for index in range(count):
        scalar = _coplanar_quad_intersection_prechecked(
            first[index], second[index], normals[index]
        )
        if scalar is not None:
            assert bool(keep[index]), f"prefilter rejected scalar contact {index}"


def test_convex_quad_numeric_prefilter_is_conservative_near_contact_tolerance() -> None:
    normal = np.asarray((0.0, 0.0, 1.0))
    u = np.asarray((1.0, 0.0, 0.0))
    v = np.asarray((0.0, 1.0, 0.0))
    origin = np.zeros(3)
    first = _rectangle(origin, u, v, 2.0, 2.0, 0.0)
    # Deliberately leave less than twice the scalar clipping tolerance between
    # the faces. The prefilter must defer this borderline case to clipping.
    second = _rectangle(
        origin, u, v, 2.0, 2.0, 0.0,
        offset_u=2.0 + 1.5 * _CONTACT_DISTANCE_TOLERANCE,
    )
    keep = _convex_quad_overlap_prefilter_batch(
        first[None, :, :], second[None, :, :], normal[None, :]
    )
    assert bool(keep[0]) is True
