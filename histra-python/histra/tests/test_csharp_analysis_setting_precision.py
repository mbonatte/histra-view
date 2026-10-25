"""Native analysis factory and arc-length commit boundaries."""
from pathlib import Path
from types import SimpleNamespace
import json

import numpy as np

from histra.solver.arc_length import ArcLength
from histra.solver.solution_algorithm import _new_line_search
from histra.solver.nonlinear_step import _load_reduction_stop_reached


def test_native_analysis_settings_and_arc_commit():
    path = Path(__file__).parent / "fixtures/csharp-analysis-setting-precision-2026.1.1.json"
    for case in json.loads(path.read_text(encoding="utf-8-sig"))["cases"]:
        tolerance, minimum, maximum, radius, threshold = case["inputs"]
        an = SimpleNamespace(method="StandardBisectionLineSearch", line_search_tolerance=tolerance,
                             line_search_min_eta=minimum, line_search_max_eta=maximum,
                             is_max_arc_length_ray=True, max_arc_length_ray=radius,
                             update_dr2=False, load_reduction_ratio_to_stop=True,
                             load_reduction_ratio_to_stop_value=threshold)
        search = _new_line_search(an)
        np.testing.assert_array_equal(
            [search.tolerance, search.min_eta, search.max_eta],
            [case["tolerance"], case["min_eta"], case["max_eta"]],
        )
        arc = ArcLength()
        arc._lf_items = [(0.0, 0.0), (1.0, 1.0)]
        arc._target_displacement = 1.0
        arc._arc_length2 = 0.5
        stop = arc.commit(None, an, 0.0, 0, [False])
        assert stop == case["stop"]
        assert arc._arc_length2 == case["arc_length2"]
        threshold = case["reduction_threshold"]
        assert _load_reduction_stop_reached(an, np.nextafter(threshold, -np.inf))
        assert not _load_reduction_stop_reached(an, threshold)
        assert not _load_reduction_stop_reached(an, np.nextafter(threshold, np.inf))


def test_stable_arc_commit_retains_explicit_squared_radius_cap():
    an = SimpleNamespace(is_max_arc_length_ray=True, max_arc_length_ray=0.1, update_dr2=False)
    arc = ArcLength(constraint_mode="stable")
    arc._lf_items = [(0.0, 0.0), (1.0, 1.0)]
    arc._target_displacement = 1.0
    arc._arc_length2 = 0.5
    assert not arc.commit(None, an, 0.0, 0, [False])
    radius = float(np.float32(0.1))
    assert arc._arc_length2 == radius * radius
