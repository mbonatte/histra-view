from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from histra.solver.cancellation import CancelCheck, raise_if_cancelled


@dataclass
class Program:
    """Runtime vectors, status and callbacks used by the solver."""

    gdl: int = 0
    ls: Any | None = None
    u: Any | None = None
    v: Any | None = None
    max_u: float = 0.0
    elem_max_u_key: int = 0
    elem_max_u_type: str = ""
    to_stop: bool = False
    index_fact_k: int = 0
    current_load_factor: float = 0.0
    on_log: Any | None = None
    on_progress: Any | None = None
    should_cancel: CancelCheck | None = None
    diagnostics: Any | None = None
    # Newton receives alfa by value; its UpdateK fallback survives trial
    # rollback within that call and is reset by the next Newton invocation.
    static_tangent_alpha: float | None = None

    def log(self, msg: str) -> None:
        if self.on_log:
            self.on_log(msg)
        else:
            import logging

            logging.getLogger(__name__).info(msg)

    def progress(self, val: float) -> None:
        self.check_cancelled()
        if self.on_progress:
            self.on_progress(float(val))

    def check_cancelled(self) -> None:
        """Raise at a solver-safe checkpoint when cancellation is requested."""
        raise_if_cancelled(self.should_cancel)
    def get_value_graph_analysis(
        self,
        collections: Any,
        an: Any,
        dof: int,
        reaction_sum: Any,
        out_displ: list,
    ) -> list[float]:
        """Port of C# ``Program.GetValueGraphAnalysis``.

        Returns the graph force/displacement pair used by solver monitoring:
        ``values[0]`` is the reaction sum projected on the analysis direction
        and ``values[1:]`` are the active model-point displacements projected
        on the same direction.  ``out_displ`` receives the control displacement
        C# uses for commit/stop decisions: the master model-point projection
        when ``master_point > 0``, the maximum absolute projection when the
        master is not a positive key, or ``|u[dof]|`` when no model point is
        defined.
        """
        direction = (
            float(getattr(an, "dir_x", 0.0) or 0.0),
            float(getattr(an, "dir_y", 0.0) or 0.0),
            float(getattr(an, "dir_z", 0.0) or 0.0),
        )
        force = 0.0
        if reaction_sum is not None:
            force = (
                float(getattr(reaction_sum, "x", 0.0)) * direction[0]
                + float(getattr(reaction_sum, "y", 0.0)) * direction[1]
                + float(getattr(reaction_sum, "z", 0.0)) * direction[2]
            )
        master = int(getattr(an, "master_point", -10))
        points = getattr(collections, "model_points", None) or {}
        if master in points:
            from histra.solver.output_projection import model_point_displacement

            values = [force]
            displ = 0.0
            for key, active in (getattr(an, "active_model_points", None) or {}).items():
                if not active:
                    continue
                point = points.get(int(key))
                if point is None:
                    continue
                if self.u is None:
                    point_value = 0.0
                else:
                    vector = model_point_displacement(collections, point, self.u)
                    point_value = (
                        float(vector[0]) * direction[0]
                        + float(vector[1]) * direction[1]
                        + float(vector[2]) * direction[2]
                    )
                values.append(point_value)
                if master > 0:
                    if int(key) == master:
                        displ = point_value
                else:
                    displ = max(displ, abs(point_value))
            out_displ.append(displ)
            return values
        if self.u is not None and dof is not None and 0 <= int(dof) < len(self.u):
            displ = abs(float(self.u[int(dof)]))
            out_displ.append(displ)
            return [force, displ]
        out_displ.append(0.0)
        return [force, 0.0]
    def add_value_graph_static_analysis(
        self,
        collections: Any,
        an: Any,
        values: list,
        ref_values: list,
        dof: int,
        step: int,
        time: float,
    ) -> None:
        del collections, an, values, ref_values, dof, step, time
