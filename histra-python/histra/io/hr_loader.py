"""HiStrA HRX loader.

The C# model stores load-function definitions and their points as separate
top-level entities.  This loader preserves that relationship and attaches
``LoadFunctionItem`` objects after the streaming parse is complete.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Union

import numpy as np

from histra.model.interface import Interface
from histra.model.load import (
    Analysis,
    LoadCombination,
    LoadCombinationItem,
    LoadCondition,
    LoadFunction,
    LoadFunctionItem,
    LoadTemplate,
    LoadTemplateItem,
    LineLoadElement,
    ModelPoint,
)
from histra.model.masonry_material import MasonryMaterial
from histra.model.model import Collections, Model
from histra.model.node import Node, NodeC
from histra.model.quad import Quad
from histra.model.restraint import Restraint


_CONSUMED_TAGS = frozenset(
    {
        "Node",
        "NodeC",
        "Quad",
        "Interface",
        "Restraint",
        "LoadCombination",
        "LoadCondition",
        "LoadFunction",
        "LoadFunctionItem",
        "Template",
        "Analysis",
        "AdvancedOptionsDefault",
        "AdvancedOptions",
    }
)

_UNSUPPORTED_V1_ELEMENT_TAGS = frozenset(
    {
        "Frame",
        "Slab",
        "Link",
        "Joint",
        "Solid",
        "Fiber",
        "Truss",
        "Vertex",
        "InterfaceMF",
        "NodeBC",
    }
)


def _record_unsupported(model: Model, category: str, value: str) -> None:
    key = f"{category}:{value}"
    model.unsupported_v1_features[key] = model.unsupported_v1_features.get(key, 0) + 1


def _parse_model_root(elem: ET.Element, model: Model) -> None:
    model.version = _attr(elem, "version", "Version", default="")
    model.gdl = _safe_int(_attr(elem, "GDL", "gdl", default="0"))
    model.wizard_type = _attr(elem, "WizardType", default="")
    model.is_locked = _safe_bool(_attr(elem, "IsLocked", default="false"))


def _parse_advanced_options(elem: ET.Element, model: Model) -> None:
    model.geometry_tolerance_node = float(np.float32(_safe_float(
        _attr(elem, "ToleranceNode", default=str(model.geometry_tolerance_node)),
        model.geometry_tolerance_node,
    )))
    model.geometry_tolerance_plane = float(np.float32(_safe_float(
        _attr(elem, "TolerancePlane", default=str(model.geometry_tolerance_plane)),
        model.geometry_tolerance_plane,
    )))
    model.interface_nrow = _safe_int(
        _attr(elem, "InterfaceNrow", default=str(model.interface_nrow)),
        model.interface_nrow,
    )
    model.interface_imax = _safe_float(
        _attr(elem, "InterfaceImax", default=str(model.interface_imax)),
        model.interface_imax,
    )
    model.mass_matrix_type = _attr(
        elem,
        "MassMatrixType",
        default=model.mass_matrix_type,
    )


def _parse_load_condition(elem: ET.Element) -> LoadCondition:
    return LoadCondition(
        id=_safe_int(_attr(elem, "Id", "id", default="0")),
        name=_attr(elem, "Name", "name", default=""),
        description=_attr(elem, "Description", default=""),
        mass_in_dir_x=_safe_float(_attr(elem, "MassInDirX", default="1"), 1.0),
        mass_in_dir_y=_safe_float(_attr(elem, "MassInDirY", default="1"), 1.0),
        mass_in_dir_z=_safe_float(_attr(elem, "MassInDirZ", default="1"), 1.0),
        is_main_load=_safe_bool(_attr(elem, "isMainLoad", "IsMainLoad", default="false")),
        is_favourable=_safe_bool(_attr(elem, "isFavourable", "IsFavourable", default="false")),
        is_un_favourable=_safe_bool(_attr(elem, "isUnFavourable", "IsUnFavourable", default="true")),
        gamma_fav_str=_safe_float(_attr(elem, "GammaFavSTR", default="1"), 1.0),
        gamma_unfav_str=_safe_float(_attr(elem, "GammaUnfavSTR", default="1"), 1.0),
        gamma_fav_geo=_safe_float(_attr(elem, "GammaFavGEO", default="1"), 1.0),
        gamma_unfav_geo=_safe_float(_attr(elem, "GammaUnfavGEO", default="1"), 1.0),
        action=_safe_int(_attr(elem, "Action", default="0")),
    )


def _parse_load_function(elem: ET.Element) -> LoadFunction:
    return LoadFunction(
        key=_safe_int(_attr(elem, "Key", "key", default="0")),
        name=_attr(elem, "Name", "name", default=""),
        type_discr=_safe_bool(_attr(elem, "typeDiscr", "TypeDiscr", default="false")),
        discr_val=_safe_float(_attr(elem, "DiscrVal", "discrVal", default="0.1"), 0.1),
    )


def _parse_load_function_item(elem: ET.Element) -> LoadFunctionItem:
    return LoadFunctionItem(
        key=_safe_int(_attr(elem, "Key", "key", default="0")),
        load_function_key=_safe_int(_attr(elem, "LoadFunctionKey", "loadFunctionKey", default="0")),
        pseudo_time=_safe_float(_attr(elem, "PseudoTime", "pseudoTime", default="0")),
        multiplier=_safe_float(_attr(elem, "Multiplier", "multiplier", default="0")),
    )


def _parse_load_template_item(elem: ET.Element) -> LoadTemplateItem:
    return LoadTemplateItem(
        key=_safe_int(_attr(elem, "Key", default="0")),
        id=_safe_int(_attr(elem, "Id", default="0")),
        load_template_key=_safe_int(_attr(elem, "IdLoadTemplate", default="0")),
        load_condition_id=_safe_int(_attr(elem, "IdLoadCondition", default="0")),
        load_value=_safe_float(_attr(elem, "LoadValue", default="0")),
        dir_x=_safe_float(_attr(elem, "DirX", default="0")),
        dir_y=_safe_float(_attr(elem, "DirY", default="0")),
        dir_z=_safe_float(_attr(elem, "DirZ", default="0")),
        psi0=_safe_float(_attr(elem, "Psi0", default="0")),
        psi1=_safe_float(_attr(elem, "Psi1", default="0")),
        psi2=_safe_float(_attr(elem, "Psi2", default="0")),
        is_projected=_safe_bool(_attr(elem, "IsProjected", default="false")),
        load_type=_attr(elem, "IdTypeLoad", default="Force"),
        load_direction=_safe_int(_attr(elem, "IdLoadDirection", default="0")),
    )


def _parse_line_load_element(elem: ET.Element) -> LineLoadElement:
    type_of = _attr(elem, "TypeOf", "typeof", default="")
    if type_of.endswith("LineLoadElement"):
        return LineLoadElement(
            key=_safe_int(_attr(elem, "Key", default="0")),
            parent_key=_safe_int(_attr(elem, "ParentKey", default="0")),
            element_key=_safe_int(_attr(elem, "ElementKey", default="0")),
            element_type=_attr(elem, "ElementType", default=""),
            load_template_key=_safe_int(_attr(elem, "IdLoadTemplate", default="0")),
            point1=_parse_xyz(_attr(elem, "Point1", default="0;0;0")),
            point2=_parse_xyz(_attr(elem, "Point2", default="0;0;0")),
        )
    raise NotImplementedError(
        f"Unsupported HRX load element type: {type_of or "<missing>"}"
    )


def _parse_model_point(elem: ET.Element) -> ModelPoint:
    return ModelPoint(
        key=_safe_int(_attr(elem, "Key", default="0")),
        element_key=_safe_int(_attr(elem, "ElementKey", "IdElement", default="0")),
        element_type=_attr(elem, "ElementType", default=""),
        id_vertex=_safe_int(_attr(elem, "IdVertex", default="0")),
    )


def _parse_template(elem: ET.Element, model: Model, collections: Collections) -> None:
    purpose_type = _attr(elem, "PurposeType", default="")
    if purpose_type in {"AreaLoad", "LineLoad", "PointLoad"}:
        template = LoadTemplate(
            key=_safe_int(_attr(elem, "Key", default="0")),
            name=_attr(elem, "Name", default=""),
            purpose_type=purpose_type,
            dynamic_coefficient=_safe_float(
                _attr(elem, "DynamicCoefficient", default="1"), 1.0
            ),
        )
        collections.load_templates[template.key] = template
    elif purpose_type == "MasonryMaterial":
        material = MasonryMaterial(
            key=_safe_int(_attr(elem, "Key", default="0")),
            name=_attr(elem, "Name", default=""),
            w=_safe_float(_attr(elem, "w", default="0")),
            E_min=_safe_float(_attr(elem, "E_min", default="0")),
            E_med=_safe_float(_attr(elem, "E_med", default="0")),
            E_max=_safe_float(_attr(elem, "E_max", default="0")),
            G_min=_safe_float(_attr(elem, "G_min", default="0")),
            G_med=_safe_float(_attr(elem, "G_med", default="0")),
            G_max=_safe_float(_attr(elem, "G_max", default="0")),
            fm_min=_safe_float(_attr(elem, "fm_min", default="0")),
            fm_med=_safe_float(_attr(elem, "fm_med", default="0")),
            fm_max=_safe_float(_attr(elem, "fm_max", default="0")),
            fvk0_min=_safe_float(_attr(elem, "fvk0_min", default="0")),
            fvk0_med=_safe_float(_attr(elem, "fvk0_med", default="0")),
            fvk0_max=_safe_float(_attr(elem, "fvk0_max", default="0")),
            properties=dict(elem.attrib),
        )
        collections.materials[material.key] = material
    elif purpose_type.endswith("Material"):
        template_key = _safe_int(_attr(elem, "Key", default="0"))
        model.unsupported_material_templates[template_key] = purpose_type


def _parse_analysis(elem: ET.Element) -> Analysis:
    return Analysis(
        key=_safe_int(_attr(elem, "Key", default="0")),
        name=_attr(elem, "Name", default=""),
        analysis_type=_safe_int(_attr(elem, "AnalysisType", default="0")),
        load_combination_key=_safe_int(_attr(elem, "LoadCombinationKey", default="0")),
        load_function_key=_safe_int(_attr(elem, "LoadFunctionKey", default="0")),
        initial_analysis_key=_safe_int(_attr(elem, "InitialAnalysisKey", default="-100"), -100),
        initial_combination_analysis_key=_safe_int(_attr(elem, "InitialCombinationAnalysisKey", default="1"), 1),
        dir_x=_safe_float(_attr(elem, "DirX", default="0")),
        dir_y=_safe_float(_attr(elem, "DirY", default="0")),
        dir_z=_safe_float(_attr(elem, "DirZ", default="-1"), -1.0),
        is_seismic=_safe_bool(_attr(elem, "IsSeismic", default="false")),
        mult=_safe_float(_attr(elem, "Mult", default="1"), 1.0),
        type_load_distribution=_attr(elem, "TypeLoadDistribution", default="LoadCombination"),
        force_imposed=_safe_bool(_attr(elem, "ForceImposed", default="true")),
        force_control=_safe_bool(_attr(elem, "ForceControl", default="true")),
        integration_method=_attr(elem, "IntegrationMethod", default="LoadControl"),
        method=_attr(elem, "Method", default="StandardNewtonRaphson"),
        adaptive_convergence_criteria=_attr(elem, "AdapticConvergenceCriteria", default="ForceMoment"),
        convergence_tolerance=_safe_float(_attr(elem, "ConvergenceTolerance", default="0.0001"), 1.0e-4),
        max_iterations=_safe_int(_attr(elem, "MaxIterations", default="1000"), 1000),
        max_u=_safe_float(_attr(elem, "maxU", "MaxU", default="100"), 100.0),
        number_of_eigen_modes=_safe_int(_attr(elem, "NumberOfEigenModes", default="1"), 1),
        number_of_lanczos_eigen_vectors=_safe_int(_attr(elem, "NumberOfLanczosEigenVectors", default="3"), 3),
        modal_procedure=_attr(elem, "ModalProcedure", default="InverseIterations"),
        residual_vector_tolerance=_safe_float(_attr(elem, "ResidualVectorTolerance", default="0.5"), 0.5),
        modal_convergence_criteria=_attr(elem, "ModalConvergenceCriteria", default="Frquency"),
        pdelta_effect=_attr(elem, "PdeltaEffect", default="None"),
        als=_safe_bool(_attr(elem, "ALS", default="false")),
        max_number_als=_safe_int(_attr(elem, "MaxNumberALS", default="10"), 10),
        load_factor_als=_safe_int(_attr(elem, "LoadFactorALS", default="2"), 2),
        master_point=_safe_int(_attr(elem, "MasterPoint", default="-10"), -10),
        target_displacement=_safe_float(_attr(elem, "TargetDisplacement", default="0")),
        dr2=_safe_float(_attr(elem, "Dr2", "DR2", default="0.0001"), 1.0e-4),
        arc_length_procedure=_attr(elem, "ArcLengthProcedure", default="OnlyControlPoint"),
        update_dr2=_safe_bool(_attr(elem, "UpdateDr2", default="false")),
        desired_iterations=_safe_int(_attr(elem, "DesiredIterations", default="5"), 5),
        is_max_arc_length_ray=_safe_bool(_attr(elem, "IsMaxArcLengthRay", default="false")),
        max_arc_length_ray=_safe_float(_attr(elem, "MaxArcLengthRay", default="1"), 1.0),
        line_search_tolerance=_safe_float(_attr(elem, "LineSearchTolerance", default="0.8"), 0.8),
        line_search_max_iterations=_safe_int(_attr(elem, "LineSearchMaxIterations", default="1000"), 1000),
        line_search_max_eta=_safe_float(_attr(elem, "LineSearchMaxEta", default="10"), 10.0),
        line_search_min_eta=_safe_float(_attr(elem, "LineSearchMinEta", default="0.1"), 0.1),
        load_reduction_ratio_to_stop=_safe_bool(_attr(elem, "LoadReductionRatioToStop", default="false")),
        load_reduction_ratio_to_stop_value=_safe_float(_attr(elem, "LoadReductionRatioToStopValue", default="0.1"), 0.1),
        check_secant_stiffness=_safe_bool(_attr(elem, "CheckSecantStiffness", default="false")),
        secant_stiffness_ratio=_safe_float(_attr(elem, "SecantStiffnessRatio", default="0")),
        step_save=_safe_int(_attr(elem, "StepSave", default="1")),
        active_model_points={
            _safe_int(_attr(child, "Key", default="0")): _safe_bool(_attr(child, "Value", default="false"))
            for child in elem.findall("./ActiveModelPoints/ActiveModelPoint")
        },
    )


def load_model(path: Union[str, Path]) -> Model:
    """Load a HiStrA ``.hrx`` model file into an in-process Python ``Model``.

    Parses XML geometry, materials, analyses, load functions, and boundary conditions.
    The returned model retains its source HRX path for differential auditing. Serialized
    computational springs in the HRX are reference snapshots from past C# runs; solvers
    will freshly prepare the mesh and topology via ``prepare_model`` before solving.

    Parameters
    ----------
    path : str or Path
        Filesystem path to the input ``.hrx`` XML model file.

    Returns
    -------
    Model
        The parsed domain model entity containing collections of nodes, quads,
        interfaces, materials, loads, and analysis definitions.

    Examples
    --------
    >>> from histra import load_model
    >>> model = load_model("path/to/structure.hrx")
    >>> len(model.collections.quads) > 0
    True
    """

    source_path = Path(path).resolve()
    model = Model(source_path=str(source_path))
    collections = Collections()
    load_function_items: list[LoadFunctionItem] = []
    load_template_items: list[LoadTemplateItem] = []

    context = ET.iterparse(str(source_path), events=("end",))

    for _event, elem in context:
        tag = elem.tag

        if tag == "HiStrA":
            _parse_model_root(elem, model)
            elem.clear()

        elif tag in {"AdvancedOptionsDefault", "AdvancedOptions"}:
            _parse_advanced_options(elem, model)
            elem.clear()

        elif tag == "Node":
            node = Node.from_xml(elem)
            collections.nodes[node.key] = node
            elem.clear()

        elif tag == "NodeC":
            node_c = NodeC.from_xml(elem)
            collections.node_c[node_c.key] = node_c
            elem.clear()

        elif tag == "Quad":
            quad = Quad.from_xml(elem)
            collections.quads[quad.key] = quad
            elem.clear()

        elif tag == "Interface":
            # Nested references inside a Quad have no Key and must stay attached
            # until the parent Quad is parsed.
            if elem.get("Key") is None:
                continue
            interface = Interface.from_xml(elem)
            collections.interfaces[interface.key] = interface
            elem.clear()

        elif tag == "Restraint":
            restraint = Restraint.from_xml(elem)
            collections.restraints[restraint.key] = restraint
            elem.clear()

        elif tag in _UNSUPPORTED_V1_ELEMENT_TAGS:
            _record_unsupported(model, "element", tag)
            elem.clear()

        elif tag == "LoadCombination":
            combination = _parse_load_combination(elem)
            collections.load_combinations[combination.key] = combination
            elem.clear()

        elif tag == "LoadCondition":
            condition = _parse_load_condition(elem)
            collections.load_conditions[condition.id] = condition
            elem.clear()

        elif tag == "LoadFunction":
            function = _parse_load_function(elem)
            collections.load_functions[function.key] = function
            elem.clear()

        elif tag == "LoadFunctionItem":
            load_function_items.append(_parse_load_function_item(elem))
            elem.clear()

        elif tag == "LoadTemplateItem":
            load_template_items.append(_parse_load_template_item(elem))
            elem.clear()

        elif tag == "LoadElement":
            line_load = _parse_line_load_element(elem)
            collections.line_loads[line_load.key] = line_load
            elem.clear()

        elif tag == "ModelPoint":
            model_point = _parse_model_point(elem)
            collections.model_points[model_point.key] = model_point
            elem.clear()

        elif tag == "Template":
            _parse_template(elem, model, collections)
            elem.clear()

        elif tag == "Analysis":
            analysis = _parse_analysis(elem)
            collections.analyses[analysis.key] = analysis
            elem.clear()

    # Attach the separate C# LoadFunctionItem collection to each function.
    for item in load_function_items:
        function = collections.load_functions.get(item.load_function_key)
        if function is not None:
            function.items.append(item)
    for function in collections.load_functions.values():
        function.items.sort(key=lambda item: (item.pseudo_time, item.key))

    for item in load_template_items:
        template = collections.load_templates.get(item.load_template_key)
        if template is not None:
            template.items.append(item)
    for template in collections.load_templates.values():
        template.items.sort(key=lambda item: (item.id, item.key))

    for analysis in collections.analyses.values():
        analysis.load_function = collections.load_functions.get(
            analysis.load_function_key
        )

    model.collections = collections

    # A saved locked HRX contains C#-generated computational objects.  Keep
    # them available to a comparison reader, but prevent a Python solve from
    # treating them as a prepared Python model.  Python preparation clears
    # this marker after recreating interfaces, afference and springs.
    model.requires_python_preparation = True

    # HRX files normally contain the active generalized-DOF count and saved
    # afference matrices.  Recover the count only when the header is zero.
    if model.gdl == 0:
        max_gdl = 0
        for element in (
            list(collections.quads.values())
            + list(collections.interfaces.values())
        ):
            for aff_i in element.aff:
                for entry in aff_i:
                    max_gdl = max(max_gdl, entry.gdl)
        model.gdl = max_gdl

    return model


def _parse_load_combination(elem: ET.Element) -> LoadCombination:
    combination = LoadCombination(
        key=_safe_int(_attr(elem, "Key", default="0")),
        name=_attr(elem, "Name", default=""),
        limit_state=_attr(elem, "LimitState", default=""),
    )
    for child in elem.iterfind("Item"):
        combination.items.append(
            LoadCombinationItem(
                column_key=_safe_int(
                    _attr(child, "ColumnKey", default="0")
                ),
                row_key=_safe_int(_attr(child, "RowKey", default="0")),
                name=_attr(child, "Name", default=""),
                type_data=_attr(child, "TypeData", default="Number"),
                secondary_type_data=_attr(
                    child, "SecondaryTypeData", default="Number"
                ),
                val=_safe_float(_attr(child, "Val", default="0")),
                combination=_safe_int(
                    _attr(child, "Combination", default="0")
                ),
            )
        )
    return combination


def _attr(elem: ET.Element, *names: str, default: str = "") -> str:
    for name in names:
        value = elem.get(name)
        if value is not None:
            return value
    return default


def _parse_xyz(value: str) -> tuple[float, float, float]:
    parts = str(value).replace(",", ".").split(";")
    if len(parts) != 3:
        raise ValueError(f"Expected X;Y;Z coordinates, got {value!r}")
    return tuple(float(part) for part in parts)  # type: ignore[return-value]


def _safe_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
