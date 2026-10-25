"""C#-compatible mass-matrix assembly for HiStrA macro-elements.

The active C# ``Quad.ComputeLocalMassfromSelfWeight`` implementation always
integrates a consistent 7x7 macro-element mass matrix with a 6x6x6 Gauss rule.
Its ``diagonal``/``MassMatrixType`` argument is currently ignored; this module
preserves that observed behaviour for numerical parity.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable

import numpy as np
import scipy.sparse as sp

# Original Operations.g and MasonryMaterial.w are System.Single.
GRAVITY_ACCELERATION = float(np.float32(980.6))
_GAUSS_COORDS, _GAUSS_WEIGHTS_1D = np.polynomial.legendre.leggauss(6)
_GAUSS_POINTS = np.asarray(
    [(a, b, c) for a in _GAUSS_COORDS for b in _GAUSS_COORDS for c in _GAUSS_COORDS],
    dtype=float,
)
_GAUSS_WEIGHTS = np.asarray(
    [wa * wb * wc for wa in _GAUSS_WEIGHTS_1D for wb in _GAUSS_WEIGHTS_1D for wc in _GAUSS_WEIGHTS_1D],
    dtype=float,
)


class MassMatrixError(RuntimeError):
    """Raised when a C#-compatible mass matrix cannot be assembled."""


@dataclass(frozen=True)
class MassMatrixAssembly:
    matrix: sp.csc_matrix
    requested_type: str
    effective_type: str
    quad_count: int


def _shape3(coords: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """C# ``FForma(0)`` trilinear-hexahedron shape functions and derivatives."""
    a = coords[:, 0]
    b = coords[:, 1]
    c = coords[:, 2]
    ap, am = 1.0 + a, 1.0 - a
    bp, bm = 1.0 + b, 1.0 - b
    cp, cm = 1.0 + c, 1.0 - c
    n = np.column_stack(
        (
            ap * bp * cp,
            ap * bm * cp,
            ap * bm * cm,
            ap * bp * cm,
            am * bp * cp,
            am * bm * cp,
            am * bm * cm,
            am * bp * cm,
        )
    ) / 8.0
    da = np.column_stack(
        (bp * cp, bm * cp, bm * cm, bp * cm, -bp * cp, -bm * cp, -bm * cm, -bp * cm)
    ) / 8.0
    db = np.column_stack(
        (ap * cp, -ap * cp, -ap * cm, ap * cm, am * cp, -am * cp, -am * cm, am * cm)
    ) / 8.0
    dc = np.column_stack(
        (ap * bp, ap * bm, -ap * bm, -ap * bp, am * bp, am * bm, -am * bm, -am * bp)
    ) / 8.0
    return n, da, db, dc


_N8, _D1, _D2, _D3 = _shape3(_GAUSS_POINTS)


def _map_hexahedron(
    coordinates: np.ndarray, natural_coordinate: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n, da, db, dc = _shape3(np.asarray(natural_coordinate, dtype=float).reshape(1, 3))
    return n[0] @ coordinates, da[0] @ coordinates, db[0] @ coordinates, dc[0] @ coordinates


def _invert_hexahedron(target: np.ndarray, coordinates: np.ndarray) -> np.ndarray:
    """Newton inversion matching the role of C# ``FForma.Invert3D``."""
    natural = np.zeros(3, dtype=float)
    previous_error = float("inf")
    for _ in range(100):
        position, dx1, dx2, dx3 = _map_hexahedron(coordinates, natural)
        jacobian = np.column_stack((dx1, dx2, dx3))
        try:
            increment = np.linalg.solve(jacobian, target - position)
        except np.linalg.LinAlgError as exc:
            raise MassMatrixError("Degenerate Quad thickness volume while locating its centre.") from exc
        candidate = natural + increment
        error = float(np.abs(candidate - natural).sum())
        natural = candidate
        if error <= 1.0e-13:
            return natural
        if error >= previous_error:
            break
        previous_error = error
    return natural


def _b_matrices(quad: Any, natural: np.ndarray, positions: np.ndarray, node0: np.ndarray) -> np.ndarray:
    """Evaluate the C# local kinematic ``B`` matrix at one or many points."""
    natural = np.asarray(natural, dtype=float).reshape(-1, 3)
    positions = np.asarray(positions, dtype=float).reshape(-1, 3)
    result = np.zeros((natural.shape[0], 3, 4), dtype=float)
    offset = positions - node0
    result[:, 0, 1] = offset[:, 2]
    result[:, 1, 0] = -offset[:, 2]
    result[:, 2, 0] = offset[:, 1]
    result[:, 0, 2] = -offset[:, 1]
    result[:, 1, 2] = offset[:, 0]
    result[:, 2, 1] = -offset[:, 0]

    a = natural[:, 0]
    b = natural[:, 1]
    m2 = (1.0 - a) * (1.0 - b) / 4.0
    m3 = (1.0 + a) * (1.0 - b) / 4.0
    length4 = float(quad.length[3])
    sin4 = float(quad.sin[3])
    sin2 = float(quad.sin[1])
    sin3 = float(quad.sin[2])
    if abs(sin3) <= 1.0e-30:
        raise MassMatrixError(f"Quad {quad.key} has Sin3=0 and cannot form its mass matrix.")
    cos2 = float(quad.cos[1])
    sin1 = float(quad.sin[0])
    cos1 = float(quad.cos[0])
    first = (-length4 * sin4 * sin2 / sin3) * m2 + (-length4 * sin1) * m3
    second = (-length4 * sin4 * cos2 / sin3) * m2 + (length4 * cos1) * m3
    e1 = np.asarray(quad.reference_e1, dtype=np.float32).astype(float)
    e2 = np.asarray(quad.reference_e2, dtype=np.float32).astype(float)
    result[:, :, 3] = first[:, None] * e1 + second[:, None] * e2
    return result


def compute_quad_local_mass(
    quad: Any,
    model: Any,
    *,
    gravity: float = GRAVITY_ACCELERATION,
) -> np.ndarray:
    """Return the active C# implementation's 7x7 Quad mass matrix."""
    if gravity <= 0.0 or not isfinite(gravity):
        raise ValueError("gravity must be a positive finite value.")
    try:
        nodes = [model.collections.nodes[int(key)].point for key in quad.node_keys]
    except KeyError as exc:
        raise MassMatrixError(f"Quad {quad.key} references missing Node {exc.args[0]}.") from exc
    try:
        material = model.collections.materials[int(quad.material_key)]
    except KeyError as exc:
        raise MassMatrixError(
            f"Quad {quad.key} references missing masonry material {quad.material_key}."
        ) from exc

    # Native Node.Point, Quad.Normal/Thickness and reference axes are Single
    # storage, promoted before the Point3d/Double mass integration arithmetic.
    mid_surface = np.asarray([(point.x, point.y, point.z) for point in nodes], dtype=np.float32).astype(float)
    normals = np.asarray([(point.x, point.y, point.z) for point in quad.normal], dtype=np.float32).astype(float)
    thickness = np.asarray(quad.thickness, dtype=np.float32).astype(float)
    if mid_surface.shape != (4, 3) or normals.shape != (4, 3) or thickness.shape != (4,):
        raise MassMatrixError(f"Quad {quad.key} has incomplete geometry for mass integration.")

    volume_nodes = np.vstack(
        (
            mid_surface + normals * thickness[:, None] / 2.0,
            mid_surface - normals * thickness[:, None] / 2.0,
        )
    )
    centre = np.asarray((quad.g.x, quad.g.y, quad.g.z), dtype=np.float32).astype(float)
    centre_natural = _invert_hexahedron(centre, volume_nodes)

    positions = _N8 @ volume_nodes
    dx1 = _D1 @ volume_nodes
    dx2 = _D2 @ volume_nodes
    dx3 = _D3 @ volume_nodes
    determinants = np.einsum("ij,ij->i", np.cross(dx1, dx2), dx3)
    if np.any(~np.isfinite(determinants)) or np.any(determinants <= 0.0):
        minimum = float(np.nanmin(determinants))
        raise MassMatrixError(
            f"Quad {quad.key} has a non-positive 3D Jacobian during mass integration "
            f"(minimum {minimum:.6g})."
        )

    b_gauss = _b_matrices(quad, _GAUSS_POINTS, positions, mid_surface[0])
    centre_position, _, _, _ = _map_hexahedron(volume_nodes, centre_natural)
    b_centre = _b_matrices(
        quad,
        centre_natural.reshape(1, 3),
        centre_position.reshape(1, 3),
        mid_surface[0],
    )[0]

    # Vtilde * N from the C# routine simplifies to [I, B(q)-B(centre)].
    velocity = np.zeros((_GAUSS_POINTS.shape[0], 3, 7), dtype=float)
    velocity[:, :, :3] = np.eye(3)
    velocity[:, :, 3:] = b_gauss - b_centre

    density = float(np.float32(material.w)) / gravity
    local = np.einsum(
        "pki,pkj,p->ij",
        velocity,
        velocity,
        determinants * _GAUSS_WEIGHTS,
    ) * density

    # The C# implementation treats existing local applied loads as point masses.
    applied = np.asarray(getattr(quad.status, "p", np.zeros(7)), dtype=float)
    if applied.shape[0] < 7:
        raise MassMatrixError(f"Quad {quad.key} has fewer than seven local load entries.")
    local[np.arange(7), np.arange(7)] += np.abs(applied[:7] / gravity)

    cutoff = float(np.max(local)) * 1.0e-15
    local[np.abs(local) < cutoff] = 0.0
    return local


def assemble_mass_matrix(
    model: Any,
    *,
    on_progress: Callable[[float], None] | None = None,
) -> MassMatrixAssembly:
    """Assemble the global C#-compatible mass matrix for supported elements.

    The Python domain currently implements Quad/Interface models. Interfaces
    carry no independent mass in the C# path. Vertex, Solid, Frame and Fiber
    masses are rejected if such future collections are populated rather than
    being silently discarded.
    """
    collections = getattr(model, "collections", None)
    if collections is None:
        raise MassMatrixError("Model.collections is not initialized.")
    n = int(getattr(model, "gdl", 0))
    if n <= 0:
        raise MassMatrixError("The model has no active global DOFs.")

    for collection_name in ("vertices", "solids", "frames", "fibers"):
        unsupported = getattr(collections, collection_name, None)
        if unsupported:
            raise NotImplementedError(
                f"Modal mass assembly for {collection_name} is not implemented in the Python port."
            )

    rows: list[int] = []
    cols: list[int] = []
    values: list[float] = []
    quads = tuple(collections.quads.values())
    for index, quad in enumerate(quads, start=1):
        local = compute_quad_local_mass(quad, model)
        if len(quad.aff) < 7:
            raise MassMatrixError(f"Quad {quad.key} has only {len(quad.aff)} afference rows.")
        for local_i in range(7):
            for local_j in range(7):
                value = float(local[local_i, local_j])
                if value == 0.0:
                    continue
                # Deliberately do not multiply by afference alpha: C# AssembleM
                # scatters the local value unchanged to every afference pair.
                for aff_i in quad.aff[local_i]:
                    global_i = int(aff_i.gdl) - 1
                    if not 0 <= global_i < n:
                        raise MassMatrixError(
                            f"Quad {quad.key} has out-of-range mass DOF {aff_i.gdl}."
                        )
                    for aff_j in quad.aff[local_j]:
                        global_j = int(aff_j.gdl) - 1
                        if not 0 <= global_j < n:
                            raise MassMatrixError(
                                f"Quad {quad.key} has out-of-range mass DOF {aff_j.gdl}."
                            )
                        rows.append(global_i)
                        cols.append(global_j)
                        values.append(value)
        if on_progress is not None and quads:
            on_progress(index / len(quads))

    matrix = sp.coo_matrix((values, (rows, cols)), shape=(n, n), dtype=float).tocsc()
    matrix.sum_duplicates()
    if matrix.nnz == 0:
        raise MassMatrixError("The assembled mass matrix is empty.")
    if np.any(~np.isfinite(matrix.data)):
        raise MassMatrixError("The assembled mass matrix contains NaN or infinite values.")

    requested = str(getattr(model, "mass_matrix_type", "Consistent"))
    return MassMatrixAssembly(
        matrix=matrix,
        requested_type=requested,
        effective_type="Consistent (C# Quad integration; HRX switch ignored)",
        quad_count=len(quads),
    )


def build_translational_pseudovectors(model: Any, mass: sp.spmatrix) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build C# ``ex/ey/ez``, ``M*e`` and total directional masses."""
    collections = getattr(model, "collections", None)
    if collections is None:
        raise MassMatrixError("Model.collections is not initialized.")
    n = int(model.gdl)
    directions = np.zeros((n, 3), dtype=float)
    for direction in range(3):
        for quad in collections.quads.values():
            if direction < len(quad.aff) and quad.aff[direction]:
                entry = quad.aff[direction][0]
                dof = int(entry.gdl) - 1
                if not 0 <= dof < n:
                    raise MassMatrixError(
                        f"Quad {quad.key} has out-of-range pseudovector DOF {entry.gdl}."
                    )
                # C# assignment semantics: later elements overwrite, not add.
                directions[dof, direction] = float(entry.alfa)
        # NodeC pseudovectors can be added when preprocessing parses their
        # afferences; current supported HRX Quad topology already contributes
        # every active translational DOF.
    mass_times_direction = np.asarray(mass @ directions, dtype=float)
    totals = np.einsum("ij,ij->j", directions, mass_times_direction)
    if np.any(totals <= 0.0) or np.any(~np.isfinite(totals)):
        raise MassMatrixError(
            "At least one translational pseudovector has zero or invalid total mass."
        )
    return directions, mass_times_direction, totals
