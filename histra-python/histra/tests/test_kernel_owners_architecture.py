"""Architecture checks for the extracted interface/quad kernel owners."""

import importlib.util

import histra.solver.hysteretic_kernels.interface_coulomb as interface_coulomb
import histra.solver.hysteretic_kernels.quad_takeda as quad_takeda
import histra.solver.hysteretic_kernels.transverse as transverse


def test_hysteretic_batch_facade_reexports_interface_kernels_and_constants():
    batch = importlib.import_module("histra.solver.hysteretic_batch")
    names = (
        "CDN",
        "CFY0",
        "CFY1",
        "CKTANG",
        "CKTANG_COMMITTED",
        "COULOMB_STATE_SIZE",
        "CU",
        "CF",
        "_advance_interface_coulomb_targets",
        "_assemble_full_interface_forces",
        "_commit_elastic_sliding_batch",
        "_commit_initial_coulomb_batch",
        "_evaluate_elastic_sliding_batch",
        "_evaluate_initial_coulomb_batch",
    )

    for name in names:
        assert getattr(batch, name) is getattr(interface_coulomb, name)


def test_hysteretic_batch_facade_reexports_quad_kernels_and_constants():
    batch = importlib.import_module("histra.solver.hysteretic_batch")
    names = (
        "QDN",
        "QFY0",
        "QFY1",
        "QUAD_STATE_SIZE",
        "QUAD_PARAM_SIZE",
        "QPCOHESION",
        "QPSUBLAW",
        "QUAD_SUBLAW_COULOMB",
        "QUAD_SUBLAW_CACOVIC",
        "QUAD_SUBLAW_ELASTIC",
        "QUAD_HYSTERETIC_TAKEDA",
        "QUAD_HYSTERETIC_INITIAL",
        "QUAD_FRACTURE_NONE",
        "QUAD_FRACTURE_FIXED",
        "QUAD_FRACTURE_INTERPOLATED",
        "QTCONTACT",
        "QTPHASE",
        "_commit_quad_takeda_batch",
        "_evaluate_quad_takeda_batch",
        "_quad_tau_limit",
        "_quad_interpolated_shear_energy",
        "_quad_shear_ultimate_strain",
        "_quad_tangent_reload_t",
        "_quad_tangent_reload_c",
        "_quad_yield_tension",
        "_quad_yield_compression",
    )

    for name in names:
        assert getattr(batch, name) is getattr(quad_takeda, name)


def test_kernel_modules_share_the_transverse_phase_codes():
    for name in ("ELASTIC", "PLASTIC_T", "PLASTIC_C", "RELOAD_T", "RELOAD_C",
                 "UNLOAD_T", "UNLOAD_C", "RUPTURE", "RUPTURE_T", "RUPTURE_C"):
        assert getattr(quad_takeda, name) is getattr(transverse, name)
    # interface_coulomb only needs the Initial-law phase subset.
    for name in ("ELASTIC", "PLASTIC_T", "PLASTIC_C", "RUPTURE"):
        assert getattr(interface_coulomb, name) is getattr(transverse, name)


def test_hysteretic_batch_facade_reexports_topology_layer():
    batch = importlib.import_module("histra.solver.hysteretic_batch")
    topology = importlib.import_module("histra.solver.hysteretic_topology")
    names = (
        "_InterfaceSlice",
        "_SIMPLE_PARAM_GETTER",
        "_PARAM_GETTER",
        "_build_force_by_dof_topology",
        "_extract_spring_committed",
        "_extract_spring_curve_type",
        "_extract_spring_params",
        "_extract_spring_target",
        "_extract_spring_trial",
    )

    for name in names:
        assert getattr(batch, name) is getattr(topology, name)


def test_hysteretic_batch_facade_reexports_kinematics_and_scatter_kernels():
    batch = importlib.import_module("histra.solver.hysteretic_batch")
    kinematics = importlib.import_module("histra.solver.hysteretic_kernels.kinematics")
    scatter = importlib.import_module("histra.solver.hysteretic_kernels.scatter")
    kin_names = (
        "_map_global_to_local",
        "_prepare_interface_kinematics",
        "_map_and_prepare_interface_kinematics",
        "_prepare_quad_kinematics",
    )
    scatter_names = (
        "_scatter_local_forces",
        "_refresh_global_resisting_force",
        "_refresh_global_resisting_force_by_dof",
        "_refresh_max_u_cache",
    )

    for name in kin_names:
        assert getattr(batch, name) is getattr(kinematics, name)
    for name in scatter_names:
        assert getattr(batch, name) is getattr(scatter, name)


def test_kernel_owners_have_no_reverse_dependency_on_hysteretic_batch():
    for module in (interface_coulomb, quad_takeda):
        source = importlib.util.find_spec(module.__name__).origin
        with open(source, "r", encoding="utf-8") as handle:
            text = handle.read()
        assert "hysteretic_batch" not in text
