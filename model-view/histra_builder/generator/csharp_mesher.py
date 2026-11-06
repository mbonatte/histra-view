"""C#-parity bridge mesher for the straight wizard path.

This is the first verified slice of ``BridgeMesher.AddBridge1``:

* ``AddBridgeRow1`` / ``AddSemiArcoSx1`` / ``AddSemiArcoDx1``
* ``AddMesh4`` / ``AddMesh3`` convex-quad subdivision
* ``AddMeshArco1`` arch ring and springing pulvino
* ``AddSpallePile`` pier shaft generation for ``Hf = 0``

The native C# mesher always builds the elliptical arch.  The separate
``Span.true_circular_geometry`` option selects the viewer's circular extension.

It intentionally works with :class:`CSharpBridgeSpec` instead of the previous
generic ``BridgeSpec`` so every C# dimension has a real home.  Later tasks add
foundation/GLR generation, multi-layer elevations, inclination/slope/curvature
and the native HRX writer.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .csharp_arch import (
    ArchParams,
    arch_extrados_springing,
    arch_intrados_point,
    arch_offset_inward,
    get_points_in_arch_equi_spaced,
    half_arch_params,
    half_arch_params_circular,
)
from .geometry import Point3D, compute_quad_kinematics, signed_area_xz
from .mesher import GeneratedQuad, MonitoringPoint, PierMetadata
from .restraints import GeneratedNodeC, GeneratedRestraint
from .materials import DEFAULT_TEMPLATES
from .csharp_discretize import (
    discretize_bottom_foundation_pileb2,
    discretize_bottom_pileb2,
    discretize_top_pileb2,
)
from .csharp_model import (
    Abutment,
    BridgeDefinition,
    CSharpBridgeSpec,
    Elevations,
    GeneratedLineLoad,
    Pier,
    Span,
)


def _normalise(v) -> Point3D:
    vx, vy, vz = _xyz(v)
    n = math.sqrt(vx * vx + vy * vy + vz * vz)
    if n < 1.0e-15:
        return Point3D(1.0, 0.0, 0.0)
    return Point3D(vx / n, vy / n, vz / n)


def _xyz(value) -> Tuple[float, float, float]:
    if isinstance(value, Point3D):
        return (value.x, value.y, value.z)
    return (float(value[0]), float(value[1]), float(value[2]))


def _dist(a, b) -> float:
    ax, ay, az = _xyz(a)
    bx, by, bz = _xyz(b)
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


def _sub(a, b) -> Point3D:
    ax, ay, az = _xyz(a)
    bx, by, bz = _xyz(b)
    return Point3D(ax - bx, ay - by, az - bz)


def _add(a, b) -> Point3D:
    ax, ay, az = _xyz(a)
    bx, by, bz = _xyz(b)
    return Point3D(ax + bx, ay + by, az + bz)


def _dot(a, b) -> float:
    ax, ay, az = _xyz(a)
    bx, by, bz = _xyz(b)
    return ax * bx + ay * by + az * bz


def _lerp(a, b, t: float) -> Point3D:
    ax, ay, az = _xyz(a)
    bx, by, bz = _xyz(b)
    return Point3D(
        ax + (bx - ax) * t,
        ay + (by - ay) * t,
        az + (bz - az) * t,
    )


def _arrotonda(value: float) -> int:
    """C# ``Operations.Arrotonda``: round up unless the value is integral."""
    floor = math.floor(value)
    return int(floor + 1.0) if abs(value - floor) > 0.0 else int(floor)


@dataclass
class GeneratedGeometryLineRestraint:
    """C# ``GeometryLineRestraint`` (foundation line support)."""

    key: int
    name: str
    node_key1: int
    node_key2: int
    b: float
    h: float = 30.0
    material_key: int = 0
    load_condition_key: int = 0
    zg: float = 0.0
    parent_key: int = 1
    parent_type: str = "Bridge"
    parent_edge: int = 0
    alignment: str = "Center"
    dy: float = 0.0
    mechanical_type: str = "Foundation"
    k: Tuple[float, ...] = (-1.0, -1.0, -1.0, -1.0, -1.0, -1.0)
    behaviours: Tuple[str, ...] = ("Fixed",) * 6


@dataclass
class CSharpBridgeMesh:
    """Structural mesh produced by the C#-parity mesher."""

    spec: CSharpBridgeSpec
    nodes: Dict[int, Point3D]
    quads: Dict[int, GeneratedQuad]
    geometry_line_restraints: List[GeneratedGeometryLineRestraint]
    restraints: List[GeneratedRestraint]
    node_cs: List[GeneratedNodeC]
    monitoring_points: List[object]
    piers: List[PierMetadata]
    deck_z: float
    total_length: float
    line_loads: List[GeneratedLineLoad] = field(default_factory=list)
    control_model_point_key: Optional[int] = None


class CSharpMesher:
    """Port of the straight ``BridgeMesher.AddBridge1`` path."""

    def __init__(self, spec: CSharpBridgeSpec, *, legacy_backfill: bool = False,
                 previous_backfill: bool = False) -> None:
        self.spec = spec
        # Used only to recognize files generated before backfill clipping was fixed.
        self._legacy_backfill = legacy_backfill
        self._previous_backfill = previous_backfill
        self.nodes: Dict[int, Point3D] = {}
        self._node_index: Dict[Tuple[float, float, float], int] = {}
        self.quads: Dict[int, GeneratedQuad] = {}
        self._next_node_key = 1
        self._next_quad_key = 1
        self._deck_z = 0.0
        self._total_length = 0.0
        self._foundation_edges: List[Tuple[int, float, int, List[GeneratedQuad], int, int, float]] = []
        self._next_glr_key = 1
        self._next_restraint_key = 1
        self._next_node_c_key = 1
        self._node_c_map: Dict[int, int] = {}
        self._glrs: List[GeneratedGeometryLineRestraint] = []
        self._restraints: List[GeneratedRestraint] = []
        self._node_cs: List[GeneratedNodeC] = []
        self._piers: List[PierMetadata] = []
        self._monitoring_points: List[MonitoringPoint] = []
        self._line_loads: List[GeneratedLineLoad] = []
        self._control_model_point_key: Optional[int] = None
        # Optional (top Y, bottom Y, top Z, bottom Z, top width, bottom width).
        self._strip_transform = None
        self._quad_transforms = {}

    # -- geometric primitives -------------------------------------------------

    def _node(self, point) -> int:
        px, py, pz = _xyz(point)
        key = (round(px, 4), round(py, 4), round(pz, 4))
        existing = self._node_index.get(key)
        if existing is not None:
            return existing
        node_key = self._next_node_key
        self._next_node_key += 1
        self._node_index[key] = node_key
        self.nodes[node_key] = Point3D(key[0], key[1], key[2])
        return node_key

    def _quad(self, points: Sequence[Sequence[float]], material_key: int, thickness: float, group: str) -> GeneratedQuad:
        pts = [Point3D(*_xyz(p)) for p in points]
        # Preserve the C# node order: BridgeMesher relies on it for the
        # element reference system and sets the normal from the winding.
        kinematics = compute_quad_kinematics(
            pts,
            thickness=thickness,
            out_of_plane_normal=(0.0, 1.0, 0.0),
        )
        keys = tuple(self._node(_xyz(point)) for point in pts)
        key = self._next_quad_key
        self._next_quad_key += 1
        quad = GeneratedQuad(
            key=key,
            node_keys=(keys[0], keys[1], keys[2], keys[3]),
            material_key=material_key,
            thickness=thickness,
            kinematics=kinematics,
            group=group,
        )
        self.quads[key] = quad
        if self._strip_transform is not None:
            self._quad_transforms[key] = self._strip_transform
        return quad

    # -- C# WizardBridge geometry -------------------------------------------

    def _abscissa(self) -> List[float]:
        values: List[float] = []
        cursor = 0.0
        for element in self.spec.elements:
            if isinstance(element, Span):
                cursor += element.L
                values.append(cursor - element.L / 2.0)
            elif isinstance(element, Pier):
                cursor += element.b2
                values.append(cursor - element.b2 / 2.0)
            elif isinstance(element, Abutment):
                if element.kind == "Destra":
                    cursor += element.b2
                    values.append(cursor)
                else:
                    values.append(cursor)
                    cursor += element.b2
        return values

    def _element_origin(self, target: object) -> float:
        """Return the element centre using C# cumulative Abscissa layout."""
        cursor = 0.0
        for element in self.spec.elements:
            if isinstance(element, Span):
                centre = cursor + element.L / 2.0
                cursor += element.L
            else:
                centre = cursor + element.b2 / 2.0
                cursor += element.b2
            if element is target:
                return centre
        return cursor

    def _strip_centres(self) -> List[float]:
        # C# walks from +Width/2 and subtracts half-lane widths.
        cursor = self.spec.definition.width / 2.0
        centres: List[float] = []
        for corsia in self.spec.definition.corsias:
            cursor -= corsia.width / 2.0
            centres.append(cursor)
            cursor -= corsia.width / 2.0
        return centres

    # -- AddMesh4 / AddMesh3 -------------------------------------------------

    def _add_mesh4(
        self,
        points1: Sequence[Sequence[float]],
        points2: Sequence[Sequence[float]],
        material_key: int,
        thickness: float,
        is_right: bool,
        generate: bool = True,
        material_key2: Optional[int] = None,
        row_index_material: int = -1,
    ) -> Tuple[int, int]:
        value = _normalise(_sub(points2[1], points2[0]))
        denominator = _dot(value, _sub(points1[-1], points1[0]))
        if abs(denominator) < 1.0e-15:
            denominator = 1.0
        n = len(points1) - 1
        first_gap = _dist(points1[0], points2[0])
        last_gap = _dist(points1[-1], points2[-1])
        m = max(1, _arrotonda(max(first_gap, last_gap) / self.spec.definition.nl))

        if not generate:
            return n, m

        for i in range(n):
            a: List[Point3D] = [None, None, None, None]  # type: ignore[list-item]
            a[0] = Point3D(*_xyz(points1[i]))
            a[1] = Point3D(*_xyz(points1[i + 1]))
            a[2] = _lerp(
                points2[0],
                points2[1],
                _dot(value, _sub(points1[i + 1], points1[0])) / denominator,
            )
            a[3] = _lerp(
                points2[0],
                points2[1],
                _dot(value, _sub(points1[i], points1[0])) / denominator,
            )
            for j in range(m):
                if is_right:
                    points = [
                        _lerp(a[1], a[2], j / m),
                        _lerp(a[0], a[3], j / m),
                        _lerp(a[0], a[3], (j + 1) / m),
                        _lerp(a[1], a[2], (j + 1) / m),
                    ]
                else:
                    points = [
                        _lerp(a[0], a[3], j / m),
                        _lerp(a[1], a[2], j / m),
                        _lerp(a[1], a[2], (j + 1) / m),
                        _lerp(a[0], a[3], (j + 1) / m),
                    ]
                material = (material_key2 if material_key2 is not None and
                            j >= row_index_material else material_key)
                self._quad(points, material, thickness, "CSharp_Fill")
        return n, m

    def _add_mesh3(
        self,
        points: Sequence[Sequence[float]],
        n: int,
        m: int,
        material_key: int,
        thickness: float,
        is_right: bool,
        group: str = "CSharp_Fill",
        material_key2: Optional[int] = None,
        row_index_material: int = -1,
    ) -> List[GeneratedQuad]:
        created: List[GeneratedQuad] = []
        for i in range(n):
            if is_right:
                a = [
                    _lerp(points[0], points[3], i / n),
                    _lerp(points[1], points[2], i / n),
                    _lerp(points[1], points[2], (i + 1) / n),
                    _lerp(points[0], points[3], (i + 1) / n),
                ]
            else:
                a = [
                    _lerp(points[0], points[3], i / n),
                    _lerp(points[1], points[2], i / n),
                    _lerp(points[1], points[2], (i + 1) / n),
                    _lerp(points[0], points[3], (i + 1) / n),
                ]
            for j in range(m):
                created.append(
                    self._quad(
                        [
                            _lerp(a[0], a[1], j / m),
                            _lerp(a[0], a[1], (j + 1) / m),
                            _lerp(a[3], a[2], (j + 1) / m),
                            _lerp(a[3], a[2], j / m),
                        ],
                        (material_key2 if material_key2 is not None and
                         i >= row_index_material else material_key),
                        thickness,
                        group,
                    )
                )
        return created

    # -- AddSemiArcoSx1 / Dx1 ------------------------------------------------

    def _add_semi_arch(
        self,
        span: Span,
        params: ArchParams,
        x1: float,
        x2: float,
        y: float,
        is_right: bool,
        heights: int,
        strip_width: float,
        hmuro: float = 0.0,
        fill_material_override: int = 0,
    ) -> Tuple[List[Point3D], int]:
        z1 = self.spec.elevations.get_z(x1, 1, hmuro)
        z2 = self.spec.elevations.get_z(x2, 1, hmuro)

        springing = arch_extrados_springing(params, is_right)
        extrados = Point3D(springing[0], y, springing[2])
        edge_x = x2 if is_right else x1
        ext_edge = Point3D(edge_x, y, extrados.z)

        crown = Point3D(params.crown_point[0], y, params.crown_point[2])
        extrados_points = get_points_in_arch_equi_spaced(
            (extrados.x, extrados.y, extrados.z),
            (crown.x, crown.y, crown.z),
            params,
            self.spec.definition.nl,
        )
        extrados_points = [Point3D(p[0], y, p[2]) for p in extrados_points]

        if not self._legacy_backfill and any(point.z > self.spec.elevations.get_z(point.x, 1, hmuro) + 1e-6 for point in extrados_points):
            if (not self._previous_backfill and not params.circular and len(self.spec.elevations.elevations) == 1
                    and self.spec.elevations.get_z(edge_x, 1, hmuro) > extrados.z + 1e-6
                    and self.spec.elevations.get_z(edge_x, 2, hmuro) >= crown.z + 1e-6):
                return self._add_single_crossing_backfill(
                    params, extrados, crown, edge_x, heights, strip_width, hmuro,
                    fill_material_override, is_right)
            if any(self.spec.elevations.generates_layer(layer) for layer in range(1, heights + 1)):
                self._add_clipped_backfill(extrados_points, edge_x, heights, strip_width, hmuro, fill_material_override)
            if self._previous_backfill:
                return extrados_points, 1
            # AddMesh1's M is the transverse subdivision of the first
            # Colonne; the adjacent support reuses it. Intersect the native
            # ellipse with the first active elevation rather than guessing
            # from the discretized polyline.
            if not params.circular:
                for layer in range(1, heights + 1):
                    z_edge = self.spec.elevations.get_z(edge_x, layer, hmuro)
                    if z_edge <= extrados.z + 1e-6:
                        continue
                    z_crown = self.spec.elevations.get_z(crown.x, layer, hmuro)
                    if z_crown >= crown.z - 1e-6:
                        break
                    slope = (z_crown - z_edge) / (crown.x - edge_x)
                    cx, _, cz = params.center
                    offset = z_edge + slope * (cx - edge_x) - cz
                    a = 1 / params.rx**2 + slope**2 / params.rz**2
                    b = 2 * slope * offset / params.rz**2
                    c = offset**2 / params.rz**2 - 1
                    disc = b*b - 4*a*c
                    if disc < 0:
                        break
                    roots = [cx + (-b + sign * math.sqrt(disc)) / (2*a) for sign in (-1, 1)]
                    candidates = [x for x in roots if min(edge_x, crown.x)-1e-6 <= x <= max(edge_x, crown.x)+1e-6]
                    if not candidates:
                        break
                    intersection = min(candidates, key=lambda x: abs(x - extrados.x))
                    distance = max(abs(extrados.x - edge_x), abs(intersection - edge_x))
                    return extrados_points, max(1, _arrotonda(distance / self.spec.definition.nl))
            return extrados_points, 1

        fill_material, fill_material2, row_index = self.spec.elevations.get_material_key(1)
        if fill_material_override > 0:
            fill_material = fill_material_override
            fill_material2 = fill_material_override
        upper = [
            Point3D(extrados_points[0].x, y, self.spec.elevations.get_z(extrados_points[0].x, 1, hmuro)),
            Point3D(extrados_points[-1].x, y, self.spec.elevations.get_z(extrados_points[-1].x, 1, hmuro)),
        ]
        n4, m4 = self._add_mesh4(
            extrados_points,
            upper,
            fill_material,
            strip_width,
            is_right,
            self.spec.elevations.generates_layer(1),
            fill_material2,
            row_index,
        )

        side = [
            Point3D(edge_x, y, extrados.z),
            extrados,
            Point3D(extrados.x, y, self.spec.elevations.get_z(extrados.x, 1, hmuro)),
            Point3D(edge_x, y, self.spec.elevations.get_z(edge_x, 1, hmuro)),
        ]
        n_side = max(1, _arrotonda(min(_dist(side[0], side[1]), _dist(side[2], side[3])) / self.spec.definition.nl))
        if self.spec.elevations.generates_layer(1):
            self._add_mesh3(
                side,
                m4,
                n_side,
                fill_material,
                strip_width,
                is_right,
                material_key2=fill_material2,
                row_index_material=row_index,
            )

        # Stack the remaining elevation layers as structured quad bands over
        # the same extrados columns.  This is the C# ``else``/flat-layer path;
        # curved transition triangles are a separate golden-dependent branch.
        columns = sorted({x1, x2, *(point.x for point in extrados_points)})
        for layer in range(2, heights + 1):
            if not self.spec.elevations.generates_layer(layer):
                continue
            layer_material, layer_material2, row_index = self.spec.elevations.get_material_key(layer)
            if fill_material_override > 0:
                layer_material = fill_material_override
                layer_material2 = fill_material_override
            for left_x, right_x in zip(columns, columns[1:]):
                width = right_x - left_x
                if abs(width) <= 1.0e-9:
                    continue
                bottom_left = self.spec.elevations.get_z(left_x, layer - 1, hmuro)
                bottom_right = self.spec.elevations.get_z(right_x, layer - 1, hmuro)
                top_left = self.spec.elevations.get_z(left_x, layer, hmuro)
                top_right = self.spec.elevations.get_z(right_x, layer, hmuro)
                if (
                    top_left - bottom_left <= 1.0e-9
                    or top_right - bottom_right <= 1.0e-9
                ):
                    continue
                points = [
                    Point3D(left_x, y, bottom_left),
                    Point3D(right_x, y, bottom_right),
                    Point3D(right_x, y, top_right),
                    Point3D(left_x, y, top_left),
                ]
                # AddMesh4 records one column per arc segment. Only the
                # springing-side block uses its independently calculated N.
                side_min, side_max = sorted((edge_x, extrados_points[0].x))
                is_side = abs(left_x - side_min) < 1.0e-6 and abs(right_x - side_max) < 1.0e-6
                subdivisions = n_side if is_side else 1
                self._add_mesh3(
                    points,
                    1 if self._legacy_backfill else max(1, _arrotonda(max(top_left-bottom_left, top_right-bottom_right) / self.spec.definition.nl)),
                    subdivisions,
                    layer_material,
                    strip_width,
                    False,
                    "CSharp_Fill",
                    layer_material2,
                    row_index,
                )

        # C# sets span.DiscrLeft/Right from Colonne.First().N.  In the
        # non-curved AddMesh4 branch each colonna is created with N=1.
        return extrados_points, 1

    def _add_single_crossing_backfill(self, params, spring, crown, edge_x, heights,
                                      width, hmuro, override, is_right):
        """C# AddSemiArco1 case: first layer crosses, second clears the arch."""
        elevations = self.spec.elevations
        z1 = elevations.get_z(edge_x, 1, hmuro)
        ratio = (z1 - params.center[2]) / params.rz
        if not -1 < ratio < 1:
            raise ValueError('Invalid layer intersection with arch ellipse')
        direction = 1 if spring.x > params.center[0] else -1
        cross = Point3D(params.center[0] + direction * params.rx * math.sqrt(1 - ratio**2), spring.y, z1)
        def arc(a, b):
            return [Point3D(*p) for p in get_points_in_arch_equi_spaced(
                _xyz(a), _xyz(b), params, self.spec.definition.nl)]
        first_arc, second_arc = arc(spring, cross), arc(cross, crown)
        side_start, side_end = Point3D(edge_x, spring.y, spring.z), Point3D(edge_x, spring.y, z1)
        subdivisions = max(1, _arrotonda(max(_dist(spring, side_start), _dist(cross, side_end)) / self.spec.definition.nl))
        first, second, row_index = elevations.get_material_key(1)
        if override > 0:
            first = second = override
        if elevations.generates_layer(1):
            dz = cross.z - spring.z
            for index, (a, b) in enumerate(zip(first_arc, first_arc[1:])):
                side_a = _lerp(side_start, side_end, (a.z - spring.z) / dz)
                side_b = _lerp(side_start, side_end, (b.z - spring.z) / dz)
                points = [a, side_a, side_b, b] if is_right else [side_a, a, b, side_b]
                material = first if index < row_index else second
                self._add_mesh3(points, 1, subdivisions, material, width, is_right)
        first, second, row_index = elevations.get_material_key(2)
        if override > 0:
            first = second = override
        upper = [Point3D(cross.x, spring.y, elevations.get_z(cross.x, 2, hmuro)),
                 Point3D(crown.x, spring.y, elevations.get_z(crown.x, 2, hmuro))]
        _, rows = self._add_mesh4(second_arc, upper, first, width, is_right,
                                  elevations.generates_layer(2), second, row_index)
        if elevations.generates_layer(2):
            left, right = sorted((edge_x, cross.x))
            points = [Point3D(left, spring.y, z1), Point3D(right, spring.y, z1),
                      Point3D(right, spring.y, elevations.get_z(right, 2, hmuro)),
                      Point3D(left, spring.y, elevations.get_z(left, 2, hmuro))]
            self._add_mesh3(points, rows, subdivisions, first, width, is_right,
                            material_key2=second, row_index_material=row_index)
        columns = [(edge_x, cross.x, subdivisions)] + [(a.x, b.x, 1) for a, b in zip(second_arc, second_arc[1:])]
        for layer in range(3, heights + 1):
            if not elevations.generates_layer(layer):
                continue
            if elevations.get_z(edge_x, layer, hmuro) <= elevations.get_z(edge_x, layer-1, hmuro) + 1e-6:
                continue
            first, second, row_index = elevations.get_material_key(layer)
            if override > 0:
                first = second = override
            rows = max(1, _arrotonda((elevations.get_z(edge_x, layer, hmuro) -
                                      elevations.get_z(edge_x, layer-1, hmuro)) / self.spec.definition.nl))
            for a, b, count in columns:
                left, right = sorted((a, b))
                points = [Point3D(left, spring.y, elevations.get_z(left, layer-1, hmuro)),
                          Point3D(right, spring.y, elevations.get_z(right, layer-1, hmuro)),
                          Point3D(right, spring.y, elevations.get_z(right, layer, hmuro)),
                          Point3D(left, spring.y, elevations.get_z(left, layer, hmuro))]
                self._add_mesh3(points, rows, count, first, width, is_right,
                                material_key2=second, row_index_material=row_index)
        return first_arc + second_arc[1:], subdivisions

    def _add_clipped_backfill(self, extrados, edge_x, heights, strip_width, hmuro, material_override):
        """Mesh horizontal bands above the piecewise-linear arch extrados.

        This quad-only transition differs from the C# mesher's Vertex-based
        transitions. Extra quad edges are allowed to terminate on arch faces;
        contact preparation matches their geometric overlap.
        """
        elevations = self.spec.elevations
        if self.spec.definition.nl <= 0:
            raise ValueError('Mesh length must be positive')
        if len(elevations.elevations) != 1:
            raise NotImplementedError('Backfill crossing an arch with variable elevations is not yet supported')
        dx = [b.x-a.x for a, b in zip(extrados, extrados[1:])]
        if any(value > 1e-6 for value in dx) and any(value < -1e-6 for value in dx):
            raise NotImplementedError('Backfill around an overhanging arch is not yet supported')
        section = elevations.elevations[0]
        if min(section.H1, section.H2, section.H3) < 0:
            raise ValueError('Backfill layer heights must not be negative')
        profile = list(extrados)
        if abs(edge_x - extrados[0].x) > 1e-6:
            profile.append(Point3D(edge_x, extrados[0].y, extrados[0].z))
        profile.sort(key=lambda point: point.x)
        levels = [elevations.get_z(0, layer, hmuro) for layer in range(1, heights + 1)]
        for left, right in zip(profile, profile[1:]):
            if right.x - left.x < 1e-6:
                continue
            cuts = [0.0, 1.0]
            if abs(right.z - left.z) > 1e-9:
                for level in levels:
                    t = (level - left.z) / (right.z - left.z)
                    if 1e-7 < t < 1.0 - 1e-7:
                        cuts.append(t)
            cuts = sorted(set(cuts))
            for start, end in zip(cuts, cuts[1:]):
                a, b = _lerp(left, right, start), _lerp(left, right, end)
                self._add_clipped_column(a, b, levels, strip_width, material_override)

    def _add_clipped_column(self, left, right, levels, strip_width, material_override):
        lower = 0.0
        for layer, upper in enumerate(levels, start=1):
            if upper < lower - 1e-8:
                raise ValueError('Backfill layer heights must not be negative')
            bottom_left, bottom_right = max(left.z, lower), max(right.z, lower)
            gap_left, gap_right = max(0.0, upper - bottom_left), max(0.0, upper - bottom_right)
            if max(gap_left, gap_right) > 1e-5 and self.spec.elevations.generates_layer(layer):
                first, second, row_index = self.spec.elevations.get_material_key(layer)
                if material_override > 0:
                    first = second = material_override
                rows = max(1, _arrotonda(max(gap_left, gap_right) / self.spec.definition.nl))
                for row in range(rows):
                    lo, hi = row / rows, (row + 1) / rows
                    points = [
                        Point3D(left.x, left.y, bottom_left + gap_left*lo),
                        Point3D(right.x, right.y, bottom_right + gap_right*lo),
                        Point3D(right.x, right.y, bottom_right + gap_right*hi),
                        Point3D(left.x, left.y, bottom_left + gap_left*hi),
                    ]
                    material = second if row >= row_index else first
                    self._add_transition_quad(points, material, strip_width)
            lower = upper

    def _add_transition_quad(self, points, material, thickness):
        """Split a triangular transition into three non-degenerate quads."""
        def emit(quad):
            rounded = [(round(p.x, 4), round(p.y, 4), round(p.z, 4)) for p in quad]
            if len(set(rounded)) != 4:
                raise ValueError('Backfill transition is too small for the mesh coordinate precision')
            self._quad(quad, material, thickness, 'CSharp_Fill')
        vertices = []
        for point in points:
            if not vertices or _dist(point, vertices[-1]) > 1e-5:
                vertices.append(point)
        if len(vertices) > 1 and _dist(vertices[0], vertices[-1]) <= 1e-5:
            vertices.pop()
        if len(vertices) == 4:
            emit(vertices)
        elif len(vertices) == 3:
            centre = Point3D(sum(p.x for p in vertices)/3, vertices[0].y, sum(p.z for p in vertices)/3)
            mid = [_lerp(vertices[i], vertices[(i+1) % 3], .5) for i in range(3)]
            for i in range(3):
                emit([vertices[i], mid[i], centre, mid[(i-1) % 3]])
        elif len(vertices) > 0:
            raise ValueError('Backfill transition produces a degenerate element')

    # -- AddMeshArco1 --------------------------------------------------------

    def _add_arch_ring(
        self,
        span: Span,
        params: ArchParams,
        extrados_points: Sequence[Point3D],
        x1: float,
        x2: float,
        y: float,
        is_right: bool,
        strip_width: float,
        foundation_owner: Optional[int] = None,
    ) -> None:
        lintradosso = span.L + span.S1 + span.S2
        springing_angle = (
            params.theta0
            if params.circular
            else math.radians(span.Adx)
        )
        for index in range(len(extrados_points) - 1):
            ext0 = extrados_points[index]
            ext1 = extrados_points[index + 1]
            int0 = arch_intrados_point(params, (ext0.x, ext0.y, ext0.z))
            int1 = arch_intrados_point(params, (ext1.x, ext1.y, ext1.z))
            int0 = Point3D(int0[0], y, int0[2])
            int1 = Point3D(int1[0], y, int1[2])
            if index == 0:
                if is_right:
                    int0 = Point3D(params.center[0] + lintradosso / 2.0, y, 0.0)
                else:
                    int0 = Point3D(params.center[0] - lintradosso / 2.0, y, 0.0)

            if type(span.arch_layers) is not int or not 1 <= span.arch_layers <= 4:
                raise ValueError("Arch thickness divisions must be an integer from 1 to 4.")
            for layer in range(span.arch_layers):
                inner0 = int0 if layer == 0 else _lerp(int0, ext0, layer / span.arch_layers)
                inner1 = int1 if layer == 0 else _lerp(int1, ext1, layer / span.arch_layers)
                outer0 = ext0 if layer + 1 == span.arch_layers else _lerp(int0, ext0, (layer + 1) / span.arch_layers)
                outer1 = ext1 if layer + 1 == span.arch_layers else _lerp(int1, ext1, (layer + 1) / span.arch_layers)
                points = ([inner0, outer0, outer1, inner1] if is_right else
                          [outer0, inner0, inner1, outer1])
                self._quad(points, span.material_key, strip_width, "CSharp_Arch")

            if span.Treinf > 0.0:
                inner0 = arch_offset_inward(params, (int0.x, int0.y, int0.z), span.Treinf)
                inner1 = arch_offset_inward(params, (int1.x, int1.y, int1.z), span.Treinf)
                inner0 = Point3D(inner0[0], y, inner0[2])
                inner1 = Point3D(inner1[0], y, inner1[2])
                reinforcement = ([inner0, int0, int1, inner1] if is_right else
                                 [int0, inner0, inner1, int1])
                self._quad(reinforcement, span.material_reinforcement_key,
                           strip_width, "CSharp_ArchReinforcement")

            if index == 0 and springing_angle > 1.0e-4:
                # The native pulvino is constructed from the last arch quad,
                # which is the reinforcement quad when one is present.
                if span.Treinf > 0.0:
                    ext0, int0 = int0, inner0
                if is_right:
                    pulvino = [
                        Point3D(int0.x, y, int0.z),
                        Point3D(x2, y, int0.z),
                        Point3D(x2, y, ext0.z),
                        Point3D(ext0.x, y, ext0.z),
                    ]
                else:
                    pulvino = [
                        Point3D(x1, y, int0.z),
                        Point3D(int0.x, y, int0.z),
                        Point3D(ext0.x, y, ext0.z),
                        Point3D(x1, y, ext0.z),
                    ]
                rows = _arrotonda(abs(pulvino[3].z - pulvino[0].z) / self.spec.definition.nl)
                pulvinos = self._add_mesh3(
                    pulvino,
                    rows,
                    1,
                    span.material_pulvino_key,
                    strip_width,
                    False,
                    "CSharp_Pulvino",
                )
                if foundation_owner is not None and pulvinos:
                    owner = self.spec.elements[foundation_owner]
                    if (
                        getattr(owner, "H", 0.0) <= 0.0
                        and getattr(owner, "Hf", 0.0) <= 0.0
                    ):
                        left_key = self._node((pulvino[0].x, y, pulvino[0].z))
                        right_key = self._node((pulvino[1].x, y, pulvino[1].z))
                        self._record_foundation_edge(
                            foundation_owner,
                            y,
                            0,
                            pulvinos[0],
                            left_key,
                            right_key,
                            strip_width,
                        )

    # -- AddBridgeRow1 -------------------------------------------------------

    def _add_bridge_row(
        self,
        abscissa: Sequence[float],
        spans: Sequence[Span],
        y: float,
        corsia_width: float,
        heights: int,
        hmuro: float = 0.0,
        fill_material_override: int = 0,
    ) -> None:
        span_index = 0
        for index in range(len(abscissa) - 1):
            span = spans[span_index]
            if (index + 1) % 2 == 0:
                span_index += 1
            x1 = abscissa[index]
            x2 = abscissa[index + 1]
            is_right = bool(index % 2)
            vector_x = x1 if is_right else x2
            if span.true_circular_geometry:
                params = half_arch_params_circular(
                    vector_x,
                    span.f,
                    span.L,
                    span.Tb,
                    span.Tt,
                    span.S1,
                    span.S2,
                    span.Dz,
                )
            else:
                params = half_arch_params(
                    vector_x,
                    span.f,
                    span.L,
                    span.Tb,
                    span.Tt,
                    span.Adx,
                    span.S1,
                    span.S2,
                    span.Dz,
                )
            params = replace(
                params,
                center=(params.center[0], y, params.center[2]),
                crown_point=(params.crown_point[0], y, params.crown_point[2]),
            )
            extrados_points, columns = self._add_semi_arch(
                span, params, x1, x2, y, is_right, heights, corsia_width, hmuro,
                fill_material_override,
            )
            foundation_owner: Optional[int] = None
            if index == 0:
                foundation_owner = 0
            elif index == len(abscissa) - 2:
                foundation_owner = len(self.spec.elements) - 1
            self._add_arch_ring(
                span,
                params,
                extrados_points,
                x1,
                x2,
                y,
                is_right,
                corsia_width,
                foundation_owner,
            )
            if is_right:
                span.discr_right = max(1, columns)
            else:
                span.discr_left = max(1, columns)

    # -- AddSpallePile -------------------------------------------------------

    def _add_spalle_pile(self, centres: Sequence[float]) -> None:
        """Port of ``generatePilaSpalla`` + ``generateMasonryFoundation``."""
        for owner_index, element in enumerate(self.spec.elements):
            if not isinstance(element, (Abutment, Pier)):
                continue
            centre = self._element_origin(element)
            for y, thickness, transform in self._support_rows(element, centres):
                self._strip_transform = transform
                top = [centre + value for value in discretize_top_pileb2(self.spec.elements, owner_index)]
                bottom = [centre + value for value in discretize_bottom_pileb2(self.spec.elements, owner_index)]
                columns = len(top) - 1
                if element.H > 0.0 and columns > 0:
                    rows = max(0, _arrotonda(element.H / self.spec.definition.nl))
                    for column in range(columns):
                        points = [
                            Point3D(bottom[column], y, -element.H),
                            Point3D(bottom[column + 1], y, -element.H),
                            Point3D(top[column + 1], y, 0.0),
                            Point3D(top[column], y, 0.0),
                        ]
                        span_width = top[column + 1] - top[column]
                        cross = max(1, _arrotonda(abs(span_width) / self.spec.definition.nl))
                        created = self._add_mesh3(
                            points,
                            rows,
                            cross,
                            element.material_key,
                            thickness,
                            False,
                            "CSharp_Pier",
                        )
                        if element.Hf <= 0.0 and created:
                            self._record_foundation_edge(
                                owner_index,
                                y,
                                column,
                                created[:cross],
                                self._node(points[0]),
                                self._node(points[1]),
                                thickness,
                            )

                    # generatePilaSpalla adds reinforcement blocks alongside
                    # the shaft independently of its main discretization.
                    for is_left, enabled, top_extension, bottom_extension, material in (
                        (True, element.is_reinf_left, element.TreinfTopLeft,
                         element.TreinfBotLeft, element.material_reinforcement_left_key),
                        (False, element.is_reinf_right, element.TreinfTopRight,
                         element.TreinfBotRight, element.material_reinforcement_right_key),
                    ):
                        if not enabled:
                            continue
                        if top_extension == 0.0 and bottom_extension == 0.0:
                            continue
                        if top_extension <= 0.0 or bottom_extension <= 0.0:
                            raise NotImplementedError(
                                "A triangular reinforcement needs C# Vertex meshing"
                            )
                        if is_left:
                            bottom_inner = centre - element.b2 / 2.0 - element.b1
                            top_inner = centre - element.b2 / 2.0
                            xs = (bottom_inner - bottom_extension, bottom_inner,
                                  top_inner, top_inner - top_extension)
                        else:
                            bottom_inner = centre + element.b2 / 2.0 + element.b3
                            top_inner = centre + element.b2 / 2.0
                            xs = (bottom_inner, bottom_inner + bottom_extension,
                                  top_inner + top_extension, top_inner)
                        points = [Point3D(xs[0], y, -element.H),
                                  Point3D(xs[1], y, -element.H),
                                  Point3D(xs[2], y, 0.0),
                                  Point3D(xs[3], y, 0.0)]
                        created = self._add_mesh3(
                            points, rows, 1, material, thickness, False,
                            "CSharp_Reinforcement",
                        )
                        if element.Hf <= 0.0 and bottom_extension > 0.0 and created:
                            self._record_foundation_edge(
                                owner_index, y, -1 if is_left else columns,
                                created[:1], self._node(points[0]),
                                self._node(points[1]), thickness,
                            )

                if element.Hf > 0.0:
                    foundation_bottom = [
                        centre + value
                        for value in discretize_bottom_foundation_pileb2(
                            self.spec.elements, owner_index
                        )
                    ]
                    foundation_columns = len(foundation_bottom) - 1
                    rows = max(1, _arrotonda(element.Hf / self.spec.definition.nl))
                    for column in range(foundation_columns):
                        points = [
                            Point3D(foundation_bottom[column], y, -element.H - element.Hf),
                            Point3D(foundation_bottom[column + 1], y, -element.H - element.Hf),
                            Point3D(foundation_bottom[column + 1], y, -element.H),
                            Point3D(foundation_bottom[column], y, -element.H),
                        ]
                        cross = max(
                            1,
                            _arrotonda(
                                abs(foundation_bottom[column + 1] - foundation_bottom[column])
                                / self.spec.definition.nl
                            ),
                        )
                        created = self._add_mesh3(
                            points,
                            rows,
                            cross,
                            element.material_foundation_key,
                            thickness,
                            False,
                            "CSharp_Foundation",
                        )
                        if created:
                            self._record_foundation_edge(
                                owner_index,
                                y,
                                column,
                                created[:cross],
                                self._node(points[0]),
                                self._node(points[1]),
                                thickness,
                            )

            self._strip_transform = None
            cap_half = self.spec.definition.width_top_pile / 2
            if element.vertical_alignment == 'Top':
                left_edge, right_edge = cap_half, cap_half + element.w2 - 2 * cap_half
            elif element.vertical_alignment == 'Bottom':
                left_edge, right_edge = cap_half + element.w2 - 2 * cap_half, cap_half
            else:
                left_edge = right_edge = element.w2 / 2
            if element.W1f > 0.0:
                wing_y = element.w1 + left_edge + element.W1f / 2.0
                self._add_foundation_wing(element, owner_index, wing_y, element.W1f)
            if element.W3f > 0.0:
                wing_y = -element.w3 - right_edge - element.W3f / 2.0
                self._add_foundation_wing(element, owner_index, wing_y, element.W3f)
            if isinstance(element, Pier) and element.shoulder_height:
                self._add_pier_shoulders(element, owner_index, centres)

    def _add_pier_shoulders(self, pier: Pier, owner_index: int, centres: Sequence[float]) -> None:
        """Rectangular masonry approximation on the two transverse pier extensions."""
        height = pier.shoulder_height
        definition = self.spec.definition
        if not math.isfinite(height) or height < 0:
            raise ValueError('Rectangular shoulder height must be nonnegative and finite')
        if (pier.vertical_alignment != 'Center' or pier.w1 or pier.w3 or
                abs(definition.width_top_pile - definition.width) > 1e-6 or
                definition.inclination_angle or definition.slope):
            raise NotImplementedError('Rectangular shoulders currently require a straight, level bridge and a centered, untapered pier')
        if pier.w2 <= definition.width + 1e-6:
            raise ValueError('Rectangular shoulders require the pier to be wider than the bridge')
        if height > self._deck_z + 1e-6:
            raise ValueError('Rectangular shoulder height cannot exceed the deck height')
        rows = max(1, _arrotonda(height / definition.nl))
        centre = self._element_origin(pier)
        points_x = [centre + x for x in discretize_top_pileb2(self.spec.elements, owner_index)]
        edge = definition.width / 2
        for y, width in self._support_strips(pier, centres):
            if abs(y) - width / 2 < edge - 1e-6:
                continue
            for left, right in zip(points_x, points_x[1:]):
                columns = max(1, _arrotonda((right-left) / definition.nl))
                self._add_mesh3([Point3D(left, y, 0), Point3D(right, y, 0),
                                 Point3D(right, y, height), Point3D(left, y, height)],
                                rows, columns, pier.material_key, width, False,
                                'CSharp_PierShoulder')

    def _support_rows(self, element, centres):
        """C# AddSpallePile strip locations, before the skew transform."""
        definition = self.spec.definition
        special = (abs(definition.width_top_pile - definition.width) > 1e-6
                   or element.w1 or element.w3 or element.vertical_alignment != 'Center')
        if not special:
            return [(y, width, None) for y, width in self._support_strips(element, centres)]
        widths = [strip.width for strip in definition.corsias]
        if not widths:
            return []
        cap_width = definition.width_top_pile
        cap = list(widths)
        cap[0] += (cap_width - definition.width) / 2
        cap[-1] += (cap_width - definition.width) / 2
        delta = element.w2 - cap_width
        if element.vertical_alignment == 'Center':
            plus = minus = delta / 2
            top_edge = element.w2 / 2
        elif element.vertical_alignment == 'Top':
            plus, minus = 0, delta
            top_edge = cap_width / 2
        elif element.vertical_alignment == 'Bottom':
            plus, minus = delta, 0
            top_edge = cap_width / 2 + delta
        else:
            raise NotImplementedError('Unsupported support vertical alignment')
        bottom_edge = top_edge + element.w1
        if element.H <= 0 and (element.w1 or element.w3):
            raise NotImplementedError('Transversely tapered supports require positive height')
        rows = []
        for index, base in enumerate(cap):
            top_width = base + (plus if index == 0 else 0) + (minus if index == len(cap)-1 else 0)
            bottom_width = top_width + (element.w1 if index == 0 else 0) + (element.w3 if index == len(cap)-1 else 0)
            if top_width <= 0 or bottom_width <= 0:
                raise ValueError('Support strip width must be positive')
            top_y = top_edge - top_width / 2
            bottom_y = bottom_edge - bottom_width / 2
            rows.append((bottom_y, bottom_width,
                         (top_y, bottom_y, 0.0, -element.H, top_width, bottom_width)))
            top_edge -= top_width
            bottom_edge -= bottom_width
        return rows

    def _support_strips(self, element: Abutment | Pier, centres: Sequence[float]) -> list[tuple[float, float]]:
        """Keep deck strips and subdivide any centered transverse extension."""
        widths = [corsia.width for corsia in self.spec.definition.corsias]
        difference = element.w2 - sum(widths)
        if abs(difference) <= 1e-6:
            return list(zip(centres, widths))
        if element.vertical_alignment != 'Center' or element.w1 or element.w3:
            raise NotImplementedError('Non-centered or transversely tapered support widths are not yet supported')
        if difference > 0:
            if self.spec.definition.nl <= 0:
                raise ValueError('Mesh length must be positive')
            extension = difference / 2.0
            count = max(1, math.ceil(extension / self.spec.definition.nl))
            thickness = extension / count
            edge = sum(widths) / 2.0
            positive = [(edge + (i + 0.5) * thickness, thickness) for i in reversed(range(count))]
            negative = [(-edge - (i + 0.5) * thickness, thickness) for i in range(count)]
            return positive + list(zip(centres, widths)) + negative
        if len(widths) == 1:
            if element.w2 <= 0:
                raise ValueError('Support transverse width must be positive')
            return [(centres[0], element.w2)]
        adjustment = difference / 2.0
        widths[0] += adjustment
        widths[-1] += adjustment
        if min(widths) <= 0:
            raise NotImplementedError('Support width is too narrow for the current deck strips')
        shifted = list(centres)
        shifted[0] += adjustment / 2.0
        shifted[-1] -= adjustment / 2.0
        return list(zip(shifted, widths))

    def _add_foundation_wing(
        self,
        element: Abutment | Pier,
        owner_index: int,
        y: float,
        width: float,
    ) -> None:
        """Port of the C# ``W1f``/``W3f`` transverse foundation blocks."""
        if element.Hf <= 0.0:
            return
        centre = self._element_origin(element)
        bottom = [
            centre + value
            for value in discretize_bottom_foundation_pileb2(
                self.spec.elements, owner_index
            )
        ]
        rows = max(1, _arrotonda(element.Hf / self.spec.definition.nl))
        for column in range(len(bottom) - 1):
            points = [
                Point3D(bottom[column], y, -element.H - element.Hf),
                Point3D(bottom[column + 1], y, -element.H - element.Hf),
                Point3D(bottom[column + 1], y, -element.H),
                Point3D(bottom[column], y, -element.H),
            ]
            cross = max(
                1,
                _arrotonda(
                    abs(bottom[column + 1] - bottom[column])
                    / self.spec.definition.nl
                ),
            )
            created = self._add_mesh3(
                points,
                rows,
                cross,
                element.material_foundation_key,
                width,
                False,
                "CSharp_Foundation",
            )
            if created:
                self._record_foundation_edge(
                    owner_index,
                    y,
                    column,
                    created[:cross],
                    self._node(points[0]),
                    self._node(points[1]),
                    width,
                )

    def _default_model_point(self) -> None:
        """Port of ``ModelPointOperations.TryAddDefaultModelPoints``.

        C# selects the highest-Z structural node closest to the plan centre of
        all nodes at that elevation.
        """
        if not self.nodes:
            return
        z_max = max(point.z for point in self.nodes.values())
        top = [
            (key, point)
            for key, point in self.nodes.items()
            if abs(point.z - z_max) <= 1.0e-9
        ]
        if not top:
            return
        x_mid = (max(point.x for _, point in top) + min(point.x for _, point in top)) / 2.0
        y_mid = (max(point.y for _, point in top) + min(point.y for _, point in top)) / 2.0
        key, point = min(
            top,
            key=lambda item: (item[1].x - x_mid) ** 2 + (item[1].y - y_mid) ** 2,
        )
        self._monitoring_points.append(
            MonitoringPoint(
                key=1,
                element_key=key,
                element_type="Node",
                id_vertex=0,
                description=f"Point in ({{X:{point.x:g} Y:{point.y:g} Z:{point.z:g}}})",
                point=point,
            )
        )

    # -- structural monitoring points ----------------------------------------

    def _select_structural_points(
        self,
        abscissa: Sequence[float],
        centres: Sequence[float],
    ) -> List[Tuple[int, str]]:
        """Pick arch-crown and pier top/bottom nodes on the outer/central strips.

        Returns ``(node_key, label)`` pairs in a stable order:

        * for every span: the arch-crown intrados node on the -Y, central and
          +Y strips;
        * for every pier: the shaft top (Z=0) and shaft base (Z=-H) nodes on
          the -Y and +Y strips.

        Quads lie in XZ planes at their strip centre, so "-Y"/"+Y" are the
        outermost strips and "0Y" is the strip whose centre is closest to
        Y=0 (with an even strip count no strip lies exactly on Y=0).
        """
        if not centres:
            return []
        tol = 1.0e-6
        y_neg = min(centres)
        y_pos = max(centres)
        y_mid = min(centres, key=lambda value: (abs(value), value))

        def group_nodes(groups: Tuple[str, ...]) -> Dict[int, Point3D]:
            keys = {
                key
                for quad in self.quads.values()
                if quad.group in groups
                for key in quad.node_keys
            }
            return {key: self.nodes[key] for key in keys}

        def pick(candidates: Dict[int, Point3D], *, y: float, x: float,
                 z: Optional[float] = None, lowest: bool = False) -> Optional[int]:
            pool = [
                (key, point) for key, point in candidates.items()
                if abs(point.y - y) <= tol
                and (z is None or abs(point.z - z) <= 1.0e-4)
            ]
            if not pool:
                return None
            dx_min = min(abs(point.x - x) for _, point in pool)
            pool = [(key, point) for key, point in pool if abs(abs(point.x - x) - dx_min) <= 1.0e-4]
            if lowest:
                return min(pool, key=lambda item: (item[1].z, item[1].x))[0]
            return min(pool, key=lambda item: item[1].x)[0]

        selected: List[Tuple[int, str]] = []
        arch_nodes = group_nodes(("CSharp_Arch", "CSharp_ArchReinforcement"))
        span_centres: List[float] = []
        for element, x_value in zip(self.spec.elements, abscissa):
            if isinstance(element, Span):
                span_centres.append(x_value)
        for span_index, x_crown in enumerate(span_centres, start=1):
            for label, y in (("-Y", y_neg), ("0Y", y_mid), ("+Y", y_pos)):
                key = pick(arch_nodes, y=y, x=x_crown, lowest=True)
                if key is not None:
                    selected.append((key, f"Span {span_index} arch crown {label}"))

        pier_nodes = group_nodes(("CSharp_Pier",))
        for pier_index, pier in enumerate(self.spec.piers, start=1):
            if pier.H <= 0.0:
                continue
            x_pier = self._element_origin(pier)
            for level, z in (("top", 0.0), ("bottom", -pier.H)):
                for label, y in (("-Y", y_neg), ("+Y", y_pos)):
                    key = pick(pier_nodes, y=y, x=x_pier, z=z)
                    if key is not None:
                        selected.append((key, f"Pier {pier_index} {level} {label}"))
        # Avoid duplicate node keys (e.g. single-strip models where -Y = +Y).
        unique: List[Tuple[int, str]] = []
        seen: set[int] = set()
        for key, label in selected:
            if key not in seen:
                seen.add(key)
                unique.append((key, label))
        return unique

    def _add_structural_model_points(self, points: Sequence[Tuple[int, str]]) -> None:
        existing = {mp.element_key for mp in self._monitoring_points}
        next_key = max((mp.key for mp in self._monitoring_points), default=0) + 1
        for node_key, label in points:
            if node_key in existing:
                continue
            point = self.nodes[node_key]
            self._monitoring_points.append(
                MonitoringPoint(
                    key=next_key,
                    element_key=node_key,
                    element_type="Node",
                    id_vertex=0,
                    description=f"{label} · Point in ({{X:{point.x:g} Y:{point.y:g} Z:{point.z:g}}})",
                    point=point,
                )
            )
            existing.add(node_key)
            next_key += 1

    def _parse_fraction(self, pos: object) -> Optional[float]:
        if isinstance(pos, (int, float)):
            f = float(pos)
            return f if 0.0 < f < 1.0 else None
        text = str(pos or "").strip().lower()
        if text in ("none", "false", "", "0"):
            return None
        if text in ("1/4", "0.25", "25%"):
            return 0.25
        if text in ("1/2", "0.5", "0.50", "50%"):
            return 0.50
        if text in ("3/4", "0.75", "75%"):
            return 0.75
        try:
            val = float(text)
            if 0.0 < val < 1.0:
                return val
        except ValueError:
            pass
        return None

    def _build_span_loads_and_control_points(self) -> None:
        """Place line loads on the road surface and attach control model points on the arch intrados."""
        cursor = 0.0
        span_idx = 0
        w_half = self.spec.width / 2.0
        deck_z = self._deck_z

        for element in self.spec.elements:
            if isinstance(element, Span):
                span_idx += 1
                span_start = cursor
                span_len = element.L
                cursor += span_len
                fraction = self._parse_fraction(getattr(element, "load_position", "none"))
                if fraction is None:
                    continue
                x_target = span_start + fraction * span_len

                # 1. Find deck quad covering x_target at deck_z
                deck_quad = None
                for q in self.quads.values():
                    pts = [self.nodes[k] for k in q.node_keys]
                    top_pts = [p for p in pts if abs(p.z - deck_z) <= 1.0e-3]
                    if len(top_pts) >= 2:
                        x_min = min(p.x for p in top_pts)
                        x_max = max(p.x for p in top_pts)
                        if x_min - 1.0e-4 <= x_target <= x_max + 1.0e-4:
                            deck_quad = q
                            break

                # 2. Find arch intrados node closest to x_target
                arch_quads = [
                    q for q in self.quads.values()
                    if q.group in ("CSharp_Arch", "CSharp_ArchReinforcement")
                ]
                arch_nodes = {k: self.nodes[k] for q in arch_quads for k in q.node_keys}
                candidates = [
                    (k, p) for k, p in arch_nodes.items()
                    if span_start - 1.0 <= p.x <= (span_start + span_len + 1.0)
                ]
                if candidates:
                    dx_min = min(abs(p.x - x_target) for _, p in candidates)
                    near_nodes = [
                        (k, p) for k, p in candidates
                        if abs(abs(p.x - x_target) - dx_min) <= 1.0e-3
                    ]
                    best_key, best_pt = min(near_nodes, key=lambda item: (item[1].z, item[1].x))

                    pos_label = getattr(element, "load_position", f"{fraction:.2f}")
                    existing_mp = next(
                        (mp for mp in self._monitoring_points if mp.element_key == best_key),
                        None,
                    )
                    if existing_mp is None:
                        mp_key = max((mp.key for mp in self._monitoring_points), default=0) + 1
                        mp = MonitoringPoint(
                            key=mp_key,
                            element_key=best_key,
                            element_type="Node",
                            id_vertex=0,
                            description=f"Span {span_idx} {pos_label} arch control point · Point in ({{X:{best_pt.x:g} Y:{best_pt.y:g} Z:{best_pt.z:g}}})",
                            point=best_pt,
                        )
                        self._monitoring_points.append(mp)
                        control_key = mp_key
                    else:
                        control_key = existing_mp.key

                    if self._control_model_point_key is None:
                        self._control_model_point_key = control_key

                # 3. Create LineLoadElement if deck_quad found
                if deck_quad is not None:
                    load_val = float(getattr(element, "load_value", 0.01) or 0.01)
                    ll_key = len(self._line_loads) + 1
                    self._line_loads.append(
                        GeneratedLineLoad(
                            key=ll_key,
                            element_key=deck_quad.key,
                            element_type="Quad",
                            load_template_key=3,
                            point1=(round(x_target, 4), -w_half, round(deck_z, 4)),
                            point2=(round(x_target, 4), w_half, round(deck_z, 4)),
                            load_value=load_val,
                        )
                    )
            elif isinstance(element, (Pier, Abutment)):
                cursor += element.b2

    # -- foundation edge / GLR / Restraint generation -----------------------

    def _record_foundation_edge(
        self,
        owner_index: int,
        strip_y: float,
        sub_index: int,
        quad: GeneratedQuad | List[GeneratedQuad],
        left_node: int,
        right_node: int,
        width: float,
    ) -> None:
        self._foundation_edges.append(
            (owner_index, strip_y, sub_index, quad if isinstance(quad, list) else [quad], left_node, right_node, width)
        )

    def _foundation_tag(self, owner_index: int) -> str:
        element = self.spec.elements[owner_index]
        if isinstance(element, Pier):
            pier_number = sum(
                1
                for item in self.spec.elements[: owner_index + 1]
                if isinstance(item, Pier)
            )
            return f"pier_{pier_number}"
        if isinstance(element, Abutment):
            return "abutment_left" if element.kind == "Sinistra" else "abutment_right"
        return ""

    def _build_foundation_supports(self) -> None:
        """Create supports for the straight, aligned foundation edges we generate."""
        if not self._foundation_edges:
            return
        edges = sorted(
            self._foundation_edges,
            key=lambda item: (item[0], -item[1], item[2]),
        )
        for owner_index, strip_y, _sub, quads, left_key, right_key, width in edges:
            left = self.nodes[left_key]
            right = self.nodes[right_key]
            if right.x < left.x:
                left_key, right_key = right_key, left_key
                left, right = right, left
            strip_width = width
            owner = self.spec.elements[owner_index]
            fixed = (owner.is_fix_dir_x, owner.is_fix_dir_z, owner.is_fix_dir_y,
                     owner.is_fix_rot_dir_x, owner.is_fix_rot_dir_z, owner.is_fix_rot_dir_y)
            behaviours = tuple("Fixed" if value else "Free" for value in fixed)
            stiffness = [-1.0 if value else 0.0 for value in fixed]
            if not owner.is_fix_dir_z:
                # GeometryRestraint.SetRestraintK changes Elastic back to Fixed;
                # BridgeMesher then sets K2 to Kz times the GLR footprint area.
                behaviours = behaviours[:1] + ("Fixed",) + behaviours[2:]
                stiffness[1] = owner.Kz * strip_width * _dist(left, right)
            stiffness_tuple = tuple(stiffness)
            glr_key = self._next_glr_key
            self._next_glr_key += 1
            glr = GeneratedGeometryLineRestraint(
                key=glr_key,
                name=str(glr_key),
                node_key1=right_key,
                node_key2=left_key,
                b=strip_width,
                k=stiffness_tuple,
                behaviours=behaviours,
            )
            self._glrs.append(glr)

            for quad in quads:
                edge_left_key, edge_right_key = quad.node_keys[:2]
                edge_left, edge_right = self.nodes[edge_left_key], self.nodes[edge_right_key]
                if edge_right.x < edge_left.x:
                    edge_left_key, edge_right_key = edge_right_key, edge_left_key
                    edge_left, edge_right = edge_right, edge_left
                nc_left = self._node_c(edge_left_key)
                nc_right = self._node_c(edge_right_key)
                # C# ``BridgeMesher`` writes the full GLR footprint stiffness
                # (Kz * B * L_edges) on the geometry object.  RestraintMesher
                # splits that GLR at every Quad face but copies the full K
                # array, which double-counts the subgrade reaction whenever one
                # GLR spans several Quad columns.  The serialized HRX is the
                # authoritative solver input, so write each child restraint with
                # its own tributary area: Kz * B * L_quad.  The children then
                # sum exactly to the parent GLR stiffness.
                restraint_stiffness = list(stiffness)
                if not owner.is_fix_dir_z:
                    tributary_length = _dist(edge_left, edge_right)
                    restraint_stiffness[1] = owner.Kz * strip_width * tributary_length
                half = strip_width / 2.0
                angle = math.radians(self.spec.definition.inclination_angle)
                dx, dy = half * math.sin(angle), half * math.cos(angle)
                point1 = Point3D(edge_left.x - dx, strip_y - dy, edge_left.z)
                point2 = Point3D(edge_right.x - dx, strip_y - dy, edge_right.z)
                point3 = Point3D(edge_right.x + dx, strip_y + dy, edge_right.z)
                point4 = Point3D(edge_left.x + dx, strip_y + dy, edge_left.z)
                restraint = GeneratedRestraint(
                    key=self._next_restraint_key,
                    name=str(self._next_restraint_key),
                    node_key1=edge_left_key,
                    node_key2=edge_right_key,
                    node_c_key1=nc_left,
                    node_c_key2=nc_right,
                    computational_element_key=quad.key,
                    computational_element_type="Quad",
                    computational_element_edge=0,
                    material_key=0,
                    parent_key=glr_key,
                    parent_type_element="GeometryLineRestraint",
                    k=tuple(restraint_stiffness),
                    behaviours=behaviours,
                    g=Point3D((edge_left.x + edge_right.x) / 2.0, strip_y,
                              (edge_left.z + edge_right.z) / 2.0),
                    point1=point1,
                    point2=point2,
                    point3=point3,
                    point4=point4,
                    foundation_tag=self._foundation_tag(owner_index),
                )
                self._next_restraint_key += 1
                self._restraints.append(restraint)

    def _find_strip_width(self, strip_y: float) -> float:
        centres = self._strip_centres()
        for corsia, centre in zip(self.spec.definition.corsias, centres):
            if abs(centre - strip_y) < 1.0e-6:
                return corsia.width
        return self.spec.definition.corsias[0].width

    def _node_c(self, node_key: int) -> int:
        existing = self._node_c_map.get(node_key)
        if existing is not None:
            return existing
        key = self._next_node_c_key
        self._next_node_c_key += 1
        self._node_c_map[node_key] = key
        self._node_cs.append(GeneratedNodeC(key=key, node_key=node_key))
        return key

    # -- public entry point --------------------------------------------------

    def mesh(self) -> CSharpBridgeMesh:
        if self.spec.wizard_type == "RailBridge2":
            raise NotImplementedError("RailBridge2 wall and backfill meshing is not yet supported")
        if self.spec.definition.attributes.get("IsVehicleLoad", "false").lower() == "true":
            raise NotImplementedError("Native wizard vehicle-load generation is not yet supported")
        if any(trunk.get("Trunk", "Straight") != "Straight" for trunk in self.spec.definition.trunks):
            raise NotImplementedError("Curved C# bridge trunks are not yet supported by the mesher")
        if any((item.spinta_passiva_sx or item.spinta_passiva_dx)
               for item in self.spec.elements if isinstance(item, (Abutment, Pier))):
            raise NotImplementedError("Passive earth-pressure surface restraints are not yet supported")
        abscissa = self._abscissa()
        if not abscissa:
            raise ValueError("bridge abscissa is empty")
        self._total_length = abscissa[-1]
        # Bridge.H is WizardBridge.getHeigthBridge / Elevations.GetMaxZ,
        # which considers the top of all three layers at every section.
        self._deck_z = max((0.0, *(section.Z3 for section in self.spec.elevations.elevations)))
        spans = [element for element in self.spec.elements if isinstance(element, Span)]
        templates = {int(template["Key"]): template for template in DEFAULT_TEMPLATES}
        templates.update({int(template["Key"]): template for template in self.spec.material_templates})
        centres = self._strip_centres()
        strips = self.spec.definition.corsias
        for index, (corsia, y) in enumerate(zip(strips, centres)):
            widening = (self.spec.definition.width_top_pile - self.spec.definition.width) / 2
            if index == 0 or index == len(strips) - 1:
                # With one strip both edges widen symmetrically.
                side = 0 if len(strips) == 1 else (1 if index == 0 else -1)
                bottom_width = corsia.width + widening * (2 if len(strips) == 1 else 1)
                self._strip_transform = (y, y + side * widening / 2, self._deck_z, 0.0,
                                         corsia.width, bottom_width)
            else:
                self._strip_transform = None
            heights = 4 if corsia.height > 0.0 else 3
            material = templates.get(corsia.material_key, {})
            fill_override = (corsia.material_key
                             if material.get("PurposeType") == "MasonryMaterial" else 0)
            self._add_bridge_row(
                abscissa,
                spans,
                y,
                corsia.width,
                heights,
                corsia.height,
                fill_override,
            )
        self._strip_transform = None
        # C# AddSpallePile runs once after all transverse rows have been built.
        self._add_spalle_pile(centres)
        # Select the structural monitoring nodes on the undeformed, unskewed
        # strip geometry; their final coordinates are read after the transform.
        structural_points = self._select_structural_points(abscissa, centres)
        # The native straight-strip transform shifts X by Y*tan(angle), then
        # applies the longitudinal grade. C# measures strip widths along its
        # skew normal, hence the 1/cos(angle) thickness multiplier.
        slope = self.spec.definition.slope
        angle = math.radians(self.spec.definition.inclination_angle)
        if abs(math.cos(angle)) < 1.0e-9:
            raise ValueError("inclination angle cannot make the strip width infinite")
        if slope or angle or self._quad_transforms:
            scale = 1.0 / math.cos(angle)
            original = dict(self.nodes)
            node_targets = {}
            widths = {}
            for quad in self.quads.values():
                transform = self._quad_transforms.get(quad.key)
                for key in quad.node_keys:
                    point = original[key]
                    y, width = point.y, quad.thickness
                    if transform:
                        yt, yb, zt, zb, wt, wb = transform
                        t = min(1.0, max(0.0, (point.z - zb) / (zt - zb))) if zt > zb else 0.0
                        y = yb + t * (yt - yb)
                        width = wb + t * (wt - wb)
                    x = point.x + y * math.tan(angle)
                    target = Point3D(round(x, 4), round(y, 4), round(point.z + x * slope, 4))
                    if key in node_targets and _dist(node_targets[key], target) > 0.001:
                        raise NotImplementedError('Conflicting transverse strip transformations at a shared node')
                    node_targets[key] = target
                    widths[(quad.key, key)] = width * scale
            for key, point in original.items():
                if key not in node_targets:
                    x = point.x + point.y * math.tan(angle)
                    node_targets[key] = Point3D(round(x, 4), point.y, round(point.z + x * slope, 4))
            self.nodes.update(node_targets)
            for quad in self.quads.values():
                quad.thickness *= scale
                quad.kinematics = compute_quad_kinematics(
                    [self.nodes[key] for key in quad.node_keys],
                    thickness=quad.thickness,
                    out_of_plane_normal=(math.sin(angle), math.cos(angle), 0.0),
                    allow_skew_normal=bool(angle or quad.key in self._quad_transforms),
                )
                quad.kinematics.thicknesses = [widths[(quad.key, key)] for key in quad.node_keys]
            self._foundation_edges = [
                (owner, y, sub, quads, left, right, width * scale)
                for owner, y, sub, quads, left, right, width in self._foundation_edges
            ]
        self._build_foundation_supports()
        self._default_model_point()
        self._add_structural_model_points(structural_points)
        self._build_span_loads_and_control_points()
        for index, element in enumerate(self.spec.piers, start=1):
            centre = self._element_origin(element)
            self._piers.append(
                PierMetadata(
                    id=f"pier_{index}",
                    index=index,
                    origin=Point3D(centre, 0.0, 0.0),
                    x_start=centre - element.b2 / 2.0,
                    x_end=centre + element.b2 / 2.0,
                    restraint_keys=[],
                )
            )
        return CSharpBridgeMesh(
            spec=self.spec,
            nodes=self.nodes,
            quads=self.quads,
            geometry_line_restraints=self._glrs,
            restraints=self._restraints,
            node_cs=self._node_cs,
            monitoring_points=self._monitoring_points,
            piers=self._piers,
            deck_z=self._deck_z,
            total_length=self._total_length,
            line_loads=self._line_loads,
            control_model_point_key=self._control_model_point_key,
        )


def build_csharp_bridge_mesh(spec: CSharpBridgeSpec) -> CSharpBridgeMesh:
    return CSharpMesher(spec).mesh()
