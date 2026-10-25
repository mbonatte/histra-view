from __future__ import annotations

from pathlib import Path

import pytest

from histra.io.hr_loader import load_model
from histra.solver.hysteretic_batch import _evaluate_linear_batch, build_hysteretic_batch


MODEL = Path(__file__).resolve().parents[1] / "model-live" / "model.hrx"


@pytest.mark.skipif(_evaluate_linear_batch is None, reason="Numba is unavailable")
def test_interface_batch_rejections_are_classified(monkeypatch) -> None:
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    model = load_model(MODEL)
    interface = next(
        value for value in model.collections.interfaces.values() if value.trasv_1
    )
    interface.trasv_1[0].tensile_curve_type = "UnsupportedForRegression"

    runtime = build_hysteretic_batch(model)

    assert runtime is not None
    counts = runtime.performance_counts()
    assert counts["interface_rejection_reasons"][
        "unsupported_tensile_curve_type"
    ] >= 1
    assert interface in runtime.unmanaged_interfaces
    assert "interface_coulomb_rejection_reasons" in counts
