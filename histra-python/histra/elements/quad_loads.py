"""Quad static/line/self-weight load integration (C# ``Quad`` load paths).

Owns the three load-integration entry points of the masonry Quad: the compiled
area-load path with its scalar fallback, the line-load integration over the
Quad edges, and the self-weight vector assembly. The methods live on a mixin
so ``Quad`` remains the single public dataclass; every body is verbatim from
the original class.
"""
from __future__ import annotations

from math import sqrt

import numpy as np
from typing import List, Tuple

from histra.elements.quad_static_load import compute_static_load_area
from histra.types.point import Point


class QuadLoadsMixin:
    """Static, line and self-weight load integration for the Quad."""

    __slots__ = ()

    def compute_static_load_internal(
        self,
        node_coords: List[Point],
        nodal_forces: List[Tuple[float, float, float]],
    ) -> List[float]:
        """Integrate an area load using the compiled C#-parity kernel.

        The kernel deliberately retains every Single-precision boundary and
        left-associative sum used by ``Quad.ComputeStaticLoadInternal``.  The
        public method only validates and packs Python objects into contiguous
        arrays; no constitutive or load-control behaviour is changed.
        """
        if len(node_coords) != 4:
            raise ValueError(
                "Quad area-load integration requires exactly four node coordinates; "
                f"received {len(node_coords)}"
            )
        node_array = np.empty((4, 3), dtype=np.float32)
        for index, point in enumerate(node_coords):
            node_array[index, 0] = np.float32(point.x)
            node_array[index, 1] = np.float32(point.y)
            node_array[index, 2] = np.float32(point.z)

        force_array = np.asarray(nodal_forces, dtype=np.float32)
        if force_array.shape != (4, 3):
            raise ValueError(
                "Quad area-load integration requires four three-component nodal "
                f"forces; received shape {force_array.shape}"
            )

        result = compute_static_load_area(
            node_array,
            force_array,
            np.asarray((self.g.x, self.g.y, self.g.z), dtype=np.float32),
            np.asarray(self.reference_e1, dtype=np.float32),
            np.asarray(self.reference_e2, dtype=np.float32),
            np.asarray(self.length, dtype=np.float64),
            np.asarray(self.sin, dtype=np.float64),
            np.asarray(self.cos, dtype=np.float64),
        )
        return result.tolist()

    def _compute_static_load_internal_scalar(
        self,
        node_coords: List[Point],
        nodal_forces: List[Tuple[float, float, float]],
    ) -> List[float]:
        """Port C# ``Quad.ComputeStaticLoadInternal`` for area loads.

        The original implementation stores geometry, shape functions, force
        interpolation and Jacobians in ``float``/XNA ``Vector3`` values, then
        adds each Gauss-point contribution to a ``double[7]`` result.  Keeping
        those single-precision operation boundaries is necessary for numerical
        path compatibility with its work-based nonlinear convergence test.
        """
        f32 = np.float32

        out = np.zeros(7, dtype=np.float64)
        gp = f32(f32(np.sqrt(3.0)) / f32(3.0))
        gauss = (gp, f32(-gp))

        g = np.asarray((self.g.x, self.g.y, self.g.z), dtype=np.float32)
        e1 = np.asarray(self.reference_e1, dtype=np.float32)
        e2 = np.asarray(self.reference_e2, dtype=np.float32)
        transform = np.zeros((4, 3, 7), dtype=np.float32)

        for i, node in enumerate(node_coords):
            xyz = np.asarray((node.x, node.y, node.z), dtype=np.float32)
            dx, dy, dz = xyz - g
            transform[i, 0, 0] = f32(1.0)
            transform[i, 1, 1] = f32(1.0)
            transform[i, 2, 2] = f32(1.0)
            transform[i, 0, 4] = dz
            transform[i, 0, 5] = f32(-dy)
            transform[i, 1, 3] = f32(-dz)
            transform[i, 1, 5] = dx
            transform[i, 2, 3] = dy
            transform[i, 2, 4] = f32(-dx)

        # C# evaluates these expressions in double precision and explicitly
        # converts the completed warping coefficient to Single.
        for component in range(3):
            transform[2, component, 6] = f32(
                -self.length[3]
                * self.sin[3]
                / self.sin[2]
                * (
                    self.sin[1] * float(e1[component])
                    + self.cos[1] * float(e2[component])
                )
            )
            transform[3, component, 6] = f32(
                -self.length[3]
                * (
                    self.sin[0] * float(e1[component])
                    - self.cos[0] * float(e2[component])
                )
            )

        length0 = f32(self.length[0])
        length1 = f32(self.length[1])
        length3 = f32(self.length[3])
        cos0 = f32(self.cos[0])
        cos1 = f32(self.cos[1])
        sin0 = f32(self.sin[0])
        sin1 = f32(self.sin[1])
        local = np.zeros((4, 2), dtype=np.float32)
        local[0] = (f32(f32(-length0) / f32(2.0)), f32(0.0))
        local[1] = (f32(length0 / f32(2.0)), f32(0.0))
        local[2] = (
            f32(f32(length0 / f32(2.0)) - f32(length1 * cos1)),
            f32(length1 * sin1),
        )
        local[3] = (
            f32(f32(-length0) / f32(2.0) + f32(length3 * cos0)),
            f32(length3 * sin0),
        )
        forces = np.asarray(nodal_forces, dtype=np.float32)

        def sum4(values: List[np.float32]) -> np.float32:
            # C#'s source expression is left associative and every operand is
            # Single; spell that out rather than allowing a NumPy reduction.
            return f32(f32(f32(values[0] + values[1]) + values[2]) + values[3])

        one = f32(1.0)
        four = f32(4.0)
        for xi in gauss:
            for eta in gauss:
                shape = np.asarray(
                    (
                        f32(f32(one - xi) * f32(one - eta) / four),
                        f32(f32(one + xi) * f32(one - eta) / four),
                        f32(f32(one + xi) * f32(one + eta) / four),
                        f32(f32(one - xi) * f32(one + eta) / four),
                    ),
                    dtype=np.float32,
                )
                dxi = np.asarray(
                    (
                        f32(-f32(one - eta) / four),
                        f32(f32(one - eta) / four),
                        f32(f32(one + eta) / four),
                        f32(-f32(one + eta) / four),
                    ),
                    dtype=np.float32,
                )
                deta = np.asarray(
                    (
                        f32(-f32(one - xi) / four),
                        f32(-f32(one + xi) / four),
                        f32(f32(one + xi) / four),
                        f32(f32(one - xi) / four),
                    ),
                    dtype=np.float32,
                )

                j11 = sum4([f32(local[i, 0] * dxi[i]) for i in range(4)])
                j12 = sum4([f32(local[i, 0] * deta[i]) for i in range(4)])
                j21 = sum4([f32(local[i, 1] * dxi[i]) for i in range(4)])
                j22 = sum4([f32(local[i, 1] * deta[i]) for i in range(4)])
                det_j = f32(f32(j11 * j22) - f32(j12 * j21))

                force_gp = np.zeros(3, dtype=np.float32)
                for component in range(3):
                    force_gp[component] = sum4(
                        [f32(shape[i] * forces[i, component]) for i in range(4)]
                    )

                transform_gp = np.zeros((3, 7), dtype=np.float32)
                for row in range(3):
                    for column in range(7):
                        transform_gp[row, column] = sum4(
                            [
                                f32(transform[i, row, column] * shape[i])
                                for i in range(4)
                            ]
                        )

                for column in range(7):
                    projection = f32(
                        f32(
                            f32(force_gp[0] * transform_gp[0, column])
                            + f32(force_gp[1] * transform_gp[1, column])
                        )
                        + f32(force_gp[2] * transform_gp[2, column])
                    )
                    # The product is Single; assignment into double[] performs
                    # the only widening conversion in this accumulation.
                    out[column] += float(f32(projection * det_j))

        return out.tolist()

    def compute_line_load_internal(
        self,
        node_coords: List[Point],
        points: Tuple[Tuple[float, float, float], Tuple[float, float, float]],
        endpoint_forces: Tuple[Tuple[float, float, float], Tuple[float, float, float]],
        *, node_tolerance: float = 1.0,
    ) -> List[float]:
        """Port the C# ``Quad.ComputeStaticLoadInternal`` line-load branch.

        The source uses XNA ``Vector`` values and ``float`` arrays throughout.
        It also contains a compatibility-sensitive interpolation typo for the
        intrinsic line coordinates: both endpoint terms use ``(1-gp)/2``.
        This method deliberately preserves that behavior because it is part of
        the committed C# LiveLoad reference path.
        """
        from histra.preprocessing.intrinsic_coordinates import native_intrinsic_2d
        from histra.preprocessing.quad_faces import _dot, _plane_normal, _plane_w, _ray_project
        from histra.preprocessing.quad_geometry import _norm, _unit
        f32 = np.float32
        out = np.zeros(7, dtype=np.float64)
        gp0 = f32(f32(np.sqrt(3.0)) / f32(3.0))
        gauss = (gp0, f32(-gp0))

        g = np.asarray((self.g.x, self.g.y, self.g.z), dtype=np.float32)
        e1 = np.asarray(self.reference_e1, dtype=np.float32)
        e2 = np.asarray(self.reference_e2, dtype=np.float32)
        e3 = np.asarray(self.reference_e3, dtype=np.float32)
        origin = np.asarray(
            (self.reference_origin.x, self.reference_origin.y, self.reference_origin.z),
            dtype=np.float32,
        )

        transform = np.zeros((4, 3, 7), dtype=np.float32)
        for i, node in enumerate(node_coords):
            xyz = np.asarray((node.x, node.y, node.z), dtype=np.float32)
            dx, dy, dz = xyz - g
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
                -self.length[3]
                * self.sin[3]
                / self.sin[2]
                * (
                    self.sin[1] * float(e1[component])
                    + self.cos[1] * float(e2[component])
                )
            )
            transform[3, component, 6] = f32(
                -self.length[3]
                * (
                    self.sin[0] * float(e1[component])
                    - self.cos[0] * float(e2[component])
                )
            )

        l0, l1, l3 = f32(self.length[0]), f32(self.length[1]), f32(self.length[3])
        local_nodes = np.asarray(
            (
                (f32(-l0 / f32(2.0)), f32(0.0)),
                (f32(l0 / f32(2.0)), f32(0.0)),
                (
                    f32(l0 / f32(2.0) - f32(l1 * f32(self.cos[1]))),
                    f32(l1 * f32(self.sin[1])),
                ),
                (
                    f32(-l0 / f32(2.0) + f32(l3 * f32(self.cos[0]))),
                    f32(l3 * f32(self.sin[0])),
                ),
            ),
            dtype=np.float32,
        )

        local_points3 = np.zeros((2, 3), dtype=np.float32)
        local_points2 = np.zeros((2, 2), dtype=np.float32)
        for i, point in enumerate(points):
            vector = np.asarray(point, dtype=np.float32) - origin
            local_points3[i] = (
                _dot(vector, e1),
                _dot(vector, e2),
                _dot(vector, e3),
            )
            local_points2[i] = (
                f32(local_points3[i, 0] - f32(self.length[0] / 2.0)),
                local_points3[i, 1],
            )

        # The float-array overload uses polygon-strip bisection, retaining
        # the original 0.001 stopping tolerance and corner shortcut.
        uv = []
        for point in local_points2:
            corner = None
            for j in range(4):
                if abs(float(f32(point[0]-local_nodes[j,0]))) < node_tolerance and abs(float(f32(point[1]-local_nodes[j,1]))) < node_tolerance:
                    corner = (f32(-1 if j in (0,3) else 1), f32(-1 if j in (0,1) else 1))
            uv.append(corner if corner is not None else native_intrinsic_2d(local_nodes, point, f32(node_tolerance)))
        forces = np.asarray(endpoint_forces, dtype=np.float32)
        line_length = _norm(np.asarray(points[0], np.float32) - np.asarray(points[1], np.float32))
        one = f32(1.0)
        two = f32(2.0)
        four = f32(4.0)

        for gauss_point in gauss:
            force = np.asarray(
                [f32(f32(forces[0,j]*f32((one-gauss_point)/two)) + f32(forces[1,j]*f32((one+gauss_point)/two))) for j in range(3)],
                dtype=np.float32,
            )
            # Preserve C# source typo (both endpoint terms use 1-gp).
            u = f32(uv[0][0]*(one-gauss_point)/two + uv[1][0]*(one-gauss_point)/two)
            v = f32(uv[0][1]*(one-gauss_point)/two + uv[1][1]*(one-gauss_point)/two)
            shape = np.asarray(
                (f32((one-u)*(one-v)/four), f32((one+u)*(one-v)/four),
                 f32((one+u)*(one+v)/four), f32((one-u)*(one+v)/four)),
                dtype=np.float32,
            )
            transform_gp = np.zeros((3,7), dtype=np.float32)
            for row in range(3):
                for col in range(7):
                    acc = f32(0.0)
                    for i in range(4):
                        acc = f32(acc + f32(transform[i,row,col]*shape[i]))
                    transform_gp[row,col] = acc
            for col in range(7):
                projection = f32(
                    f32(f32(force[0]*transform_gp[0,col]) + f32(force[1]*transform_gp[1,col]))
                    + f32(force[2]*transform_gp[2,col])
                )
                out[col] += float(f32(projection * line_length / two))

        # C# adds the moment of the line resultant about its projection on the
        # quad plane.  This term is zero for the supplied symmetric transverse
        # line, but retain the general calculation.
        f0, f1 = forces[0], forces[1]
        l0f, l1f = _norm(f0), _norm(f1)
        denom = f32(l1f + l0f)
        if line_length > 0 and abs(float(denom)) > 1e-30:
            distance = f32(line_length / f32(3.0) * f32(f32(2.0)*l1f + l0f) / denom)
            direction = np.asarray(points[1], np.float32) - np.asarray(points[0], np.float32)
            direction = _unit(direction)
            centroid = np.asarray(points[0], np.float32) + f32(distance) * direction
            vertices = np.asarray([(n.x,n.y,n.z) for n in node_coords], np.float32)
            normal = _plane_normal(vertices[0], vertices[1], vertices[2])
            projected = _ray_project(centroid, normal, _plane_w(vertices[0],normal))
            resultant = f32(0.5) * (f0+f1) * _norm(local_points3[0]-local_points3[1])
            moment = np.cross(centroid-projected, resultant).astype(np.float32)
            out[3] += float(moment[0]); out[4] += float(moment[1]); out[5] += float(moment[2])
        return out.tolist()

    def compute_self_weight_load(self, dir_x: float, dir_y: float, dir_z: float, w: float) -> List[Tuple[float, float, float]]:
        """Port C# ``Thickness[i] * w * Vector3 dir`` in single precision."""
        f32 = np.float32
        direction = (f32(dir_x), f32(dir_y), f32(dir_z))
        weight = f32(w)
        forces: List[Tuple[float, float, float]] = []
        for thickness in self.thickness:
            scalar = f32(f32(thickness) * weight)
            forces.append(
                tuple(float(f32(scalar * component)) for component in direction)
            )
        return forces

    # ── Diagonal spring kinematic transformation ─────────────────────────────
