"""Boundary regressions using saved constants and analytical expectations.

These do not all have independent native captures. Exact integer-bit assertions
freeze an expected response; they do not establish its C# provenance. See the
current source audit for native evidence and the remaining capture work.

Covers:
1. Gauss quadrature table comparisons (N=2..10).
2. Arc-Length Crisfield solver with complex roots (discriminant < 0), zero bar, and extreme trial states.
3. Sutherland-Hodgman polygon clipping with non-overlapping, touching, orthogonal, and identical quadrilaterals.
4. Polygon area with collinear points, degenerate quadrilaterals, and high-magnitude coordinates.
5. Coulomb friction with positive normal forces, high friction and cyclic slip reversal.
6. Hysteretic masonry springs with cyclic plastic strains and pinching.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest

from histra.preprocessing.csharp_fibre_geometry import _csharp_polygon_area
from histra.preprocessing.contact_geometry import _coplanar_quad_intersection_prechecked
from histra.solver.arc_length import ArcLength
from histra.springs.coulomb03 import SpringCoulomb03
from histra.springs.hysteretic import SpringHysteretic
from histra.tests.test_csharp_gauss_live import CSHARP_GAUSS_EXACT


# ==============================================================================
# Scope 1: Gauss Quadrature Stress Testing
# ==============================================================================

def test_adversarial_gauss_quadrature_orders():
    """Stress test Gauss-Legendre quadrature across orders N=2..10 against authoritative C# outputs."""
    for n in range(2, 11):
        data = CSHARP_GAUSS_EXACT[n]
        assert data["order"] == n

        cs_z = np.asarray(data["z"], dtype=np.float64)
        cs_w = np.asarray(data["w"], dtype=np.float64)
        py_z, py_w = np.polynomial.legendre.leggauss(n)

        # For order 2: exact IEEE-754 bit-for-bit equality
        if n == 2:
            for val_py, bits_cs in zip(py_z, data["z_bits"]):
                assert int(np.asarray([val_py], dtype=np.float64).view(np.int64)[0]) == int(bits_cs)
            for val_py, bits_cs in zip(py_w, data["w_bits"]):
                assert int(np.asarray([val_py], dtype=np.float64).view(np.int64)[0]) == int(bits_cs)

        # Compare using the explicit absolute/relative bounds below.
        np.testing.assert_allclose(cs_z, py_z, atol=1e-15, rtol=1e-15)
        np.testing.assert_allclose(cs_w, py_w, atol=1e-15, rtol=1e-15)

        # Symmetry invariants
        np.testing.assert_allclose(cs_z, -cs_z[::-1], atol=1e-15)
        np.testing.assert_allclose(cs_w, cs_w[::-1], atol=1e-15)
        assert abs(np.sum(cs_w) - 2.0) <= 1e-15


# ==============================================================================
# Scope 2: Arc-Length Crisfield Solver Stress Testing
# ==============================================================================

def _run_python_arc_length(case: dict) -> tuple[int, ArcLength]:
    arc = ArcLength(constraint_mode="csharp")
    arc._alpha2 = float(case["alpha2"])
    hat_vec = case["hat"] if isinstance(case["hat"], list) else [float(case["hat"])]
    bar_vec = case["bar"] if isinstance(case["bar"], list) else [float(case["bar"])]
    step_vec = case["step"] if isinstance(case["step"], list) else [float(case["step"])]

    arc._phat = np.array(hat_vec, dtype=np.float64)
    arc._delta_u_step = np.array(step_vec, dtype=np.float64)
    arc._dofs = np.arange(len(hat_vec), dtype=int)
    arc.u = np.zeros(len(hat_vec), dtype=np.float64)
    arc.state.combination = 1
    arc.update_ptarget = lambda *args: None
    arc.apply_load_domain = lambda *args: None

    class MockLinearSystem:
        def __init__(self, val):
            self.matrix_version = 1
            self.x = np.array(val, dtype=np.float64)

        def solve(self, rhs):
            self.x = rhs.copy()

        def set_x_vector(self, values):
            self.x = values.copy()

    with patch("histra.solver.arc_length.ModelManager.update_domain"):
        code = arc.update(object(), SimpleNamespace(ls=MockLinearSystem(bar_vec)), object())
    return code, arc


def test_adversarial_arc_length_complex_roots_fallback():
    """Stress test Crisfield constraint when discriminant b^2 - 4ac < 0 (complex roots)."""
    case = {
        "alpha2": 0.0,
        "hat": [1.0, 1.0],
        "step": [1.0, 2.0],
        "bar": [-3.0, 0.0],
    }
    expected_lambda_bits = 4607182418800017408  # 1.0
    expected_du = [-2.0, 1.0]

    py_code, arc = _run_python_arc_length(case)

    assert py_code == 0
    py_lambda_bits = int(np.asarray([arc._last_delta_lambda], dtype=np.float64).view(np.int64)[0])
    assert py_lambda_bits == expected_lambda_bits
    np.testing.assert_array_equal(arc._last_delta_u, expected_du)


def test_adversarial_arc_length_zero_bar_and_extreme_states():
    """Check stored zero-bar and extreme-state regression expectations."""
    # 1. Zero bar displacement: c = 0
    case_zero_bar = {
        "alpha2": 0.0,
        "hat": [2.0, 1.5],
        "step": [0.1, -0.05],
        "bar": [0.0, 0.0],
    }
    code_zero, arc_zero = _run_python_arc_length(case_zero_bar)
    assert code_zero == 0
    assert arc_zero._last_delta_lambda == 0.0
    np.testing.assert_array_equal(arc_zero._last_delta_u, [0.0, 0.0])

    # 2. Large displacements (1e5..1e6 magnitude)
    case_large = {
        "alpha2": 100.0,
        "hat": [1e5, 2e5],
        "step": [1e6, -1e6],
        "bar": [100.0, -200.0],
    }
    expected_large_lambda_bits = 4616185561189864155
    code_large, arc_large = _run_python_arc_length(case_large)
    assert code_large == 0
    py_lambda_bits = int(np.asarray([arc_large._last_delta_lambda], dtype=np.float64).view(np.int64)[0])
    assert py_lambda_bits == expected_large_lambda_bits

    # 3. Degenerate zero reference load with zero alpha2 -> error code -10
    case_zero_ref = {
        "alpha2": 0.0,
        "hat": [0.0, 0.0],
        "step": [0.1, 0.1],
        "bar": [0.01, 0.01],
    }
    code_zero_ref, _ = _run_python_arc_length(case_zero_ref)
    assert code_zero_ref == -10


# ==============================================================================
# Scope 3: Sutherland-Hodgman Polygon Clipping Stress Testing
# ==============================================================================

def test_adversarial_polygon_clipping_topologies():
    """Stress test Sutherland-Hodgman polygon clipping under diverse topological intersections."""
    # 1. Non-overlapping disjoint quadrilaterals
    p_non1 = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]
    p_non2 = [[2.0, 0.0, 0.0], [3.0, 0.0, 0.0], [3.0, 1.0, 0.0], [2.0, 1.0, 0.0]]
    py_non = _coplanar_quad_intersection_prechecked(
        np.array(p_non1), np.array(p_non2), np.array([0.0, 0.0, 1.0]), node_tolerance=1.0
    )
    assert py_non is None

    # 2. Touching edge (zero contact area, sliver rejected)
    p_edge1 = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]
    p_edge2 = [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 1.0, 0.0], [1.0, 1.0, 0.0]]
    py_edge = _coplanar_quad_intersection_prechecked(
        np.array(p_edge1), np.array(p_edge2), np.array([0.0, 0.0, 1.0]), node_tolerance=1.0
    )
    assert py_edge is None

    # 3. Touching vertex (point contact, area = 0)
    p_vert1 = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]
    p_vert2 = [[1.0, 1.0, 0.0], [2.0, 1.0, 0.0], [2.0, 2.0, 0.0], [1.0, 2.0, 0.0]]
    py_vert = _coplanar_quad_intersection_prechecked(
        np.array(p_vert1), np.array(p_vert2), np.array([0.0, 0.0, 1.0]), node_tolerance=1.0
    )
    assert py_vert is None

    # 4. Orthogonal overlapping quadrilaterals (cross intersection)
    p_ortho1 = [[0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [4.0, 2.0, 0.0], [0.0, 2.0, 0.0]]
    p_ortho2 = [[1.0, -1.0, 0.0], [3.0, -1.0, 0.0], [3.0, 3.0, 0.0], [1.0, 3.0, 0.0]]
    expected_ortho_single_bits = 1082130432  # 4.0
    py_ortho = _coplanar_quad_intersection_prechecked(
        np.array(p_ortho1), np.array(p_ortho2), np.array([0.0, 0.0, 1.0]), node_tolerance=1.0
    )
    assert py_ortho is not None
    py_ortho_area = _csharp_polygon_area(np.asarray(py_ortho, dtype=np.float32))
    assert int(np.asarray([py_ortho_area], dtype=np.float32).view(np.int32)[0]) == expected_ortho_single_bits

    # 5. Identical coincident quadrilaterals
    p_ident1 = [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 2.0, 0.0], [0.0, 2.0, 0.0]]
    p_ident2 = [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 2.0, 0.0], [0.0, 2.0, 0.0]]
    expected_ident_single_bits = 1082130432  # 4.0
    py_ident = _coplanar_quad_intersection_prechecked(
        np.array(p_ident1), np.array(p_ident2), np.array([0.0, 0.0, 1.0]), node_tolerance=1.0
    )
    assert py_ident is not None
    py_ident_area = _csharp_polygon_area(np.asarray(py_ident, dtype=np.float32))
    assert int(np.asarray([py_ident_area], dtype=np.float32).view(np.int32)[0]) == expected_ident_single_bits


# ==============================================================================
# Scope 4: Polygon Area Calculation Stress Testing
# ==============================================================================

def test_adversarial_polygon_area_geometry():
    """Stress test 3D shoelace polygon area with high magnitudes and collinear edge points."""
    # 1. High-magnitude coordinates: base offset 1e6 mm
    pts_high = [
        [1e6, 1e6, 0.0],
        [1e6 + 2.0, 1e6, 0.0],
        [1e6 + 2.0, 1e6 + 3.0, 0.0],
        [1e6, 1e6 + 3.0, 0.0],
    ]
    expected_high_single_bits = 1086324736  # 6.0
    py_high = _csharp_polygon_area(np.asarray(pts_high, dtype=np.float32))
    assert abs(py_high - 6.0) < 1e-6
    py_bits = int(np.asarray([py_high], dtype=np.float32).view(np.int32)[0])
    assert py_bits == expected_high_single_bits

    # 2. Polygon with a collinear edge vertex (pentagon where vertex 3 lies on top edge)
    pts_collinear_edge = [
        [0.0, 0.0, 0.0],
        [2.0, 0.0, 0.0],
        [2.0, 2.0, 0.0],
        [1.0, 2.0, 0.0],
        [0.0, 2.0, 0.0],
    ]
    expected_col_single_bits = 1082130432  # 4.0
    py_col_edge = _csharp_polygon_area(np.asarray(pts_collinear_edge, dtype=np.float32))
    assert abs(py_col_edge - 4.0) < 1e-6
    py_col_bits = int(np.asarray([py_col_edge], dtype=np.float32).view(np.int32)[0])
    assert py_col_bits == expected_col_single_bits

    # 3. Collinear base points: raises ZeroDivisionError on 0-norm normal vector
    pts_collinear_base = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0]]
    with pytest.raises(ZeroDivisionError):
        _csharp_polygon_area(np.asarray(pts_collinear_base, dtype=np.float32))


# ==============================================================================
# Scope 5: Coulomb Friction Stress Testing
# ==============================================================================

def test_adversarial_coulomb_friction_cyclic_and_extremes():
    """Stress test Coulomb friction with extreme normal forces and cyclic slip reversal."""
    k = 2000.0
    cohesion = 1.0
    mu = 0.5
    normal_force = 2.0
    ur = 0.05
    ktang = 0.0
    plastic_strain_ratio = 0.0

    # 1. 10-step cyclic slip history
    strains = [0.0005, 0.001, 0.002, 0.001, 0.0, -0.001, -0.002, -0.001, 0.0, 0.0015]
    expected_cyclic_bits = [
        4607182418800017408, 4611686018427387904, 4611595045623023298, -4646425410298054944,
        -4616166989129853449, -4611686018427387904, -4611776991231752510, 4574308843561158732,
        4604159260207024610, 4610113994093147726
    ]

    mom1p = max(1e-9, cohesion + mu * 0.0)
    rot1p = mom1p / k
    rot2p = max(plastic_strain_ratio, rot1p * 1.0001)
    mom2p = mom1p + ktang * (rot2p - rot1p)
    rot3p = max(ur, rot2p * 1.0001)
    mom3p = 0.0

    py_spring = SpringCoulomb03(k=k, cohesion=cohesion, mu=mu, ur=ur, sub_law="Coulomb")
    py_spring.mom1p = mom1p
    py_spring.rot1p = rot1p
    py_spring.mom2p = mom2p
    py_spring.rot2p = rot2p
    py_spring.mom3p = mom3p
    py_spring.rot3p = rot3p
    py_spring.mom1n = -mom1p
    py_spring.rot1n = -rot1p
    py_spring.mom2n = -mom2p
    py_spring.rot2n = -rot2p
    py_spring.mom3n = -mom3p
    py_spring.rot3n = -rot3p
    py_spring._set_envelope()
    py_spring.revert_to_start()
    py_spring.revert_to_last_commit()
    py_spring._cstress_normal = normal_force
    py_spring._tstress_normal = normal_force

    py_bits = []
    for s in strains:
        py_spring.set_trial_strain(s)
        f = py_spring.get_force()
        py_spring.commit()
        py_bits.append(int(np.asarray([f], dtype=np.float64).view(np.int64)[0]))

    # Bit-for-bit exact match across all 10 cyclic loading steps
    assert py_bits == expected_cyclic_bits

    # 2. High friction angle (mu = 10.0, phi = 84.3 deg)
    high_mu_strains = [0.0001, 0.0005]
    expected_high_mu_bits = [4596373779694328218, 4607182418800017408]
    s_high_mu = SpringCoulomb03(k=k, cohesion=20.0, mu=10.0, ur=ur, sub_law="Coulomb")
    s_high_mu.mom1p = 20.0
    s_high_mu.rot1p = 20.0 / k
    s_high_mu.mom2p = 20.0
    s_high_mu.rot2p = s_high_mu.rot1p * 1.0001
    s_high_mu.mom3p = 0.0
    s_high_mu.rot3p = ur
    s_high_mu.mom1n = -20.0
    s_high_mu.rot1n = -s_high_mu.rot1p
    s_high_mu.mom2n = -20.0
    s_high_mu.rot2n = -s_high_mu.rot2p
    s_high_mu.mom3n = 0.0
    s_high_mu.rot3n = -ur
    s_high_mu._set_envelope()
    s_high_mu.revert_to_start()
    s_high_mu.revert_to_last_commit()
    s_high_mu._cstress_normal = 100.0
    s_high_mu._tstress_normal = 100.0

    py_high_mu_bits = []
    for s in high_mu_strains:
        s_high_mu.set_trial_strain(s)
        f = s_high_mu.get_force()
        s_high_mu.commit()
        py_high_mu_bits.append(int(np.asarray([f], dtype=np.float64).view(np.int64)[0]))

    assert py_high_mu_bits == expected_high_mu_bits


# ==============================================================================
# Scope 6: Hysteretic and Multilinear Springs Stress Testing
# ==============================================================================

def test_adversarial_hysteretic_spring_cyclic_pinching():
    """Stress test SpringHysteretic with large cyclic plastic strains and pinching."""
    m1p, r1p = 20.0, 0.01
    m2p, r2p = 25.0, 0.03
    m3p, r3p = 0.0, 0.05
    m1n, r1n = -20.0, -0.01
    m2n, r2n = -25.0, -0.03
    m3n, r3n = 0.0, -0.05
    pinchXp, pinchYp = 0.2, 0.3
    pinchXn, pinchYn = 0.2, 0.3
    d1p = d2p = d1n = d2n = betap = betan = 0.0

    strains = [0.005, 0.015, 0.025, 0.010, 0.0, -0.015, -0.025, -0.005, 0.0, 0.020]
    expected_force_bits = [
        4621819117588971520, 4626674560937230336, 4627378248379006976, -4605140088736442415,
        -4599883871665208438, -4596697475917545472, -4595993788475768832, 4616414644882233650,
        4622284869517982642, 4626650767385953784
    ]

    py_spring = SpringHysteretic(
        k=m1p / r1p,
        tensile_curve_type="LinearHardening",
        compressive_curve_type="LinearHardening",
        pinch_xp=pinchXp, pinch_yp=pinchYp,
        pinch_xn=pinchXn, pinch_yn=pinchYn,
        damfc1p=d1p, damfc2p=d2p, damfc1n=d1n, damfc2n=d2n,
        betap=betap, betan=betan,
        mom1p=m1p, rot1p=r1p, mom2p=m2p, rot2p=r2p, mom3p=m3p, rot3p=r3p,
        mom1n=m1n, rot1n=r1n, mom2n=m2n, rot2n=r2n, mom3n=m3n, rot3n=r3n,
    )
    py_spring._set_envelope()
    py_spring.revert_to_start()
    py_spring.revert_to_last_commit()

    py_bits = []
    for s in strains:
        py_spring.set_trial_strain(s)
        f = py_spring.get_force()
        py_spring.commit()
        py_bits.append(int(np.asarray([f], dtype=np.float64).view(np.int64)[0]))

    # Verify 100% bit-for-bit match at every single cyclic step
    assert py_bits == expected_force_bits
