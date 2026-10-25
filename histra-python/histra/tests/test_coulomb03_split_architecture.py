"""Architecture checks for the SpringCoulomb03 split (§11.2 boundaries)."""

import importlib


def test_coulomb03_facade_exposes_the_complete_public_surface():
    spring = importlib.import_module("histra.springs.coulomb03")
    envelope = importlib.import_module("histra.springs.coulomb03_envelope")
    state = importlib.import_module("histra.springs.coulomb03_state")

    # The public object is the single class; the mixins are its boundaries.
    assert spring.SpringCoulomb03.__mro__[1] is state.Coulomb03StateMixin
    assert spring.SpringCoulomb03.__mro__[2] is envelope.Coulomb03EnvelopeMixin

    for name in (
        "_set_envelope",
        "_tau_limite",
        "_pos_envlp_stress_takeda",
        "_neg_envlp_stress_takeda",
        "_pos_envlp_tangent_takeda",
        "_neg_envlp_tangent_takeda",
        "_get_current_yielding_displacement_tension",
        "_get_current_yielding_displacement_compression",
    ):
        assert getattr(spring.SpringCoulomb03, name) is getattr(
            envelope.Coulomb03EnvelopeMixin, name
        )

    for name in (
        "_positive_increment_takeda",
        "_negative_increment_takeda",
        "set_trial_strain_takeda_diagonal_quad",
        "set_trial_strain_takeda",
        "set_trial_strain_initial",
        "revert_to_start",
        "revert_to_last_commit",
        "revert_to_last_commit_stress_normal",
        "commit",
        "set_trial_strain",
        "get_force",
        "get_incr_force",
        "get_displacement",
    ):
        assert getattr(spring.SpringCoulomb03, name) is getattr(
            state.Coulomb03StateMixin, name
        )


def test_coulomb03_owners_have_no_reverse_dependency_on_the_facade():
    source_env = importlib.util.find_spec(
        "histra.springs.coulomb03_envelope"
    ).origin
    source_state = importlib.util.find_spec(
        "histra.springs.coulomb03_state"
    ).origin
    for source in (source_env, source_state):
        with open(source, "r", encoding="utf-8") as handle:
            text = handle.read()
        assert "coulomb03 import" not in text
