"""Elastic and fixed Restraint support semantics shared by preprocessing/solver.

C# stores six numerical restraint stiffnesses in ``Restraint.K`` expressed in
the restraint's local reference system:

* ``-1``: fully fixed (no independent restraint DOF);
* `` 0``: free (an independent DOF exists but carries no stiffness);
* ``>0``: elastic stiffness in force/length (translations) or
  moment/rotation (rotations).

Only the verified vertical foundation case is translated here: ``K2 > 0``
with every other direction fixed.  The subgrade modulus ``Kz`` is not stored
in the HRX; the C# foundation mesher multiplies it by the tributary foundation
area ``B * L`` before writing ``K2`` (force/length).  Python therefore consumes
only the written ``K2`` value and never invents a soil material.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from histra.preprocessing.errors import ModelPreparationError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from histra.elements.interface import Interface
    from histra.model.model import Model
    from histra.model.restraint import Restraint
    from histra.types.linear_system import LinearSystem


FIXED = "fixed"
ELASTIC_VERTICAL = "elastic_vertical"

_INDEX_NAMES = ("K1", "K2", "K3", "Kr1", "Kr2", "Kr3")


def _is_fixed(value: float) -> bool:
    return abs(float(value) + 1.0) <= 1.0e-12


def _is_zero(value: float) -> bool:
    return abs(float(value)) <= 1.0e-12


def classify_restraint_stiffness(restraint: "Restraint") -> str:
    """Return the supported stiffness mode or fail with a precise reason.

    The native GUI can represent elastic stiffness independently in all six
    local directions.  Only the normal (local-2) foundation spring has C#
    source evidence and a verified interface mapping; silently accepting other
    elastic or free directions would turn unverified UI options into a
    different mechanical model.
    """
    values = [float(value) for value in restraint.k]
    if len(values) != 6:
        raise ModelPreparationError(
            f"Restraint {restraint.key} has {len(values)} stiffness values; expected 6."
        )
    if all(_is_fixed(value) for value in values):
        return FIXED

    if _is_fixed(values[0]) and values[1] > 0.0 and all(
        _is_fixed(value) for value in values[2:]
    ):
        if int(restraint.material_key) != 0:
            raise ModelPreparationError(
                f"Restraint {restraint.key} combines an elastic vertical stiffness "
                f"with MaterialKey={restraint.material_key}; elastic restraint "
                "stiffness and geotechnical material springs are not a verified "
                "combination."
            )
        if not np.isfinite(values[1]):
            raise ModelPreparationError(
                f"Restraint {restraint.key} has a non-finite elastic K2."
            )
        return ELASTIC_VERTICAL

    free = [
        _INDEX_NAMES[index] for index, value in enumerate(values) if _is_zero(value)
    ]
    elastic = [
        _INDEX_NAMES[index] for index, value in enumerate(values) if value > 0.0
    ]
    if free:
        raise ModelPreparationError(
            f"Restraint {restraint.key} has free local direction(s) {', '.join(free)}; "
            "only fully fixed restraints and a single elastic vertical K2 are translated."
        )
    if elastic:
        raise ModelPreparationError(
            f"Restraint {restraint.key} has unsupported elastic local direction(s) "
            f"{', '.join(elastic)}; only K2 (vertical foundation) is supported."
        )
    raise ModelPreparationError(
        f"Restraint {restraint.key} has unsupported stiffness values "
        f"K={list(restraint.k)!r}."
    )


def active_restraint_directions(restraint: "Restraint") -> tuple[int, ...]:
    """Return local K indices that require an independent global DOF."""
    return tuple(
        index for index, value in enumerate(restraint.k) if float(value) >= 0.0
    )


def assign_restraint_dofs(model: "Model", last_gdl: int) -> int:
    """Append native restraint DOFs after the Quad DOFs.

    C# ``ModelManager.ComputeAff`` visits Quads first and Restraints next, so
    appending here preserves the observable DOF order whenever a model actually
    contains elastic restraints.  Fully fixed restraints allocate no DOF, which
    keeps every existing fixed-restraint model bit-for-bit unchanged.

    ``last_gdl`` is the highest DOF number already assigned (0 when none).
    The return value is the new highest assigned DOF number.
    """
    assert model.collections is not None
    gdl = int(last_gdl)
    for restraint in sorted(
        getattr(model.collections, "restraints", {}).values(),
        key=lambda item: item.key,
    ):
        mode = classify_restraint_stiffness(restraint)
        restraint.u = [0.0] * 6
        restraint.solver_gdls = [0] * 6
        if mode == FIXED:
            continue
        for local_index in active_restraint_directions(restraint):
            gdl += 1
            restraint.solver_gdls[local_index] = gdl
    return gdl


def has_elastic_restraints(model: "Model") -> bool:
    assert model.collections is not None
    return any(
        classify_restraint_stiffness(restraint) != FIXED
        for restraint in getattr(model.collections, "restraints", {}).values()
    )


def restraint_reference_axes(
    restraint: "Restraint", interface: "Interface"
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the restraint local axes with the interface used as a fallback.

    Generated C# HRX records always serialise ``Restraint/ReferenceSystem``.
    Synthetic test models may omit it; in that case the generated foundation
    interface axes are the same physical axes by construction.
    """
    if restraint.has_reference_system:
        return (
            np.asarray(restraint.reference_e1, dtype=float),
            np.asarray(restraint.reference_e2, dtype=float),
            np.asarray(restraint.reference_e3, dtype=float),
        )
    return (
        np.asarray(interface.reference_e1, dtype=float),
        np.asarray(interface.reference_e2, dtype=float),
        np.asarray(interface.reference_e3, dtype=float),
    )


def _sign(value: float) -> float:
    if value > 0.0:
        return 1.0
    if value < 0.0:
        return -1.0
    return 0.0


def restraint_interface_signs(
    restraint: "Restraint", interface: "Interface"
) -> tuple[float, float, float]:
    """C# ``ComputeInterfaceAfference`` axis-alignment signs."""
    e1, e2, e3 = restraint_reference_axes(restraint, interface)
    i1 = np.asarray(interface.reference_e1, dtype=float)
    i2 = np.asarray(interface.reference_e2, dtype=float)
    i3 = np.asarray(interface.reference_e3, dtype=float)
    return (
        _sign(float(np.dot(i1, e1))),
        _sign(float(np.dot(i2, e2))),
        _sign(float(np.dot(i3, e3))),
    )


def restraint_support_entries(
    model: "Model",
) -> tuple[list[int], list[int], list[float]]:
    """Return 0-based diagonal COO entries for the restraint support springs."""
    assert model.collections is not None
    rows: list[int] = []
    cols: list[int] = []
    values: list[float] = []
    for restraint in sorted(
        getattr(model.collections, "restraints", {}).values(),
        key=lambda item: item.key,
    ):
        for local_index in active_restraint_directions(restraint):
            stiffness = float(restraint.k[local_index])
            gdl = int(restraint.solver_gdls[local_index])
            if gdl <= 0 or stiffness <= 0.0:
                continue
            rows.append(gdl - 1)
            cols.append(gdl - 1)
            values.append(stiffness)
    return rows, cols, values


def update_restraint_domain(model: "Model", ls: "LinearSystem") -> None:
    """Accumulate the local restraint displacements from ``ls.x``.

    Native ``Restraint.updateDomain`` adds the current correction to
    ``Status.U`` for every active local DOF.  The same operation also restores
    a failed trial when ``ls.x`` contains ``u_committed - u`` during rollback.
    """
    assert model.collections is not None
    x = getattr(ls, "x", ls)
    for restraint in getattr(model.collections, "restraints", {}).values():
        for local_index, gdl in enumerate(restraint.solver_gdls):
            if gdl <= 0:
                continue
            dof = int(gdl) - 1
            if 0 <= dof < len(x):
                restraint.u[local_index] += float(x[dof])


def scatter_restraint_resisting_force(model: "Model", ls: "LinearSystem") -> None:
    """Add ``-K_i * U_i`` to the residual for each active restraint DOF."""
    assert model.collections is not None
    for restraint in getattr(model.collections, "restraints", {}).values():
        for local_index, gdl in enumerate(restraint.solver_gdls):
            if gdl <= 0:
                continue
            stiffness = float(restraint.k[local_index])
            if stiffness <= 0.0:
                continue
            dof = int(gdl) - 1
            if 0 <= dof < ls.n:
                ls.sumb(dof, -stiffness * float(restraint.u[local_index]))
