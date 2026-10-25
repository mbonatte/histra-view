"""Original low-level SetSpring histories, distinct from guarded DB restart.

dbOutputManager.UpdateSpringStates skips mismatched laws before SetSpring.
These tests qualify the restoration helpers, not loaded cross-law support.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from histra.solver.restart import (
    _restore_elastic, _restore_hysteretic, capture_committed_spring_state,
)
from histra.springs.elastic import SpringElastic
from histra.springs.hysteretic import SpringHysteretic
from histra.tests.masonry_native_helpers import masonry_spring
from histra import load_model
from histra.solver.hysteretic_batch import build_hysteretic_batch
from histra.solver.model_manager import ModelManager
from tools.benchmarks.build_masonry_reference_models import DEFAULT_TEMPLATE, build_reference_model


ROOT = Path(__file__).resolve().parents[2]
NATIVE = json.loads((Path(__file__).parent / "fixtures/csharp-masonry-law-transition-2026.1.1.json").read_text(encoding="utf-8-sig"))


def _state(spring):
    values = {
        "K": spring.k, "K_tang": spring.k_tang, "U": spring.u, "F": spring.f,
        "Force": spring.get_force(), "Increment": spring.get_incr_force(),
        "Cstrain": spring._cstrain, "Cstress": spring._cstress, "Phase": spring.phase,
    }
    if isinstance(spring, SpringHysteretic):
        values.update(Umax0=spring.umax[0], Umax1=spring.umax[1],
                      Uy0=spring.uy_corr[0], Uy1=spring.uy_corr[1],
                      Fy0=spring.fy[0], Fy1=spring.fy[1], CrotPu=spring._crot_pu,
                      CrotNu=spring._crot_nu, CloadIndicator=spring._cload_indicator, F0=spring.f0)
    return values


def _assert_native(spring, expected):
    actual = _state(spring)
    assert actual.keys() == expected["bits"].keys()
    for field, value in actual.items():
        assert int(np.float64(value).view(np.int64)) == int(expected["bits"][field]), (field, value, expected["values"][field])


def test_law_transition_oracle_provenance():
    oracle = ROOT / NATIVE["generator"]
    assert hashlib.sha256(oracle.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == NATIVE["oracle_lf_sha256"]
    inputs = Path(__file__).parent / "fixtures/masonry-law-transition-inputs.json"
    assert hashlib.sha256(inputs.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == NATIVE["input_lf_sha256"]
    assert json.loads(inputs.read_text()) == NATIVE["inputs"]


@pytest.mark.parametrize("index", range(6))
def test_native_hysteretic_elastic_return(index):
    case, expected = NATIVE["inputs"]["cases"][index], NATIVE["cases"][index]
    source = masonry_spring(case["source"])
    for strain in case["strains"]:
        if case.get("set_base_u_before_trial"):
            source.u = strain
        source.set_trial_strain(strain)
        source.commit()
    _assert_native(source, expected["before"])
    for stage, reset in zip(case["stages"], expected["resets"], strict=True):
        definition = stage["target"]
        target = (SpringElastic(k=definition["k"], k_tang=definition["k"])
                  if definition.get("law") == "Elastic" else masonry_spring(definition))
        restore = _restore_elastic if isinstance(target, SpringElastic) else _restore_hysteretic
        restore(target, capture_committed_spring_state(source))
        _assert_native(target, reset["restored"])
        for row in reset["history"]:
            if case.get("set_base_u_before_trial"):
                target.u = row["strain"]
            target.set_trial_strain(row["strain"])
            _assert_native(target, row["trial"])
            target.commit()
            _assert_native(target, row["committed"])
        source = target


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("slot", ["transverse", "sliding", "quad"])
def test_native_elastic_trial_state_survives_runtime_import_and_projection(tmp_path, index, slot):
    # Test compatibility-object projection separately from constitutive
    # evaluation; expected fields still come from the original assembly.
    # Native interface/quad UpdateDomain sets the base displacement target
    # before invoking setTrialStrain; standalone spring calls do not.
    case = NATIVE["inputs"]["cases"][index + 3]
    reference = NATIVE["cases"][index + 3]["resets"][0]
    source = masonry_spring(case["source"])
    for strain in case["strains"]:
        source.set_trial_strain(strain)
        source.commit()
    target = SpringElastic(k=2300.0, k_tang=2300.0)
    _restore_elastic(target, capture_committed_spring_state(source))
    target.u = reference["history"][0]["strain"]
    target.set_trial_strain(reference["history"][0]["strain"])
    path = tmp_path / "elastic.hrx"
    build_reference_model(DEFAULT_TEMPLATE, "03_elastic_transverse_reversal").write(path)
    model = load_model(path)
    ModelManager.prepare_model(model, force=True, use_cache=False)
    interface = model.collections.interfaces[1]
    if slot == "transverse":
        interface.trasv_1[0] = target
    elif slot == "sliding":
        interface.slid[0] = target
    else:
        model.collections.quads[1].spring = target
    runtime = build_hysteretic_batch(model)
    assert runtime.manages(interface)
    runtime.sync_interface_trial_to_objects(interface)
    runtime.sync_all_to_objects()
    _assert_native(target, reference["history"][0]["trial"])
