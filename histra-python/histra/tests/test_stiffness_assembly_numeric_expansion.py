from __future__ import annotations

import numpy as np

from histra.solver.assembler import _expand_scatter_terms_numeric


def test_numeric_scatter_expansion_matches_scalar_csharp_order_exactly() -> None:
    # Four afference lists with deliberately non-uniform lengths exercise the
    # variable-size Cartesian products and immediate C# mirror ordering.
    aff_starts = np.asarray([0, 2, 5, 6], dtype=np.int64)
    aff_lengths = np.asarray([2, 3, 1, 2], dtype=np.int64)
    aff_gdls = np.asarray([7, 2, 4, 9, 1, 6, 8, 3], dtype=np.int32)
    aff_coefficients = np.asarray(
        [1.0, -0.25, 0.5, 2.0, -1.5, 0.75, -2.5, 1.25],
        dtype=np.float64,
    )
    term_aff_i = np.asarray([0, 1, 3, 2], dtype=np.int32)
    term_aff_j = np.asarray([1, 3, 0, 2], dtype=np.int32)
    term_values = np.asarray([11, 12, 13, 14], dtype=np.int32)
    term_mirror = np.asarray([False, True, True, False], dtype=np.bool_)

    rows, cols, terms, alpha_i, alpha_j = _expand_scatter_terms_numeric(
        aff_starts=aff_starts,
        aff_lengths=aff_lengths,
        aff_gdls=aff_gdls,
        aff_coefficients=aff_coefficients,
        term_aff_i=term_aff_i,
        term_aff_j=term_aff_j,
        term_values=term_values,
        term_mirror=term_mirror,
        chunk_terms=2,
    )

    expected_rows: list[int] = []
    expected_cols: list[int] = []
    expected_terms: list[int] = []
    expected_ai: list[float] = []
    expected_aj: list[float] = []
    for term in range(term_values.size):
        ai_start = int(aff_starts[term_aff_i[term]])
        aj_start = int(aff_starts[term_aff_j[term]])
        for i in range(int(aff_lengths[term_aff_i[term]])):
            ai_pos = ai_start + i
            for j in range(int(aff_lengths[term_aff_j[term]])):
                aj_pos = aj_start + j
                gi = int(aff_gdls[ai_pos])
                gj = int(aff_gdls[aj_pos])
                a_i = float(aff_coefficients[ai_pos])
                a_j = float(aff_coefficients[aj_pos])
                expected_rows.append(gi)
                expected_cols.append(gj)
                expected_terms.append(int(term_values[term]))
                expected_ai.append(a_i)
                expected_aj.append(a_j)
                if bool(term_mirror[term]):
                    expected_rows.append(gj)
                    expected_cols.append(gi)
                    expected_terms.append(int(term_values[term]))
                    # C# mirrored SumK keeps alpha arguments in local i,j order.
                    expected_ai.append(a_i)
                    expected_aj.append(a_j)

    np.testing.assert_array_equal(rows, np.asarray(expected_rows, dtype=np.int32))
    np.testing.assert_array_equal(cols, np.asarray(expected_cols, dtype=np.int32))
    np.testing.assert_array_equal(terms, np.asarray(expected_terms, dtype=np.int32))
    np.testing.assert_array_equal(alpha_i, np.asarray(expected_ai, dtype=np.float64))
    np.testing.assert_array_equal(alpha_j, np.asarray(expected_aj, dtype=np.float64))
