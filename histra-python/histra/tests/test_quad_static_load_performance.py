"""Regression tests for compiled Quad area-load integration."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from histra.elements import quad_static_load as qsl
from histra.io.hr_loader import load_model


ROOT = Path(__file__).resolve().parents[1]
LOCKED_HRX = ROOT / "model-output" / "model.hrx"


def _self_weight_inputs(model, quad):
    nodes = [model.collections.nodes[key].point for key in quad.node_keys]
    material = model.collections.materials[quad.material_key]
    forces = quad.compute_self_weight_load(0.0, 0.0, -1.0, material.w)
    return nodes, forces


def test_compiled_area_load_matches_scalar_for_reference_hrx_quads():
    model = load_model(LOCKED_HRX)
    checked = 0
    for quad in model.collections.quads.values():
        material = model.collections.materials.get(quad.material_key)
        if material is None or abs(float(material.w)) < 1.0e-30:
            continue
        nodes, forces = _self_weight_inputs(model, quad)
        expected = quad._compute_static_load_internal_scalar(nodes, forces)
        actual = quad.compute_static_load_internal(nodes, forces)
        np.testing.assert_array_equal(actual, expected)
        checked += 1
    assert checked, "Reference HRX contains no weighted Quads"


def test_area_load_scalar_fallback_matches_preserved_reference(monkeypatch):
    model = load_model(LOCKED_HRX)
    quad = next(
        item
        for item in model.collections.quads.values()
        if (
            model.collections.materials.get(item.material_key) is not None
            and abs(float(model.collections.materials[item.material_key].w)) >= 1.0e-30
        )
    )
    nodes, forces = _self_weight_inputs(model, quad)
    expected = quad._compute_static_load_internal_scalar(nodes, forces)

    monkeypatch.setattr(qsl, "_compute_static_load_area_nb", None)
    actual = quad.compute_static_load_internal(nodes, forces)
    np.testing.assert_array_equal(actual, expected)


def test_compiled_kernel_preserves_float32_operation_order():
    rng = np.random.default_rng(20260730)
    for _ in range(100):
        node_coords = rng.normal(size=(4, 3)).astype(np.float32) * np.float32(1000.0)
        nodal_forces = rng.normal(size=(4, 3)).astype(np.float32) * np.float32(20.0)
        centre = rng.normal(size=3).astype(np.float32) * np.float32(100.0)
        reference_e1 = rng.normal(size=3).astype(np.float32)
        reference_e2 = rng.normal(size=3).astype(np.float32)
        length = np.abs(rng.normal(size=4)) * 100.0 + 0.1
        sin = rng.uniform(-1.0, 1.0, size=4)
        if abs(float(sin[2])) < 0.05:
            sin[2] = 0.05
        cos = rng.uniform(-1.0, 1.0, size=4)

        expected = qsl._compute_static_load_area_scalar(
            node_coords,
            nodal_forces,
            centre,
            reference_e1,
            reference_e2,
            length,
            sin,
            cos,
        )
        actual = qsl.compute_static_load_area(
            node_coords,
            nodal_forces,
            centre,
            reference_e1,
            reference_e2,
            length,
            sin,
            cos,
        )
        np.testing.assert_array_equal(actual, expected)
