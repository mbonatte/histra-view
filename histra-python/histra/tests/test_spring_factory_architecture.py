"""Architecture checks for the extracted preprocessing spring factory."""

import importlib

import histra.preprocessing.spring_factory as spring_factory


def test_prepare_model_compatibility_facade_reexports_factory_functions():
    prepare_model = importlib.import_module("histra.preprocessing.prepare_model")
    names = (
        "_combine_coulomb",
        "_combine_hysteretic",
        "_combine_sliding",
        "_configure_combined_hysteretic",
        "_configure_combined_hysteretic_batch",
        "_configure_coulomb",
        "_configure_hysteretic",
        "_copy_coulomb_spring",
        "_copy_hysteretic_spring",
        "_hysteretic_side_definition",
        "_new_hysteretic_spring",
        "_series",
        "_set_coulomb_ultimate",
        "_set_ultimate_displacement",
    )

    for name in names:
        assert getattr(prepare_model, name) is getattr(spring_factory, name)
