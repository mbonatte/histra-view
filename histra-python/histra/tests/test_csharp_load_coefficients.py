"""Native references cover every supported primary/secondary coefficient pair."""
from pathlib import Path
import json

import numpy as np

from histra.model.load import LoadCombinationItem, LoadCondition, LoadTemplateItem
from histra.solver.load_assembly import _resolve_coefficient


def test_all_native_coefficient_bits():
    fixture = Path(__file__).parent / "fixtures/csharp-load-coefficients-2026.1.1.json"
    cases = json.loads(fixture.read_text(encoding="utf-8-sig"))["cases"]
    actual = []
    for case in cases:
        value, gs, us, gg, ug, p0, p1, p2 = case["inputs"]
        condition = LoadCondition(gamma_fav_str=gs, gamma_unfav_str=us,
                                  gamma_fav_geo=gg, gamma_unfav_geo=ug)
        template = LoadTemplateItem(psi0=p0, psi1=p1, psi2=p2)
        item = LoadCombinationItem(type_data=case["primary"],
                                   secondary_type_data=case["secondary"], val=value)
        actual.append(_resolve_coefficient(item, condition, template))
    np.testing.assert_array_equal(actual, [case["value"] for case in cases])
