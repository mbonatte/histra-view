from __future__ import annotations

from typing import Any

import numpy as np

from histra.model.model import Model
from histra.solver.incremental_integrator import StaticIntegrator
from histra.solver.model_manager import ModelManager
from histra.solver.program import Program
from histra.types.linear_system import LinearSolveError, LinearSystem


_SUPPORTED_ARC_LENGTH_PROCEDURES = {
    "onlycontrolpoint",
    "onlymodelpointsselected",
    "alldegreesoffreedom",
    "projectedcontrolpoint",
}


class ArcLength(StaticIntegrator):
    """Arc-length integrator ported from the original C# implementation.

    The algorithm separates the residual displacement ``delta_u_bar`` from the
    reference-load displacement ``delta_u_hat`` and enforces the quadratic
    constraint over either a control DOF or all active generalized DOFs.

    ``constraint_mode="csharp"`` preserves the original quadratic calculation
    and exact zero tests. The explicit ``"stable"`` option retains Python's
    simplified one-dimensional correction and small-denominator safeguards;
    it can produce different last bits and branch decisions.

    The predictor resets the squared radius from ``Analysis.Dr2`` as in C#.
    Commit-time radius limiting follows C# in the default mode; stable mode
    retains Python's comparison with radius-squared.
    """

    def __init__(self, *, constraint_mode: str = "csharp") -> None:
        if constraint_mode not in ("csharp", "stable"):
            raise ValueError("constraint_mode must be 'csharp' or 'stable'")
        super().__init__()
        self.constraint_mode = constraint_mode
        self._target_displacement = 0.0
        self._target_displacement_base = 0.0
        self._arc_length2 = 0.0
        self._alpha2 = 0.0
        self._delta_u_hat: np.ndarray | None = None
        self._delta_u_bar: np.ndarray | None = None
        self._delta_u: np.ndarray | None = None
        self._delta_u_step: np.ndarray | None = None
        self._phat: np.ndarray | None = None
        self._phat_ref: np.ndarray | None = None
        self._delta_lambda_step = 0.0
        self._current_lambda = 0.0
        self._adapt_exponent = 0.5
        self._dofs: np.ndarray | None = None
        self._projected_control_indices: np.ndarray | None = None
        self._projected_control_weights: np.ndarray | None = None
        self._projected_control_signature: tuple[Any, ...] | None = None
        self._lf_items: list[tuple[float, float]] = []
        self._current_lf_item = 1
        self._initialized = False
        self._step_snapshot: dict[str, Any] | None = None
        self._delta_u_hat_matrix_version = -1
        self._delta_u_hat_phat: np.ndarray | None = None
        self._delta_u_hat_phat_id = -1

    def _load_items(self, an: Any) -> list[tuple[float, float]]:
        items = list(getattr(getattr(an, "load_function", None), "items", []) or [])
        values = sorted(
            [(float(item.pseudo_time), float(item.multiplier)) for item in items],
            key=lambda item: item[0],
        )
        return values if len(values) >= 2 else [(0.0, 0.0), (1.0, 1.0)]

    def _segment_sign(self) -> float:
        previous = self._lf_items[self._current_lf_item - 1][1]
        current = self._lf_items[self._current_lf_item][1]
        sign = float(np.sign(current - previous))
        return sign if sign != 0.0 else 1.0

    def _model_point_dofs(self, model: Model, an: Any, point_key: int) -> list[int]:
        point = getattr(model.collections, "model_points", {}).get(int(point_key))
        if point is None:
            return []
        components = [
            float(getattr(an, "dir_x", 0.0)),
            float(getattr(an, "dir_y", 0.0)),
            float(getattr(an, "dir_z", 0.0)),
        ]
        elements = []
        if point.element_type == "Quad":
            quad = model.collections.quads.get(point.element_key)
            if quad is not None:
                elements.append(quad)
        elif point.element_type == "Node":
            for quad in model.collections.quads.values():
                if point.element_key in quad.node_keys:
                    elements.append(quad)
        else:
            raise NotImplementedError(
                f"ArcLength ModelPoint {point.key} targets unsupported type "
                f"{point.element_type!r}"
            )

        result: list[int] = []
        for element in elements:
            for component, direction in enumerate(components):
                if direction == 0.0 or component >= len(element.aff) or not element.aff[component]:
                    continue
                dof = int(element.aff[component][0].gdl) - 1
                if dof not in result:
                    result.append(dof)
        return result

    def _select_dofs(
        self,
        p: Program,
        model: Model,
        an: Any,
        fallback_dof: int | None = None,
    ) -> np.ndarray:
        n = p.ls.n
        raw_procedure = str(
            getattr(an, "arc_length_procedure", "OnlyControlPoint")
        )
        procedure = raw_procedure.casefold()
        if procedure not in _SUPPORTED_ARC_LENGTH_PROCEDURES:
            raise ValueError(
                f"Unknown ArcLengthProcedure={raw_procedure!r}; expected "
                "OnlyControlPoint, OnlyModelPointsSelected, "
                "AllDegreesOfFreedom, or ProjectedControlPoint."
            )
        master = int(getattr(an, "master_point", -10))

        if "modelpointsselected" in procedure:
            selected: list[int] = []
            for point_key, active in getattr(an, "active_model_points", {}).items():
                if active:
                    selected.extend(self._model_point_dofs(model, an, int(point_key)))
            unique = list(dict.fromkeys(selected))
            return np.asarray(unique if unique else list(range(n)), dtype=int)

        if "controlpoint" in procedure:
            if master != -10:
                selected = self._model_point_dofs(model, an, master)
                if selected:
                    return np.asarray(selected, dtype=int)
            if fallback_dof is not None and 0 <= int(fallback_dof) < n:
                return np.array([int(fallback_dof)], dtype=int)

            # C# auto-selection maximizes deltaUhat[i] * phat[i].
            if self._delta_u_hat is not None and self._phat is not None and n:
                products = self._delta_u_hat * self._phat
                positive = np.maximum(products, 0.0)
                candidate = int(np.argmax(positive))
                return np.array([candidate], dtype=int)

        # C# GetVect uses the full vector when ModelPointOperations returns -1.
        return np.arange(n, dtype=int)

    def _selected(self, vector: np.ndarray) -> np.ndarray:
        if self._projected_control_indices is not None:
            return np.asarray(
                [
                    float(
                        np.dot(
                            vector[self._projected_control_indices],
                            self._projected_control_weights,
                        )
                    )
                ],
                dtype=float,
            )
        if self._dofs is None or len(self._dofs) == 0:
            return vector
        return vector[self._dofs]

    @staticmethod
    def _quad_point_projection_weights(
        quad: Any,
        point: Any,
        node_index: int,
        direction: np.ndarray,
    ) -> np.ndarray:
        """Map a Quad's seven local DOFs to one projected point displacement."""

        offset = np.asarray(
            (point.x - quad.g.x, point.y - quad.g.y, point.z - quad.g.z),
            dtype=float,
        )
        local = np.zeros(7, dtype=float)
        local[:3] = direction
        axes = np.eye(3, dtype=float)
        local[3:6] = [
            float(np.dot(direction, np.cross(axis, offset))) for axis in axes
        ]
        if node_index == 2:
            denominator = float(quad.sin[2])
            if abs(denominator) > 1.0e-30:
                coefficient = -float(quad.length[3]) * float(quad.sin[3]) / denominator
                distortion_direction = (
                    float(quad.sin[1]) * np.asarray(quad.reference_e1, dtype=float)
                    + float(quad.cos[1]) * np.asarray(quad.reference_e2, dtype=float)
                )
                local[6] = coefficient * float(np.dot(direction, distortion_direction))
        elif node_index == 3:
            distortion_direction = (
                -float(quad.sin[0]) * np.asarray(quad.reference_e1, dtype=float)
                + float(quad.cos[0]) * np.asarray(quad.reference_e2, dtype=float)
            )
            local[6] = float(quad.length[3]) * float(
                np.dot(direction, distortion_direction)
            )
        return local

    def _build_projected_control(
        self,
        model: Model,
        point: Any,
        direction: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Precompute a compact sparse global projection outside the hot path."""

        element_type = str(point.element_type).casefold().split(".")[-1]
        projections: list[tuple[Any, Any, int]] = []
        if element_type == "node":
            node = model.collections.nodes[int(point.element_key)]
            projections = [
                (quad, node.point, node_index)
                for quad in model.collections.quads.values()
                for node_index, node_key in enumerate(quad.node_keys)
                if int(node_key) == int(node.key)
            ]
        elif element_type == "quad":
            quad = model.collections.quads[int(point.element_key)]
            vertex = int(point.id_vertex)
            if vertex == 0:
                # Quad-centre output uses only its three translations.
                local = np.zeros(7, dtype=float)
                local[:3] = direction
                projections = [(quad, None, -1)]
            elif 1 <= vertex <= len(quad.node_keys):
                node = model.collections.nodes[int(quad.node_keys[vertex - 1])]
                projections = [(quad, node.point, vertex - 1)]
            else:
                raise ValueError(
                    f"ProjectedControlPoint does not support IdVertex={vertex}."
                )
        else:
            raise ValueError(
                "ProjectedControlPoint currently supports Node and Quad model points; "
                f"received {point.element_type!r}."
            )
        if not projections:
            raise ValueError(
                f"ProjectedControlPoint model point {point.key} has no connected Quad."
            )

        scale = 1.0 / len(projections)
        global_weights: dict[int, float] = {}
        for quad, node_point, node_index in projections:
            if node_index == -1:
                local_weights = local
            else:
                local_weights = self._quad_point_projection_weights(
                    quad, node_point, node_index, direction
                )
            for local_dof, weight in enumerate(local_weights):
                if weight == 0.0:
                    continue
                for entry in quad.aff[local_dof]:
                    index = int(entry.gdl) - 1
                    if index < 0:
                        continue
                    global_weights[index] = global_weights.get(index, 0.0) + (
                        scale * weight * float(entry.alfa)
                    )
        indices = np.fromiter(sorted(global_weights), dtype=np.int64)
        weights = np.fromiter(
            (global_weights[int(index)] for index in indices), dtype=float
        )
        return indices, weights

    def _configure_projected_control(self, model: Model, an: Any) -> None:
        """Configure the opt-in physical ModelPoint arc-length coordinate.

        C# ``OnlyControlPoint`` constrains the first translational generalized
        DOF of every element connected to a Node ModelPoint.  That coordinate
        is not the projected displacement reported for the ModelPoint once
        element rotations become large.  ``ProjectedControlPoint`` leaves the
        C# path untouched and instead uses the same linear ModelPoint
        projection as graph/output processing as the scalar arc-length
        coordinate.  By default the projection follows the analysis load/
        graph direction.  The optional ``arc_length_control_dir_[xyz]``
        attributes allow continuation to use a different physical coordinate
        without changing the applied load direction.
        """

        raw_procedure = str(
            getattr(an, "arc_length_procedure", "OnlyControlPoint")
        )
        procedure = raw_procedure.casefold()
        if procedure not in _SUPPORTED_ARC_LENGTH_PROCEDURES:
            raise ValueError(
                f"Unknown ArcLengthProcedure={raw_procedure!r}; expected "
                "OnlyControlPoint, OnlyModelPointsSelected, "
                "AllDegreesOfFreedom, or ProjectedControlPoint."
            )
        if "projectedcontrolpoint" not in procedure:
            self._projected_control_indices = None
            self._projected_control_weights = None
            self._projected_control_signature = None
            return
        master = int(getattr(an, "master_point", -10))
        point = getattr(model.collections, "model_points", {}).get(master)
        if point is None:
            raise ValueError(
                "ProjectedControlPoint requires a valid Analysis.MasterPoint; "
                f"model point {master} was not found."
            )
        direction = np.asarray(
            [
                float(
                    getattr(
                        an,
                        "arc_length_control_dir_x",
                        getattr(an, "dir_x", 0.0),
                    )
                ),
                float(
                    getattr(
                        an,
                        "arc_length_control_dir_y",
                        getattr(an, "dir_y", 0.0),
                    )
                ),
                float(
                    getattr(
                        an,
                        "arc_length_control_dir_z",
                        getattr(an, "dir_z", 0.0),
                    )
                ),
            ],
            dtype=float,
        )
        if not np.any(direction):
            raise ValueError("ProjectedControlPoint requires a nonzero analysis direction.")
        reference_indices = np.asarray(
            getattr(an, "arc_length_control_reference_indices", ()), dtype=np.int64
        )
        reference_weights = np.asarray(
            getattr(an, "arc_length_control_reference_weights", ()), dtype=float
        )
        if reference_indices.size != reference_weights.size:
            raise ValueError(
                "ProjectedControlPoint reference indices and weights must have "
                "the same length."
            )
        signature = (
            procedure,
            master,
            *map(float, direction),
            tuple(map(int, reference_indices)),
            tuple(map(float, reference_weights)),
        )
        if (
            signature == self._projected_control_signature
            and self._projected_control_indices is not None
        ):
            return
        indices, weights = self._build_projected_control(model, point, direction)
        if reference_indices.size:
            combined = {
                int(index): float(weight) for index, weight in zip(indices, weights)
            }
            for index, weight in zip(reference_indices, reference_weights):
                key = int(index)
                combined[key] = combined.get(key, 0.0) - float(weight)
            indices = np.fromiter(sorted(combined), dtype=np.int64)
            weights = np.fromiter(
                (combined[int(index)] for index in indices), dtype=float
            )
        self._projected_control_indices = indices
        self._projected_control_weights = weights
        self._projected_control_signature = signature

    def _refresh_segment_load(self) -> None:
        if self._phat_ref is None:
            return
        self._phat = self._segment_sign() * self._phat_ref
        ModelManager._ptarget = self._phat.copy()
        multiplier = self._lf_items[self._current_lf_item][1]
        self._target_displacement = self._target_displacement_base * multiplier

    def domain_changed(self, p: Program, model: Model, size: int) -> None:
        an = self.state.analysis
        self._configure_projected_control(model, an)
        if not self._initialized:
            self._lf_items = self._load_items(an)
            self._current_lf_item = min(1, len(self._lf_items) - 1)
            self._target_displacement_base = float(getattr(an, "target_displacement", 0.0))
            self._arc_length2 = abs(float(getattr(an, "dr2", 1e-4)))
            self._alpha2 = 0.0
            self._phat_ref = np.asarray(ModelManager._ptarget, dtype=float).copy()
            self._initialized = True

        self._delta_u_hat = np.zeros(size)
        self._delta_u_bar = np.zeros(size)
        self._delta_u = np.zeros(size)
        self._delta_u_step = np.zeros(size)
        self._current_lambda = 0.0
        self._delta_lambda_step = 0.0
        self._refresh_segment_load()
        self._dofs = None
        self._delta_u_hat_matrix_version = -1
        self._delta_u_hat_phat = None
        self._delta_u_hat_phat_id = -1

        # Determine a stable automatic control DOF when no explicit point is
        # supplied.  A valid initial stiffness has already been assembled.
        if self._projected_control_indices is not None:
            # A scalar projection is used by _selected; the placeholder keeps
            # the established OnlyControlPoint radius scaling at one DOF.
            self._dofs = np.array([0], dtype=int)
        elif int(getattr(an, "master_point", -10)) == -10 and size:
            try:
                p.ls.solve(rhs=self._phat)
                self._delta_u_hat[:] = p.ls.x
                self._delta_u_hat_matrix_version = p.ls.matrix_version
                self._delta_u_hat_phat = self._phat.copy()
                self._delta_u_hat_phat_id = id(self._phat)
                self._dofs = self._select_dofs(p, model, an)
            except LinearSolveError:
                self._dofs = np.array([0], dtype=int)

    def new_step(
        self,
        p: Program,
        model: Model,
        ls: LinearSystem,
        an: Any,
        combination: int,
        step: int,
        dof: int,
    ) -> None:
        self.step = step
        self.iteration = 0
        # Normally this is a signature-only check. It rebuilds the compact
        # projection once when a caller intentionally changes the continuation
        # direction at a committed-step boundary.
        self._configure_projected_control(model, an)
        self._step_snapshot = {
            "u": None if self.u is None else self.u.copy(),
            "fext": None if ModelManager._fext is None else ModelManager._fext.copy(),
            "mult": self.mult,
            "lambda": self._current_lambda,
            "delta_lambda_step": self._delta_lambda_step,
            "delta_u_step": None if self._delta_u_step is None else self._delta_u_step.copy(),
        }

        if self.update_ptarget(p, model, an, combination, self.iteration):
            self._phat_ref = np.asarray(ModelManager._ptarget, dtype=float).copy()
            self._refresh_segment_load()
        if self._phat is None:
            raise RuntimeError("ArcLength reference load is not initialized")

        ls.solve(rhs=self._phat)
        self._delta_u_hat = ls.x.copy()
        self._delta_u_hat_matrix_version = ls.matrix_version
        self._delta_u_hat_phat = self._phat.copy()
        self._delta_u_hat_phat_id = id(self._phat)
        self._dofs = (
            np.array([0], dtype=int)
            if self._projected_control_indices is not None
            else self._select_dofs(p, model, an, fallback_dof=dof)
        )
        selected_hat = self._selected(self._delta_u_hat)
        denominator = float(np.dot(selected_hat, selected_hat) + self._alpha2)
        if denominator <= 1e-30:
            raise LinearSolveError("ArcLength has a zero reference-load displacement")

        # C# resets Dr2 at each NewStep.  For OnlyControlPoint it scales by
        # the number of selected DOFs; OnlyModelPointsSelected does not.
        self._arc_length2 = abs(float(getattr(an, "dr2", self._arc_length2)))
        radius2 = self._arc_length2
        procedure = str(getattr(an, "arc_length_procedure", "")).lower()
        dof_count = max(1, len(self._dofs))
        if "controlpoint" in procedure:
            radius2 *= dof_count

        delta_lambda = float(np.sqrt(radius2 / denominator))
        if bool(getattr(an, "is_max_arc_length_ray", False)):
            # Despite the property name, C# caps the predictor load increment,
            # not the geometric radius.  Preserve that behavior for reference
            # compatibility with ArcLength analyses already stored in SQLite.
            max_delta_lambda = abs(float(np.float32(getattr(an, "max_arc_length_ray", 1.0))))
            if max_delta_lambda > 0.0 and delta_lambda > max_delta_lambda:
                if "controlpoint" in procedure:
                    radius2 = abs(
                        max_delta_lambda**2
                        * (float(np.dot(selected_hat, selected_hat)) / max(1, len(self._dofs)) + self._alpha2)
                    ) * max(1, len(self._dofs))
                else:
                    radius2 = abs(max_delta_lambda**2 * denominator)
                self._arc_length2 = radius2
                delta_lambda = float(np.sqrt(radius2 / denominator))

        if self._projected_control_indices is None:
            selected_load = self._selected(self._phat)
            if delta_lambda * float(np.dot(selected_hat, selected_load)) < 0.0:
                delta_lambda *= -1.0
        elif float(selected_hat[0]) < 0.0:
            # The projection already includes the analysis direction.  Choose
            # the predictor that moves positively along that physical scalar.
            delta_lambda *= -1.0

        self._delta_lambda_step = delta_lambda
        self._current_lambda += delta_lambda
        self._delta_u = delta_lambda * self._delta_u_hat
        self._last_delta_u = self._delta_u.copy()
        self._last_delta_lambda = float(delta_lambda)
        self._delta_u_step[:] = self._delta_u
        ls.set_x_vector(self._delta_u)
        if self.u is not None:
            self.u += self._delta_u
        self.apply_load_domain(model, delta_lambda)
        ModelManager.update_domain(model, ls, self.state)

        display_radius = np.sqrt(radius2 / max(1, len(self._dofs))) if "controlpoint" in procedure else np.sqrt(radius2)
        p.log(
            f"Step {step} solving: dr={display_radius:.6g}, "
            f"dLambda={delta_lambda:.6g}"
        )

    def update(self, model: Model, p: Program, an: Any) -> int:
        self.iteration += 1
        ls = p.ls
        self._delta_u_bar = ls.x.copy()
        if self._phat is None or self._delta_u_step is None:
            self.errors.append("ArcLength is not initialized")
            return -10

        reference_is_cached = (
            self._delta_u_hat is not None
            and self._delta_u_hat_matrix_version == ls.matrix_version
            and self._delta_u_hat_phat_id == id(self._phat)
        )
        if not reference_is_cached:
            try:
                ls.solve(rhs=self._phat)
            except LinearSolveError as exc:
                self.errors.append(f"ArcLength reference-load solve failed: {exc}")
                return -10
            self._delta_u_hat = ls.x.copy()
            self._delta_u_hat_matrix_version = ls.matrix_version
            self._delta_u_hat_phat = self._phat.copy()
            self._delta_u_hat_phat_id = id(self._phat)

        hat = self._selected(self._delta_u_hat)
        bar = self._selected(self._delta_u_bar)
        step = self._selected(self._delta_u_step)

        a = self._alpha2 + float(np.dot(hat, hat))
        b = 2.0 * (
            self._alpha2 * self._delta_lambda_step
            + float(np.dot(hat, bar))
            + float(np.dot(step, hat))
        )
        c = 2.0 * float(np.dot(step, bar)) + float(np.dot(bar, bar))

        def is_zero(value: float) -> bool:
            return value == 0.0 if self.constraint_mode == "csharp" else abs(value) < 1e-30

        if is_zero(a):
            if is_zero(b):
                self.errors.append("ArcLength constraint has zero reference load and denominator")
                return -10
            delta_lambda = -c / b
        elif self.constraint_mode == "stable" and self._alpha2 == 0.0 and hat.size == 1:
            # In 1D cylindrical arc-length, the spherical constraint on a single
            # scalar coordinate is (s + delta_u)^2 = s^2.  Preserving the forward
            # predictor branch (s * (s + delta_u) > 0) uniquely requires
            # delta_u = 0, giving delta_lambda = -bar / hat.  Evaluating the
            # general quadratic formula here is analytically redundant and
            # catastrophically ill-conditioned when |bar| >> |s|.
            denominator = float(hat[0])
            if abs(denominator) < 1e-30:
                self.errors.append("ArcLength reference-load displacement is zero")
                return -10
            delta_lambda = -float(bar[0]) / denominator
        else:
            discriminant = b * b - 4.0 * a * c
            if discriminant < 0.0:
                # Same fallback as C#, with denominator checking and a coherent
                # direction choice.
                numerator = float(np.dot(step, bar))
                denominator = float(np.dot(step, hat)) + self._alpha2 * self._delta_lambda_step
                if is_zero(denominator):
                    self.errors.append("ArcLength linearized constraint denominator is zero")
                    return -10
                delta_lambda = -numerator / denominator
                if self._projected_control_indices is None and self._phat is not None:
                    if delta_lambda * float(np.dot(hat, self._selected(self._phat))) < 0.0:
                        delta_lambda *= -1.0
            else:
                root = float(np.sqrt(discriminant))
                dl1 = (-b + root) / (2.0 * a)
                dl2 = (-b - root) / (2.0 * a)
                directional = float(np.dot(hat, step))
                criterion1 = float(np.dot(step, step) + np.dot(bar, step) + dl1 * directional)
                delta_lambda = dl1 if criterion1 > 0.0 else dl2

        self._delta_u = self._delta_u_bar + delta_lambda * self._delta_u_hat
        self._last_delta_u = self._delta_u.copy()
        self._last_delta_lambda = float(delta_lambda)
        self._delta_u_step += self._delta_u
        self._delta_lambda_step += delta_lambda
        self._current_lambda += delta_lambda
        ls.set_x_vector(self._delta_u)
        if self.u is not None:
            self.u += self._delta_u
        ModelManager.update_domain(model, ls, self.state)
        self.update_ptarget(
            p, model, an, int(self.state.combination), self.iteration
        )
        self.apply_load_domain(model, delta_lambda)
        return 0

    def update_trial(
        self,
        model: Model,
        p: Program,
        an: Any,
        delta_eta: float,
        direction: np.ndarray,
    ) -> int:
        if abs(delta_eta) < 1e-30:
            return 0
        delta_u = delta_eta * direction
        delta_lambda = delta_eta * getattr(self, "_last_delta_lambda", 0.0)
        p.ls.set_x_vector(delta_u)
        if self.u is not None:
            self.u += delta_u
        ModelManager.update_domain(model, p.ls, self.state)
        self.apply_load_domain(model, delta_lambda)
        self._current_lambda += delta_lambda
        self._delta_lambda_step += delta_lambda
        if self._delta_u_step is not None:
            self._delta_u_step += delta_u
        self.update_ptarget(
            p, model, an, int(self.state.combination), self.iteration
        )
        return 0

    def revert_failed_step(self, model: Model, ls: LinearSystem) -> None:
        if self._step_snapshot is None:
            self.revert_to_last_commit(model, ls)
            return
        snapshot = self._step_snapshot
        if snapshot["fext"] is not None and ModelManager._fext is not None:
            ModelManager._fext[:] = snapshot["fext"]
        self.mult = snapshot["mult"]
        self._current_lambda = snapshot["lambda"]
        self._delta_lambda_step = snapshot["delta_lambda_step"]
        if snapshot["delta_u_step"] is not None and self._delta_u_step is not None:
            self._delta_u_step[:] = snapshot["delta_u_step"]
        self.revert_to_last_commit(model, ls)

    @staticmethod
    def cutback_step(an: Any) -> bool:
        """Reduce an opt-in failed-step radius while preserving all equations."""

        factor = float(getattr(an, "arc_length_cutback_factor", 0.5))
        radius = float(np.sqrt(abs(float(getattr(an, "dr2", 0.0)))))
        minimum = max(0.0, float(getattr(an, "arc_length_min_radius", 0.0)))
        if not 0.0 < factor < 1.0 or radius <= minimum or radius <= 0.0:
            return False
        reduced = max(minimum, factor * radius)
        if reduced >= radius:
            return False
        an.dr2 = reduced * reduced
        if bool(getattr(an, "is_max_arc_length_ray", False)):
            max_ray = float(np.float32(getattr(an, "max_arc_length_ray", 0.0)))
            if max_ray > 0.0:
                an.max_arc_length_ray = float(np.float32(max_ray * factor))
        return True

    def commit(
        self,
        model: Model,
        an: Any,
        disp: float,
        dof_max: int,
        has_domain_changed: list[bool],
    ) -> bool:
        del model, dof_max
        if self.u_committed is not None and self.u is not None:
            self.u_committed[:] = self.u

        previous_multiplier = self._lf_items[self._current_lf_item - 1][1]
        target_multiplier = self._lf_items[self._current_lf_item][1]
        increasing = target_multiplier - previous_multiplier > 0.0
        reached = disp >= self._target_displacement if increasing else disp <= self._target_displacement

        if reached and self._current_lf_item < len(self._lf_items) - 1:
            self._current_lf_item += 1
            has_domain_changed[0] = True
            reached = False

        if bool(getattr(an, "update_dr2", False)):
            desired = max(1.0, float(getattr(an, "desired_iterations", 5)))
            actual = max(1.0, float(self.iteration))
            self._arc_length2 *= (desired / actual) ** self._adapt_exponent

        if bool(getattr(an, "is_max_arc_length_ray", False)):
            max_radius = float(np.float32(getattr(an, "max_arc_length_ray", 1.0)))
            if self.constraint_mode == "csharp":
                self._arc_length2 = min(self._arc_length2, max_radius)
            elif max_radius > 0.0:
                self._arc_length2 = min(self._arc_length2, max_radius * max_radius)
        return reached

    def get_time(self) -> float:
        return float(self.step)


class ArcLengthLinear(ArcLength):
    """C# ``ArcLength1`` linearized arc-length corrector.

    ``ArcLengthLinear`` is not an alias for the quadratic ``ArcLength``
    corrector.  The C# factory selects ``ArcLength1`` and its update solves a
    linearized constraint using the current step displacement.  Keeping the
    distinct update is required both for HRX compatibility and for strategy
    selection near a turning point.
    """

    def update(self, model: Model, p: Program, an: Any) -> int:
        """Apply C# ``ArcLength1.Update`` exactly in the Python state model."""

        self.iteration += 1
        ls = p.ls
        self._delta_u_bar = ls.x.copy()
        if self._phat is None or self._delta_u_step is None:
            self.errors.append("ArcLengthLinear is not initialized")
            return -10

        # ArcLength1 explicitly resolves the reference load on every
        # correction.  Do not reuse the quadratic integrator's cache here:
        # the C# method overwrites LS.B with phat and calls Solve regardless
        # of whether the tangent has changed.
        try:
            ls.solve(rhs=self._phat)
        except LinearSolveError as exc:
            self.errors.append(f"ArcLengthLinear reference-load solve failed: {exc}")
            return -10
        self._delta_u_hat = ls.x.copy()
        self._delta_u_hat_matrix_version = ls.matrix_version
        self._delta_u_hat_phat = self._phat.copy()
        self._delta_u_hat_phat_id = id(self._phat)

        hat = self._selected(self._delta_u_hat)
        bar = self._selected(self._delta_u_bar)
        step = self._selected(self._delta_u_step)
        numerator = float(np.dot(step, bar))
        # MatrixManager.Vector.operator +(Vector, double) adds the scalar to
        # every selected component.  alpha2 is zero for the supplied static
        # HRX models, but retaining this expression preserves ArcLength1's
        # actual behavior for a nonzero alpha2 compatibility input.
        denominator = float(
            np.dot(step, hat + self._alpha2 * self._delta_lambda_step)
        )
        if abs(denominator) < 1.0e-30:
            self.errors.append(
                "ArcLengthLinear constraint has a zero reference-load denominator"
            )
            return -10
        delta_lambda = -numerator / denominator

        self._delta_u = self._delta_u_bar + delta_lambda * self._delta_u_hat
        self._last_delta_u = self._delta_u.copy()
        self._last_delta_lambda = float(delta_lambda)
        self._delta_u_step += self._delta_u
        self._delta_lambda_step += delta_lambda
        self._current_lambda += delta_lambda
        ls.set_x_vector(self._delta_u)
        if self.u is not None:
            self.u += self._delta_u
        ModelManager.update_domain(model, ls, self.state)
        self.update_ptarget(
            p, model, an, int(self.state.combination), self.iteration
        )
        self.apply_load_domain(model, delta_lambda)
        return 0
