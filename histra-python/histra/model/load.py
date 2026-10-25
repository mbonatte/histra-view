"""Load and analysis dataclasses matching the HiStrA HRX schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class LoadCombinationItem:
    """One coefficient entry in a load combination."""

    column_key: int = 0
    row_key: int = 0
    name: str = ""
    type_data: str = "Number"
    secondary_type_data: str = "Number"
    val: float = 0.0
    combination: int = 0


@dataclass
class LoadCombination:
    """A load combination coefficient table."""

    key: int = 0
    name: str = ""
    limit_state: str = ""
    items: List[LoadCombinationItem] = field(default_factory=list)

    def get_coefficient(
        self, row_key: int, col_key: int
    ) -> LoadCombinationItem | None:
        for item in self.items:
            if item.row_key == row_key and item.column_key == col_key:
                return item
        return None


@dataclass
class LoadCondition:
    """A load condition type (gravity, variable action, and so on)."""

    id: int = 0
    name: str = ""
    description: str = ""
    mass_in_dir_x: float = 1.0
    mass_in_dir_y: float = 1.0
    mass_in_dir_z: float = 1.0
    is_main_load: bool = False
    is_favourable: bool = False
    is_un_favourable: bool = True
    gamma_fav_str: float = 1.0
    gamma_unfav_str: float = 1.0
    gamma_fav_geo: float = 1.0
    gamma_unfav_geo: float = 1.0
    action: int = 0

    def is_gravity(self) -> bool:
        return self.action == 1


@dataclass(frozen=True)
class LoadFunctionItem:
    """One point of the pseudo-time/load-multiplier function."""

    key: int = 0
    load_function_key: int = 0
    pseudo_time: float = 0.0
    multiplier: float = 0.0


@dataclass
class LoadFunction:
    """Load application function.

    C# stores ``LoadFunction`` and ``LoadFunctionItem`` as separate collections.
    The loader attaches matching items here and orders them by pseudo-time.
    """

    key: int = 0
    name: str = ""
    type_discr: bool = False
    discr_val: float = 0.1
    items: List[LoadFunctionItem] = field(default_factory=list)




@dataclass
class LoadTemplateItem:
    """One load-template value (force direction, magnitude and condition)."""

    key: int = 0
    id: int = 0
    load_template_key: int = 0
    load_condition_id: int = 0
    load_value: float = 0.0
    dir_x: float = 0.0
    dir_y: float = 0.0
    dir_z: float = 0.0
    psi0: float = 0.0
    psi1: float = 0.0
    psi2: float = 0.0
    is_projected: bool = False
    load_type: str = "Force"
    # Existing programmatic clients supply a custom vector. The XML reader
    # supplies the native IdLoadDirection value (default 0) explicitly.
    load_direction: int = 7

    def direction_for(self, element) -> tuple[float, float, float]:
        """Original LoadTemplateItem.Dir(Element), including Single normalization."""
        import numpy as np
        from histra.preprocessing.quad_geometry import _unit

        code = int(self.load_direction)
        if 0 <= code <= 3:
            vector = ((0.,0.,-1.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.))[code]
        elif 4 <= code <= 6:
            if element is None:
                raise ValueError("An element is required for a local load direction")
            vector = getattr(element, ("reference_e1","reference_e2","reference_e3")[code-4])
        elif code == 7:
            vector = self.direction
        else:
            raise ValueError(f"Unsupported IdLoadDirection={code}")
        norm_vec = _unit(np.asarray(vector, dtype=np.float32))
        return (float(norm_vec[0]), float(norm_vec[1]), float(norm_vec[2]))

    @property
    def direction(self) -> tuple[float, float, float]:
        return (self.dir_x, self.dir_y, self.dir_z)


@dataclass
class LoadTemplate:
    """C# ``LoadTemplate`` subset required by static element loads."""

    key: int = 0
    name: str = ""
    purpose_type: str = ""
    dynamic_coefficient: float = 1.0
    items: List[LoadTemplateItem] = field(default_factory=list)


@dataclass(frozen=True)
class LineLoadElement:
    """A line load assigned directly to one computational element."""

    key: int = 0
    parent_key: int = 0
    element_key: int = 0
    element_type: str = ""
    load_template_key: int = 0
    point1: tuple[float, float, float] = (0.0, 0.0, 0.0)
    point2: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def points(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        return (self.point1, self.point2)


@dataclass(frozen=True)
class ModelPoint:
    """Model point used to select ArcLength constraint DOFs."""

    key: int = 0
    element_key: int = 0
    element_type: str = ""
    id_vertex: int = 0


@dataclass
class Analysis:
    """Static/modal analysis definition used by the translated solver."""

    key: int = 0
    name: str = ""
    analysis_type: int = 0
    load_combination_key: int = 0
    load_function_key: int = 0
    initial_analysis_key: int = -100
    initial_combination_analysis_key: int = 1
    dir_x: float = 0.0
    dir_y: float = 0.0
    dir_z: float = -1.0
    is_seismic: bool = False
    mult: float = 1.0
    # C# load-path controls.  ``force_imposed`` is retained for HRX fidelity;
    # the supplied C# runtime only uses it in the desktop UI.  ``force_control``
    # affects the C# load-refresh path for frame/restraint domains, which are
    # outside the V1 computational scope, but retaining it prevents an HRX
    # setting from being silently discarded.
    type_load_distribution: str = "LoadCombination"
    force_imposed: bool = True
    force_control: bool = True

    integration_method: str = "LoadControl"
    method: str = "StandardNewtonRaphson"
    adaptive_convergence_criteria: str = "ForceMoment"
    convergence_tolerance: float = 1e-4
    max_iterations: int = 1000
    max_u: float = 100.0

    number_of_eigen_modes: int = 1
    number_of_lanczos_eigen_vectors: int = 3
    modal_procedure: str = "InverseIterations"
    residual_vector_tolerance: float = 0.5
    modal_convergence_criteria: str = "Frquency"

    pdelta_effect: str = "None"
    als: bool = False
    max_number_als: int = 10
    load_factor_als: int = 2

    master_point: int = -10
    target_displacement: float = 0.0
    dr2: float = 1.0e-4
    arc_length_procedure: str = "OnlyControlPoint"
    update_dr2: bool = False
    desired_iterations: int = 5
    is_max_arc_length_ray: bool = False
    max_arc_length_ray: float = 1.0

    line_search_tolerance: float = 0.8
    line_search_max_iterations: int = 1000
    line_search_max_eta: float = 10.0
    line_search_min_eta: float = 0.1

    load_reduction_ratio_to_stop: bool = False
    load_reduction_ratio_to_stop_value: float = 0.1
    check_secant_stiffness: bool = False
    secant_stiffness_ratio: float = 0.0
    step_save: int = 1
    active_model_points: dict[int, bool] = field(default_factory=dict)

    # Populated by ``load_model`` after all top-level entities are parsed.
    load_function: LoadFunction | None = field(default=None, repr=False)
