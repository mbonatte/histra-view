# `histra.springs.coulomb03`

**Source:** `histra/springs/coulomb03.py`  
**Size:** 1086 lines  
**Layer:** Constitutive spring laws and XML type dispatch.

## Purpose

Implements the detailed Coulomb03/Takeda-style nonlinear contact/friction state machine with committed and trial history.

## Dependencies

**Internal:** `histra.springs.base`, `histra.springs.registry`, `histra.types.hysteretic_curve_types`, `histra.types.phase_enum`, `histra.types.xml_utils`  
**Python/third-party:** `dataclasses`, `math`, `typing`, `xml`  

## API and implementation units

### `SpringCoulomb03`

Coulomb friction spring type 03 — direct port of C# SpringCoulomb03.

**Bases:** `Spring`

**Declared state fields (grouped)**

- Configuration/public: `check_contact_area`, `sub_law`, `hysteretic_type`, `cohesion`, `mu`, `plastic_strain_ratio`, `plastic_stiffness_ratio`, `max_tensile_ratio`, `reload_stiffness_ratio`, `bcacovic`, `mom1p`, `rot1p`, `mom2p`, `rot2p`, `mom3p`, `rot3p`, `mom1n`, `rot1n`, `mom2n`, `rot2n`, `mom3n`, `rot3n`, `e1p`, `e2p`, `e3p`, `e1n`, `e2n`, `e3n`, `eup`, `eun`, `energy_a`, `fy`, `ur`, `umax`, `cenergy_d`, `dn`, `area_corrente`, `k_tang_committed`, `tangent_reload_t`, `tangent_reload_c`, `phase`, `t_phase`
- Committed/history: `check_contact_area`, `cohesion`, `_cstress`, `_cstrain`, `_cstress_normal`, `_cstress_normal_prev`, `_ccontact_area`, `_crot_pu`, `_crot_nu`, `_crot_lim_pu`, `_crot_lim_nu`, `_crot_yp`, `_crot_yn`, `_cmom_max`, `_cmom_min`, `_cload_indicator`, `_cplastic_tension_indicator`, `_cplastic_compression_indicator`, `_c_phase_unload_t`, `_c_phase_unload_c`, `_cup`, `cenergy_d`
- Trial/current: `_tstress`, `_tstrain`, `_tstress_normal`, `_tcontact_area`, `_trot_max`, `_trot_min`, `_trot_pu`, `_trot_nu`, `_trot_lim_pu`, `_trot_lim_nu`, `_trot_yp`, `_trot_yn`, `_tmom_max`, `_tmom_min`, `_tload_indicator`, `_tplastic_tension_indicator`, `_tplastic_compression_indicator`, `_t_phase_unload_t`, `_t_phase_unload_c`, `_tenergy_d`, `_tup`, `tangent_reload_t`, `tangent_reload_c`, `t_phase`

**Methods**

| Method | Description |
|---|---|
| `def c() -> float` | C. |
| `def c(val: float) -> None` | C. |
| `def kt() -> float` | Kt. |
| `def kt(val: float) -> None` | Kt. |
| `def _from_xml(elem: ET.Element, type_of: str = '') -> SpringCoulomb03` | Subclass-specific XML constructor used by the registry/base factory. |
| `def _set_envelope() -> None` | Compute envelope slopes from backbone points (C# setEnvelope). |
| `def _tau_limite(N: float, ratio_cohesion: float = 1.0) -> float` | Coulomb or Cacovic limiting shear stress (C# TauLimite). |
| `def h() -> float` | Hardening modulus (C# H = E1p*E2p/(E1p - E2p)). |
| `def _pos_envlp_stress_takeda(strain: float) -> float` | Positive envelope stress (C# posEnvlpStressTakeda). |
| `def _neg_envlp_stress_takeda(strain: float) -> float` | Negative envelope stress (C# negEnvlpStressTakeda). |
| `def _pos_envlp_tangent_takeda(strain: float) -> float` | Positive envelope tangent, sets t_phase based on branch (C# posEnvlpTangentTakeda). |
| `def _neg_envlp_tangent_takeda(strain: float) -> float` | Negative envelope tangent, sets t_phase (C# negEnvlpTangentTakeda). |
| `def _get_current_yielding_displacement_tension(phase_unload: int, dstrain: float) -> float` | C# GetCurrentYieldingDisplacementTension. |
| `def _get_current_yielding_displacement_compression(phase_unload: int, dstrain: float) -> float` | C# GetCurrentYieldingDisplacementCompression. |
| `def _positive_increment_takeda(dstrain: float) -> None` | C# positiveIncrementTakeda. |
| `def _negative_increment_takeda(dstrain: float) -> None` | C# negativeIncrementTakeda. |
| `def set_trial_strain_takeda_diagonal_quad(strain: float, dN: float, masonry = None, volume: float = 0.0, sigma: float = 0.0) -> int` | C# setTrialStrainTakedaDiagonalQuad. |
| `def set_trial_strain_takeda(strain: float) -> int` | C# setTrialStrainTakeda (generic, no fracture-energy path). |
| `def set_trial_strain_initial(strain: float) -> int` | C# setTrialStrainInitial (simpler elastic-plastic with hardening). |
| `def revert_to_start() -> None` | C# revertToStart. |
| `def revert_to_last_commit() -> None` | C# RevertToLastCommit. |
| `def commit() -> None` | C# Commit. |
| `def set_trial_strain(strain: float) -> None` | Dispatch to Takeda or Initial hysteretic type (C# setTrialStrain). |
| `def get_force() -> float` | Returns the current spring force. |
| `def get_incr_force() -> float` | Get incr force. |
| `def get_displacement() -> float` | Get displacement. |

## Runtime behavior

- Maintains a large history state for contact, friction, unloading/reloading, yielding, and energy.
- Offers standard, Takeda, and diagonal-quad trial-strain paths.

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
