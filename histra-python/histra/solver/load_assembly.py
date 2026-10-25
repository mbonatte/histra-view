"""Static load generation and global load-vector assembly.

This module follows the responsibilities of C# ``LoadTemplateManager`` and
the load-generation portion of ``ModelManager``.  Stiffness assembly remains
in :mod:`histra.solver.assembler`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from histra.model.model import Model

if TYPE_CHECKING:
    from histra.model.load import LoadCombinationItem, LoadCondition, LoadTemplateItem


_PSI_FIELDS = {
    "Psi0": "psi0",
    "Psi1": "psi1",
    "Psi2": "psi2",
}

_GAMMA_FIELDS = {
    "GammaFavSTR": "gamma_fav_str",
    "GammaUnfavSTR": "gamma_unfav_str",
    "GammaFavGEO": "gamma_fav_geo",
    "GammaUnfavGEO": "gamma_unfav_geo",
}

_GAMMA_PSI0_FIELDS = {
    "GammaFavSTR_Psi0": "gamma_fav_str",
    "GammaUnfavSTR_Psi0": "gamma_unfav_str",
    "GammaFavGEO_Psi0": "gamma_fav_geo",
    "GammaUnfavGEO_Psi0": "gamma_unfav_geo",
}

_GC_PRIMARY_TYPES = {
    "GC": "Number",
    "Psi0_GC": "Psi0",
    "Psi1_GC": "Psi1",
    "Psi2_GC": "Psi2",
    "GammaFavSTR_GC": "GammaFavSTR",
    "GammaUnfavSTR_GC": "GammaUnfavSTR",
    "GammaFavGEO_GC": "GammaFavGEO",
    "GammaUnfavGEO_GC": "GammaUnfavGEO",
    "GammaFavSTR_Psi0_GC": "GammaFavSTR_Psi0",
    "GammaUnfavSTR_Psi0_GC": "GammaUnfavSTR_Psi0",
    "GammaFavGEO_Psi0_GC": "GammaFavGEO_Psi0",
    "GammaUnfavGEO_Psi0_GC": "GammaUnfavGEO_Psi0",
}


def _coefficient_factor(
    type_data: str,
    condition: "LoadCondition",
    template_item: "LoadTemplateItem | None",
    *,
    number: float,
) -> float:
    """Evaluate one non-GC C# ``TypeDataEnum`` coefficient."""

    if type_data == "Number":
        return float(np.float32(number))
    gamma_field = _GAMMA_FIELDS.get(type_data)
    if gamma_field is not None:
        return float(np.float32(getattr(condition, gamma_field)))
    psi_field = _PSI_FIELDS.get(type_data)
    if psi_field is not None:
        if template_item is None:
            raise ValueError(f"{type_data} coefficient requires a load-template item")
        return float(np.float32(getattr(template_item, psi_field)))
    gamma_field = _GAMMA_PSI0_FIELDS.get(type_data)
    if gamma_field is not None:
        if template_item is None:
            raise ValueError(f"{type_data} coefficient requires a load-template item")
        return float(np.float32(getattr(condition, gamma_field)) * np.float32(template_item.psi0))
    raise NotImplementedError(f"Unsupported load-combination coefficient type: {type_data}")


def _resolve_coefficient(
    item: "LoadCombinationItem",
    condition: "LoadCondition",
    template_item: "LoadTemplateItem | None" = None,
) -> float:
    """Port C# ``LoadTemplateManager.GetCoefficient`` for one table item.

    ``*_GC`` values multiply their primary factor by ``SecondTypeData``.  The
    C# implementation contains one long-standing asymmetry: both
    ``GammaFavSTR_Psi1_GC`` and ``GammaUnfavSTR_Psi1_GC`` use
    ``GammaUnfavSTR``.  It is preserved deliberately for reference parity.
    """

    type_data = str(item.type_data)
    if type_data == "GammaFavSTR_Psi1_GC" or type_data == "GammaUnfavSTR_Psi1_GC":
        if template_item is None:
            raise ValueError(f"{type_data} coefficient requires a load-template item")
        primary = np.float32(condition.gamma_unfav_str) * np.float32(template_item.psi1)
        return float(np.float32(primary * np.float32(_coefficient_factor(
            str(item.secondary_type_data),
            condition,
            template_item,
            number=float(item.val),
        ))))

    primary_type = _GC_PRIMARY_TYPES.get(type_data)
    if primary_type is None:
        return _coefficient_factor(
            type_data,
            condition,
            template_item,
            number=float(item.val),
        )

    primary_number = 1.0 if type_data == "GC" else float(item.val)
    primary = _coefficient_factor(
        primary_type,
        condition,
        template_item,
        number=primary_number,
    )
    secondary = _coefficient_factor(
        str(item.secondary_type_data),
        condition,
        template_item,
        number=float(item.val),
    )
    return float(np.float32(primary) * np.float32(secondary))


def _get_comb_coeff_gravity(model: Model, analysis_key: int, combination: int) -> float:
    """Read the active self-weight coefficient from a load combination."""

    analysis = model.collections.analyses.get(analysis_key)
    if analysis is None:
        raise KeyError(f"Analysis {analysis_key} is not present in the model")
    if int(getattr(analysis, "analysis_type", 0)) == 5:
        return 0.0

    combination_table = model.collections.load_combinations.get(
        analysis.load_combination_key
    )
    if combination_table is None:
        raise KeyError(
            f"Load combination {analysis.load_combination_key} for analysis "
            f"{analysis_key} is missing"
        )

    gravity_condition = next(
        (
            condition
            for condition in model.collections.load_conditions.values()
            if condition.is_gravity()
        ),
        None,
    )
    if gravity_condition is None:
        raise NotImplementedError(
            f"Analysis {analysis_key} has no gravity load condition (Action == 1); "
            "non-gravity load generation is not implemented"
        )

    coefficient = combination_table.get_coefficient(
        combination, gravity_condition.id
    )
    if coefficient is None:
        raise KeyError(
            f"Load combination {combination_table.key} has no row {combination} "
            f"coefficient for gravity condition {gravity_condition.id}"
        )
    return _resolve_coefficient(coefficient, gravity_condition)


def _get_load_template_coefficient(
    model: Model,
    analysis_key: int,
    combination: int,
    load_condition_id: int,
    template_item: "LoadTemplateItem | None" = None,
) -> float:
    """Resolve one C# load-template coefficient from the active combination."""

    analysis = model.collections.analyses.get(analysis_key)
    if analysis is None:
        raise KeyError(f"Analysis {analysis_key} is not present in the model")
    combination_table = model.collections.load_combinations.get(
        analysis.load_combination_key
    )
    if combination_table is None:
        raise KeyError(
            f"Load combination {analysis.load_combination_key} for analysis "
            f"{analysis_key} is missing"
        )
    condition = model.collections.load_conditions.get(load_condition_id)
    if condition is None:
        raise KeyError(f"Load condition {load_condition_id} is missing")
    coefficient = combination_table.get_coefficient(combination, load_condition_id)
    if coefficient is None:
        # Empty cells in existing rows contribute zero without rewriting inputs.
        if any(item.row_key == combination for item in combination_table.items):
            return 0.0
        raise KeyError(
            f"Load combination {combination_table.key} has no row {combination} "
            f"coefficient for condition {load_condition_id}"
        )
    return _resolve_coefficient(coefficient, condition, template_item)


def generate_line_loads(model: Model, analysis_key: int, combination: int = 1) -> None:
    """Generate direct Quad line loads along the active C# call chain."""

    analysis = model.collections.analyses.get(analysis_key)
    if analysis is None:
        raise KeyError(f"Analysis {analysis_key} is not present in the model")

    for load in model.collections.line_loads.values():
        if load.element_type != "Quad":
            raise NotImplementedError(
                f"LineLoadElement {load.key} targets unsupported element type "
                f"{load.element_type!r}"
            )
        quad = model.collections.quads.get(load.element_key)
        if quad is None:
            raise KeyError(
                f"LineLoadElement {load.key} references missing Quad {load.element_key}"
            )
        template = model.collections.load_templates.get(load.load_template_key)
        if template is None:
            raise KeyError(
                f"LineLoadElement {load.key} references missing template "
                f"{load.load_template_key}"
            )
        if template.purpose_type != "LineLoad":
            raise ValueError(
                f"Load template {template.key} has purpose {template.purpose_type!r}, "
                "expected 'LineLoad'"
            )

        endpoint = np.zeros(3, dtype=np.float32)
        for item in template.items:
            if item.load_type != "Force":
                raise NotImplementedError(
                    f"Line-load template item {item.key} has unsupported type "
                    f"{item.load_type!r}"
                )
            coefficient = np.float32(
                _get_load_template_coefficient(
                    model, analysis_key, combination, item.load_condition_id, item
                )
            )
            modal = int(analysis.analysis_type) == 5
            # HiStrA's GenerateLoadsForceAnalysis overrides modal directions
            # to (1, 1, 1), irrespective of the saved IsSeismic/Dir fields.
            direction = np.asarray(
                (1.0, 1.0, 1.0) if modal else (
                    (analysis.dir_x, analysis.dir_y, analysis.dir_z)
                    if bool(analysis.is_seismic) else item.direction_for(quad)
                ),
                dtype=np.float32,
            )
            value = np.float32(item.load_value)
            scaled_value = np.float32(coefficient * value)
            force = np.multiply(scaled_value, direction, dtype=np.float32)
            if modal:
                condition = model.collections.load_conditions[item.load_condition_id]
                # Original LoadTemplateManager.ComputeMassNodalForce applies
                # each Single mass participation factor before summation.
                force *= np.asarray(
                    (condition.mass_in_dir_x, condition.mass_in_dir_y,
                     condition.mass_in_dir_z), dtype=np.float32,
                )
            endpoint += force

        if not np.any(endpoint):
            continue
        nodes = []
        for node_key in quad.node_keys:
            node = model.collections.nodes.get(node_key)
            if node is None:
                raise KeyError(
                    f"Quad {quad.key} line-load integration references missing Node "
                    f"{node_key}"
                )
            nodes.append(node.point)
        local_load = quad.compute_line_load_internal(
            nodes,
            load.points,
            (tuple(float(x) for x in endpoint), tuple(float(x) for x in endpoint)),
            node_tolerance=float(model.geometry_tolerance_node),
        )
        for index in range(7):
            quad.status.p[index] += local_load[index]


def generate_self_weight_loads(
    model: Model, analysis_key: int, combination: int = 1
) -> None:
    """Generate each Quad's seven generalized self-weight loads."""

    analysis = model.collections.analyses.get(analysis_key)
    if analysis is None:
        raise KeyError(f"Analysis {analysis_key} is not present in the model")

    coefficient = _get_comb_coeff_gravity(model, analysis_key, combination)
    if abs(coefficient) < 1.0e-30:
        return

    direction = (
        (float(analysis.dir_x), float(analysis.dir_y), float(analysis.dir_z))
        if analysis.is_seismic
        else (0.0, 0.0, -1.0)
    )
    # ModelLoadOperations scales an XNA Vector3 by a Single coefficient.
    # Round the components before multiplication as well as its result.
    dx, dy, dz = np.asarray(direction, dtype=np.float32) * np.float32(coefficient)

    for quad in model.collections.quads.values():
        for index in range(7):
            quad.status.p[index] = 0.0
        material = model.collections.materials.get(quad.material_key)
        if material is None or abs(material.w) < 1.0e-30:
            continue
        node_coordinates = []
        for node_key in quad.node_keys:
            node = model.collections.nodes.get(node_key)
            if node is None:
                break
            node_coordinates.append(node.point)
        if len(node_coordinates) != 4:
            continue
        nodal_forces = quad.compute_self_weight_load(dx, dy, dz, material.w)
        local_load = quad.compute_static_load_internal(node_coordinates, nodal_forces)
        for index in range(7):
            quad.status.p[index] += local_load[index]


def assemble_load_vector(
    model: Model,
    analysis_key: int | None = None,
    combination: int = 1,
) -> np.ndarray:
    """Assemble the active global load vector."""

    if analysis_key is not None:
        for quad in model.collections.quads.values():
            for index in range(7):
                quad.status.p[index] = 0.0
        generate_self_weight_loads(model, analysis_key, combination)
        generate_line_loads(model, analysis_key, combination)

    vector = np.zeros(model.gdl)
    for quad in model.collections.quads.values():
        for local_dof in range(7):
            value = quad.status.p[local_dof] if local_dof < len(quad.status.p) else 0.0
            if abs(value) < 1.0e-30 or local_dof >= len(quad.aff):
                continue
            for entry in quad.aff[local_dof]:
                global_dof = entry.gdl - 1
                if 0 <= global_dof < model.gdl:
                    vector[global_dof] += value * entry.alfa
    return vector


def extract_displacements(
    model: Model,
    results_path: str | None = None,
    analysis_key: int = 1,
    combination: int = 1,
    step: int | None = None,
) -> np.ndarray:
    """Extract the full active displacement vector from SQLite or model state."""

    displacement = np.zeros(model.gdl)
    if results_path is not None:
        from histra.io.results_reader import read_quad_states

        quad_states = read_quad_states(
            results_path, analysis_key, combination, step
        )
        for quad_key, quad_state in quad_states.items():
            quad = model.collections.quads.get(quad_key)
            if quad is None:
                continue
            local = quad_state.u if hasattr(quad_state, "u") else quad_state
            for local_dof in range(7):
                if local_dof < len(quad.aff) and quad.aff[local_dof]:
                    global_dof = quad.aff[local_dof][0].gdl - 1
                    if 0 <= global_dof < model.gdl:
                        displacement[global_dof] = local[local_dof]
        return displacement

    for quad in model.collections.quads.values():
        for local_dof in range(7):
            if local_dof < len(quad.aff) and quad.aff[local_dof]:
                global_dof = quad.aff[local_dof][0].gdl - 1
                if 0 <= global_dof < model.gdl:
                    displacement[global_dof] = (
                        quad.status.u[local_dof]
                        if local_dof < len(quad.status.u)
                        else 0.0
                    )
    return displacement
