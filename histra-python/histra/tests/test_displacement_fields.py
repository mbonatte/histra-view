"""Batch output must preserve C# projection bits and ordered node averaging."""

import json
from pathlib import Path
import struct
from types import SimpleNamespace as Namespace

import numpy as np
import pytest

from histra.io.displacement_fields import build_displacement_fields
from histra.postprocessing import compute_node_displacements, quad_node_displacement


def _quad(aff, nodes, rng):
    return Namespace(
        aff=aff,
        node_keys=nodes,
        g=Namespace(x=1.25, y=-2.5, z=1.1),
        length=[1.0, 1.0, 1.0, 123.456789],
        sin=rng.uniform(-1, 1, 4),
        cos=rng.uniform(-1, 1, 4),
        reference_e1=[0.6, 0.8, 0.0],
        reference_e2=[-0.8, 0.6, 0.1],
    )


def _model(quads, gdl=7):
    point = Namespace(x=31.25, y=-12.5, z=7.3)
    nodes = {key: Namespace(name=str(key), point=point) for key in (0, 1, 2, 3, 4)}
    return Namespace(gdl=gdl, collections=Namespace(quads=quads, nodes=nodes, interfaces={}))


def _assert_bits(actual, expected):
    expected = np.asarray(expected, dtype=np.float32)
    assert actual.dtype == np.float32
    np.testing.assert_array_equal(actual.view(np.uint32), expected.view(np.uint32))


def test_batch_projection_matches_original_csharp_binary_fixture():
    data = json.loads(
        (Path(__file__).parent / "fixtures/csharp_quad_displacement_2026_1_1.json").read_text(
            encoding="utf-8-sig"
        )
    )

    def decode(value):
        return struct.unpack("<d", struct.pack("<q", int(value)))[0]

    aff = [[Namespace(gdl=i + 1, alfa=1.0)] for i in range(7)]
    quad = _quad(aff, [1, 2, 3, 4], np.random.default_rng(0))
    quad.sin = [decode(v) for v in data["sin_bits"]]
    quad.cos = [decode(v) for v in data["cos_bits"]]
    quad.length[3] = decode(data["length_bits"])
    quad.reference_e1 = [data["e1"][a] for a in ("X", "Y", "Z")]
    quad.reference_e2 = [data["e2"][a] for a in ("X", "Y", "Z")]
    steps = [{"u": np.array([decode(v) for v in case["u_bits"]])} for case in data["cases"]]
    actual, _ = build_displacement_fields(_model({1: quad}), steps)
    for index, case in enumerate(data["cases"]):
        np.testing.assert_array_equal(
            actual[index, 0, case["vertex"]].view(np.int32), np.array(case["bits"], dtype=np.int32)
        )


@pytest.mark.parametrize("denominator", [0.6, 0.0, 1e-31, 1e-30, -1e-29])
def test_batch_matches_scalar_for_shared_nodes_unsorted_quads_and_afferences(denominator):
    rng = np.random.default_rng(1302)
    quads = {}
    for key in (7, 2, 13):
        aff = [
            [
                Namespace(gdl=dof, alfa=weight)
                for dof, weight in zip((i + 1, 8 + i, -1, 22), (1.2, -0.8, 12.0, 8.0))
            ]
            for i in range(7)
        ]
        quad = _quad(aff, np.roll([1, 2, 3, 4], key % 4), rng)
        quad.sin[2] = denominator
        quads[key] = quad
    model = _model(quads, gdl=21)
    steps = [{"u": rng.normal(size=21) * 10.0**scale} for scale in range(-12, 13)]
    steps.append({"u": None})
    quad_fields, node_fields = build_displacement_fields(model, steps)
    for index, step in enumerate(steps[:-1]):
        expected = [
            [
                quad_node_displacement(q, model.collections.nodes[key].point, corner, step["u"])
                for corner, key in enumerate(q.node_keys)
            ]
            for _, q in sorted(quads.items())
        ]
        _assert_bits(quad_fields[index], expected)
        rows = compute_node_displacements(model, step["u"], only_quad_nodes=True)
        expected_nodes = np.zeros((5, 3), np.float32)
        expected_nodes[: len(rows)] = [(row.ux, row.uy, row.uz) for row in rows]
        _assert_bits(node_fields[index], expected_nodes)
    assert not np.any(quad_fields[-1]) and not np.any(node_fields[-1])
    without_nodes, missing = build_displacement_fields(
        model, steps, include_node_displacements=False
    )
    _assert_bits(without_nodes, quad_fields)
    assert missing is None
    _, truncated = build_displacement_fields(model, steps, node_count=2)
    _assert_bits(truncated, node_fields[:, :2])


def test_empty_projection_and_invalid_displacement_length():
    empty, nodes = build_displacement_fields(_model({}), [])
    assert empty.shape == (0, 0, 4, 3) and nodes.shape == (0, 5, 3)
    with pytest.raises(ValueError, match="length 7"):
        build_displacement_fields(_model({}), [{"u": np.zeros(6)}])
