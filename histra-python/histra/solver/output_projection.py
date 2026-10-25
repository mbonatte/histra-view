"""Backend-facing projection of in-memory solver results.

The displacement rows intentionally reproduce the subset selected by
``histra-job-runner`` from C# ``DisplModelPoints``:
``IdElement``, ``ParentKey``, ``Step``, ``Ux``, ``Uy`` and ``Uz``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np

from histra.postprocessing import _average_node_displacements, quad_node_displacement
from histra.solver.outcomes import AnalysisExecution, AnalysisStep


class OutputProjectionError(RuntimeError):
    """Raised when requested output cannot be projected from an execution."""


class UnsupportedOutputError(OutputProjectionError):
    """Raised when the Python solver does not implement an output family."""


@dataclass(frozen=True)
class ModelPointDisplacement:
    id_element: int
    parent_key: int
    step: int
    ux: float
    uy: float
    uz: float

    def as_runner_dict(self) -> dict[str, float | int]:
        return {
            "IdElement": self.id_element,
            "ParentKey": self.parent_key,
            "Step": self.step,
            "Ux": self.ux,
            "Uy": self.uy,
            "Uz": self.uz,
        }


def project_reactions(execution: AnalysisExecution, request: Any) -> list[dict[str, Any]]:
    """Project reactions using the Job Runner's ``ReactionSumStates`` shape.

    Extracts base reaction sums (R1, R2, R3) across selected committed solver
    steps matching the C# ``ReactionSumStates`` schema.

    Parameters
    ----------
    execution : AnalysisExecution
        Execution record containing committed analysis steps and reactions.
    request : Any
        Request specification with optional ``all_steps`` or ``step`` filters.

    Returns
    -------
    list[dict[str, Any]]
        List of dictionaries with keys ``Step``, ``R1``, ``R2``, and ``R3``.

    Raises
    ------
    OutputProjectionError
        If an expected reaction component is missing from a committed step.
    """
    selected = _select_steps(execution.output_steps, request)
    rows: list[dict[str, Any]] = []
    for step in selected:
        if step.reaction_x is None or step.reaction_y is None or step.reaction_z is None:
            raise OutputProjectionError(
                f"Analysis {execution.analysis_name!r} step {step.step} has no committed reaction."
            )
        rows.append(
            {
                "Step": int(step.step),
                "R1": float(step.reaction_x),
                "R2": float(step.reaction_y),
                "R3": float(step.reaction_z),
            }
        )
    return rows


def model_point_displacement(
    collections: Any,
    point: Any,
    u: Sequence[float] | np.ndarray,
) -> np.ndarray:
    """Return the global X/Y/Z displacement of one HRX model point.

    Port of the element switch in C# ``ModelPointOperations.AddStateModelPoints``
    for the supported element subset (Node and Quad model points).
    """
    element_key = int(point.element_key)
    element_type = str(point.element_type).casefold().split(".")[-1]
    if element_type == "node":
        try:
            node = collections.nodes[element_key]
        except KeyError as exc:
            raise OutputProjectionError(
                f"ModelPoint {point.key} references missing Node {element_key}."
            ) from exc
        contributions = [
            quad_node_displacement(quad, node.point, index, u)
            for quad in collections.quads.values()
            for index, node_key in enumerate(quad.node_keys)
            if int(node_key) == element_key
        ]
        if not contributions:
            raise UnsupportedOutputError(
                f"Node ModelPoint {point.key} references Node {element_key}, which "
                "has no supported Quad contribution."
            )
        return _average_node_displacements(contributions)
    if element_type == "quad":
        try:
            quad = collections.quads[element_key]
        except KeyError as exc:
            raise OutputProjectionError(
                f"ModelPoint {point.key} references missing Quad {element_key}."
            ) from exc
        vertex = int(point.id_vertex)
        if vertex == 0:
            # C# ModelPointOperations uses Quad.Status.U[0..2] at the centre.
            return np.asarray(
                [
                    sum(
                        float(u[entry.gdl - 1]) * float(entry.alfa)
                        for entry in quad.aff[local_dof]
                        if 0 <= entry.gdl - 1 < len(u)
                    )
                    for local_dof in range(3)
                ],
                dtype=float,
            )
        if 1 <= vertex <= len(quad.node_keys):
            node_key = int(quad.node_keys[vertex - 1])
            try:
                node = collections.nodes[node_key]
            except KeyError as exc:
                raise OutputProjectionError(
                    f"Quad {element_key} vertex {vertex} references missing Node {node_key}."
                ) from exc
            return quad_node_displacement(quad, node.point, vertex - 1, u)
        raise UnsupportedOutputError(
            f"ModelPoint {point.key} has unsupported IdVertex={vertex}."
        )
    raise UnsupportedOutputError(
        f"ModelPoint {point.key} uses unsupported element type {point.element_type!r}."
    )


def compute_model_point_displacements(
    model: Any,
    global_displacement: Sequence[float] | np.ndarray,
    *,
    step: int,
    model_point_ids: Sequence[int] = (),
) -> tuple[ModelPointDisplacement, ...]:
    """Compute C#-compatible displacement rows for the supported model subset.

    ``model_point_ids`` follows the existing runner contract and therefore
    filters by C# ``IdElement`` (the HRX ``ModelPoint.ElementKey``), not by the
    ModelPoint's own key.
    """
    collections = getattr(model, "collections", None)
    if collections is None:
        raise OutputProjectionError("Model.collections is not initialized.")
    u = np.asarray(global_displacement, dtype=float)
    if u.ndim != 1 or u.size != int(model.gdl):
        raise OutputProjectionError(
            f"Expected displacement vector length {model.gdl}; received shape {u.shape}."
        )

    requested_elements = {int(value) for value in model_point_ids}
    rows: list[ModelPointDisplacement] = []
    for point in sorted(
        collections.model_points.values(),
        key=lambda item: (int(item.element_key), int(item.key)),
    ):
        element_key = int(point.element_key)
        if requested_elements and element_key not in requested_elements:
            continue
        displacement = model_point_displacement(collections, point, u)
        rows.append(
            ModelPointDisplacement(
                id_element=element_key,
                parent_key=int(point.key),
                step=int(step),
                ux=float(displacement[0]),
                uy=float(displacement[1]),
                uz=float(displacement[2]),
            )
        )
    return tuple(rows)


def project_displacements(
    model: Any,
    execution: AnalysisExecution,
    request: Any,
) -> list[dict[str, float | int]]:
    """Project model point displacements into C# ``DisplModelPoints`` rows.

    Interpolates global displacement vectors to HRX model points (nodes and quad
    centers/vertices), returning ordered records formatted for the Job Runner.

    Parameters
    ----------
    model : Model
        Structural model containing nodes, quads, and model points.
    execution : AnalysisExecution
        Execution record containing committed analysis steps with displacement vectors.
    request : Any
        Request specification with optional ``model_point_ids``, ``all_steps``, or
        ``step`` filters.

    Returns
    -------
    list[dict[str, float | int]]
        List of dictionaries with keys ``IdElement``, ``ParentKey``, ``Step``,
        ``Ux``, ``Uy``, and ``Uz``.
    """
    selected = _select_steps(execution.output_steps, request)
    ids = tuple(int(value) for value in getattr(request, "model_point_ids", ()) or ())
    rows: list[ModelPointDisplacement] = []
    for step in selected:
        rows.extend(
            compute_model_point_displacements(
                model,
                step.u,
                step=step.step,
                model_point_ids=ids,
            )
        )
    # Match Job Runner's C# SQL ORDER BY IdElement, Step. ParentKey provides a
    # stable tie-break for multiple model points on the same element.
    rows.sort(key=lambda row: (row.id_element, row.step, row.parent_key))
    return [row.as_runner_dict() for row in rows]


def project_analysis_outputs(
    model: Any,
    execution: AnalysisExecution,
    request: Any,
) -> dict[str, Any]:
    """Project supported outputs without depending on Job Runner classes.

    Extracts displacements, reactions, and modal analysis outcomes requested by
    a backend execution request.

    Parameters
    ----------
    model : Model
        Structural model containing elements and collections.
    execution : AnalysisExecution
        Execution record containing step history and modal outcomes.
    request : Any
        Request container specifying which output families (displacements, reactions,
        modal_shapes) are enabled.

    Returns
    -------
    dict[str, Any]
        Dictionary with enabled keys such as ``modal_analysis``, ``displacements``,
        and ``reactions``.

    Raises
    ------
    UnsupportedOutputError
        If an unsupported output family (such as response-spectrum modal contributions)
        is requested.
    """
    result: dict[str, Any] = {}

    if execution.modal_result is not None:
        result["modal_analysis"] = execution.modal_result.as_dict(
            include_shapes=bool(getattr(request, "include_modal_shapes", False))
        )

    displacements = getattr(request, "displacements", None)
    if displacements is not None and bool(getattr(displacements, "enabled", False)):
        result["displacements"] = project_displacements(model, execution, displacements)

    reactions = getattr(request, "reactions", None)
    if reactions is not None and bool(getattr(reactions, "enabled", False)):
        result["reactions"] = project_reactions(execution, reactions)

    modal = getattr(request, "modal_contributions", None)
    if modal is not None and bool(getattr(modal, "enabled", False)):
        raise UnsupportedOutputError(
            "Response-spectrum modal contribution projection is not supported. "
            "Modal eigenanalysis summaries are returned under 'modal_analysis'."
        )

    return result


def _select_steps(
    available: Iterable[AnalysisStep],
    request: Any,
) -> tuple[AnalysisStep, ...]:
    steps = tuple(available)
    if not steps:
        raise OutputProjectionError("The analysis has no committed output steps.")
    if bool(getattr(request, "all_steps", False)):
        return steps
    requested_step = getattr(request, "step", None)
    if requested_step is not None:
        target = int(requested_step)
        selected = tuple(step for step in steps if step.step == target)
        if not selected:
            available_steps = ", ".join(str(step.step) for step in steps)
            raise OutputProjectionError(
                f"Requested step {target} is unavailable; available steps: {available_steps}."
            )
        return selected
    return (steps[-1],)
