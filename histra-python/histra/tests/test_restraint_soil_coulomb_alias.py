from __future__ import annotations

import xml.etree.ElementTree as ET
from types import SimpleNamespace

import numpy as np
import pytest

import histra.solver.hysteretic_batch as batch
from histra.elements.interface import Interface
from histra.preprocessing.prepare_model import _combine_coulomb
from histra.springs.base import Spring
from histra.springs.coulomb03 import SpringCoulomb03
from histra.tests.test_hysteretic_batch_material_update import _model
from histra.types.afference_entry import AfferenceEntry


def test_combine_coulomb_preserves_active_object_for_restrained_rigid_side() -> None:
    rigid = SpringCoulomb03(k=-1.0)
    active = SpringCoulomb03(k=70.0, cohesion=0.04, mu=1.427, area=431.1)

    combined = _combine_coulomb(
        rigid,
        active,
        restrained=True,
        preserve_single_side_identity=True,
    )

    assert combined is active


def test_normal_restraint_coulomb_abstraction_keeps_independent_copy() -> None:
    rigid = SpringCoulomb03(k=-1.0)
    active = SpringCoulomb03(k=70.0, cohesion=0.04, mu=1.427, area=431.1)

    combined = _combine_coulomb(rigid, active, restrained=True)

    assert combined is not active
    assert combined.k == active.k


def test_interface_xml_duplicate_out_of_plane_key_restores_csharp_alias() -> None:
    xml = ET.fromstring(
        """
        <Interface Key="6762" ParentTypeElement1="Restraint"
                   ParentTypeElement2="Quad" Length="23.9500122070313"
                   Thickness1="36" DimAff1="6" DimAff2="2" DimAff3="4">
          <SlidOutPlan>
            <Spring TypeOf="HiStrA.Objects.SpringCoulomb03" Key="1"
                    ParentKey="6762" ParentType="Interface"
                    SpringPurpose="SlidOutOfPlan" K="70.9779869561"
                    E1p="70.9779869561" E1n="70.9779869561"
                    C="0.04311001478" Mu="1.427" Area="431.1002"
                    Length="11.975" HystereticType="Initial" SubLaw="Coulomb" />
            <Spring TypeOf="HiStrA.Objects.SpringCoulomb03" Key="1"
                    ParentKey="6762" ParentType="Interface"
                    SpringPurpose="SlidOutOfPlan" K="70.9779869561"
                    E1p="70.9779869561" E1n="70.9779869561"
                    C="0.04311001478" Mu="1.427" Area="431.1002"
                    Length="11.975" HystereticType="Initial" SubLaw="Coulomb" />
          </SlidOutPlan>
        </Interface>
        """
    )

    interface = Interface.from_xml(xml)

    assert len(interface.slid_out_plan) == 2
    assert interface.slid_out_plan[0] is interface.slid_out_plan[1]
    assert interface.slid_out_plan[0].key == 1


def test_shared_out_of_plane_spring_accumulates_both_endpoint_increments() -> None:
    interface = Interface(
        key=6762,
        length=23.9500122070313,
        thickness=[36.0, 36.0],
        nrow=0,
        ncol=0,
        nspring=0,
        parent_type_element1="Restraint",
        parent_type_element2="Quad",
    )
    shared = Spring(k=70.0)
    interface.slid_out_plan = [shared, shared]
    interface.aff[10] = [AfferenceEntry(gdl=1, alfa=1.0)]
    interface.aff[11] = [AfferenceEntry(gdl=2, alfa=1.0)]

    u11 = 3.7204371384e-05
    u12 = 3.7652350324e-05
    interface.update_domain(np.array([u11, u12], dtype=np.float64), state=None)

    # C# updates the same object twice. Since di + dj == 1, the final shared
    # spring displacement is du_op_a + du_op_b = -(U11 + U12).
    assert shared.u == pytest.approx(-(u11 + u12), rel=0.0, abs=2.0e-18)
    assert interface.slid_out_plan[0].u == interface.slid_out_plan[1].u


def test_random006_interface_6762_matches_csharp_committed_oop_history() -> None:
    """Regression for the concrete Soil mismatch found in random_006.

    C# interface 6762 is a restraint/Quad Soil interface.  Its purpose-21
    spring stays elastic in Vert steps 1..5, so force is K*U.  The stored C#
    displacement history can therefore be reproduced without the large HRX
    fixture while still locking the shared-object kinematics that caused the
    original factor-of-two Python error.
    """
    interface = Interface(
        key=6762,
        length=23.9500122070313,
        thickness=[36.0, 36.0],
        nrow=0,
        ncol=0,
        nspring=0,
        parent_type_element1="Restraint",
        parent_type_element2="Quad",
    )
    shared = Spring(k=70.9779869561)
    interface.slid_out_plan = [shared, shared]
    interface.aff[10] = [AfferenceEntry(gdl=1, alfa=1.0)]
    interface.aff[11] = [AfferenceEntry(gdl=2, alfa=1.0)]

    csharp_local_u11_u12 = (
        (3.720437138401789e-05, 3.7652350324065436e-05),
        (0.00010838999138828042, 0.00010940658061898167),
        (4.0221728793973365e-05, 4.202867191672858e-05),
        (0.0007662216391386995, 0.0007669319155712714),
        (0.0004916691133432333, 0.0004936591737872474),
    )
    csharp_u = (
        -7.485672170808333e-05,
        -0.0002177965720072622,
        -8.225040071070216e-05,
        -0.0015331535547099709,
        -0.0009853282871304814,
    )
    csharp_f = (
        -0.005313179416976306,
        -0.01545876224702511,
        -0.005837967868782129,
        -0.10882015300797558,
        -0.06993661831147054,
    )

    previous = np.zeros(2, dtype=np.float64)
    for local, expected_u, expected_f in zip(
        csharp_local_u11_u12, csharp_u, csharp_f
    ):
        current = np.asarray(local, dtype=np.float64)
        interface.update_domain(current - previous, state=None)
        previous = current
        assert shared.u == pytest.approx(expected_u, rel=0.0, abs=3.0e-18)
        assert shared.f == pytest.approx(expected_f, rel=0.0, abs=1.0e-13)


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_dense_runtime_maps_aliased_out_of_plane_slots_to_one_state_row() -> None:
    model = _model()
    interface = model.collections.interfaces[1]
    shared = interface.slid_out_plan[0]
    interface.slid_out_plan = [shared, shared]

    runtime = batch.HystereticBatchRuntime(model)
    record_index = runtime._record_by_id[id(interface)]

    assert runtime._oop0_index[record_index] >= 0
    assert runtime._oop0_index[record_index] == runtime._oop1_index[record_index]


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_dense_material_update_remaps_compatible_identity_topology_change() -> None:
    model = _model()
    runtime = batch.HystereticBatchRuntime(model)
    interface = model.collections.interfaces[1]
    record_index = runtime._record_by_id[id(interface)]

    # Keep references to the expensive transverse storage. A Coulomb-only
    # identity remap must not discard/rebuild these arrays.
    transverse_storage = {
        name: id(getattr(runtime, name))
        for name in (
            "_params",
            "committed",
            "trial",
            "targets",
            "enabled",
            "_transverse_k",
        )
    }

    shared = interface.slid_out_plan[0]
    interface.slid_out_plan = [shared, shared]

    # Patch 3 deliberately supports compatible OOP identity-topology changes
    # by rebuilding only the small interface-Coulomb storage. A fresh runtime
    # built from this mutated model would likewise contain one shared OOP row.
    assert runtime.try_update_material_interfaces([interface]) is True

    oop0 = int(runtime._oop0_index[record_index])
    oop1 = int(runtime._oop1_index[record_index])
    assert oop0 >= 0
    assert oop0 == oop1
    assert runtime.coulomb_springs[oop0] is shared

    for name, object_id in transverse_storage.items():
        assert id(getattr(runtime, name)) == object_id
