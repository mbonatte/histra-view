# `histra.springs.hysteretic`

**Source:** `histra/springs/hysteretic.py`  
**Size:** 808 lines  
**Layer:** Constitutive spring laws and XML type dispatch.

## Purpose

Implements a nonlinear hysteretic spring with configurable tension/compression envelopes, pinching, damage, and loading reversals.

## Dependencies

**Internal:** `histra.springs.base`, `histra.springs.registry`, `histra.types.hysteretic_curve_types`, `histra.types.phase_enum`, `histra.types.xml_utils`  
**Python/third-party:** `dataclasses`, `enum`, `math`, `typing`, `xml`  

## API and implementation units

### `SpringHysteretic`

Hysteretic spring with multi-linear/parabolic backbone and pinching rules.

**Bases:** `Spring`

**Declared state fields (grouped)**

- Configuration/public: `pinch_xp`, `pinch_yp`, `pinch_xn`, `pinch_yn`, `damfc1p`, `damfc2p`, `damfc1n`, `damfc2n`, `betap`, `betan`, `rot1p`, `mom1p`, `rot2p`, `mom2p`, `rot3p`, `mom3p`, `mom1n`, `rot1n`, `rot2n`, `mom2n`, `rot3n`, `mom3n`, `e1n`, `e1p`, `e2n`, `e2p`, `e3n`, `e3p`, `eun`, `eup`, `energy_a`, `tensile_curve_type`, `compressive_curve_type`, `fy`, `kt`, `ur`, `alfau`, `alfar`, `umax`, `uy_corr`, `f0`, `f0_target`, `kstrain`, `cenergy_d`, `k_tang_committed`, `is_on`, `phase`, `t_phase`
- Committed/history: `compressive_curve_type`, `cenergy_d`, `_crot_pu`, `_crot_nu`, `_cload_indicator`, `_cstress`, `_cstrain`
- Trial/current: `tensile_curve_type`, `_trot_max`, `_trot_min`, `_trot_pu`, `_trot_nu`, `_tenergy_d`, `_tload_indicator`, `_tstress`, `_tstrain`, `t_phase`

**Methods**

| Method | Description |
|---|---|
| `def _from_xml(elem: ET.Element, type_of: str = '') -> SpringHysteretic` | Subclass-specific XML constructor used by the registry/base factory. |
| `def revert_to_start() -> None` | Reset to initial (virgin) state (C# ``SpringHysteretic.revertToStart()``). |
| `def revert_to_last_commit() -> None` | Revert trial state to last committed state (C# ``RevertToLastCommit()``). |
| `def commit() -> None` | Commit trial → committed (C# ``SpringHysteretic.Commit()``). |
| `def get_force() -> float` | Return trial stress (C# ``SpringHysteretic.GetForce()``). |
| `def get_incr_force() -> float` | Force increment trial − committed (C# ``SpringHysteretic.GetIncrForce()``). |
| `def get_displacement() -> float` | Return trial strain (C# ``SpringHysteretic.GetDisplacement()``). |
| `def set_trial_strain(strain: float) -> None` | Set trial strain and compute trial stress/tangent. |
| `def _positive_increment(d_strain: float) -> None` | Port of C# ``positiveIncrement(double dStrain)``. |
| `def _negative_increment(d_strain: float) -> None` | Port of C# ``negativeIncrement(double dStrain)``. |
| `def _pos_envlp_stress(strain: float) -> float` | Positive envelope stress (C# ``posEnvlpStress``). |
| `def _pos_envlp_stress_linear(strain: float) -> float` | Positive envelope — linear/linear-softening branch. |
| `def _pos_envlp_stress_exponential(strain: float) -> float` | Positive envelope — exponential softening branch. |
| `def _neg_envlp_stress(strain: float) -> float` | Negative envelope stress (C# ``negEnvlpStress``). |
| `def _neg_envlp_stress_linear(strain: float) -> float` | Negative envelope — linear/linear-softening branch. |
| `def _neg_envlp_stress_parabolic(strain: float) -> float` | Negative envelope — parabolic branch. |
| `def _pos_envlp_tangent(strain: float) -> float` | Positive envelope tangent stiffness (C# ``posEnvlpTangent``). |
| `def _pos_envlp_tangent_linear(strain: float) -> float` | Positive envelope tangent — linear branch. |
| `def _pos_envlp_tangent_exponential(strain: float) -> float` | Positive envelope tangent — exponential branch. |
| `def _neg_envlp_tangent(strain: float) -> float` | Negative envelope tangent stiffness (C# ``negEnvlpTangent``). |
| `def _neg_envlp_tangent_linear(strain: float) -> float` | Negative envelope tangent — linear branch. |
| `def _neg_envlp_tangent_parabolic(strain: float) -> float` | Negative envelope tangent — parabolic branch. |
| `def _pos_envlp_rotlim(strain: float) -> float` | Positive envelope rotation limit (C# ``posEnvlpRotlim``). |
| `def _neg_envlp_rotlim(strain: float) -> float` | Negative envelope rotation limit (C# ``negEnvlpRotlim``). |
| `def initialize() -> None` | Compute envelope stiffness from backbone points (C# ``initialize()``). |
| `def _set_envelope() -> None` | Compute envelope stiffnesses E1/E2/E3/Eu (C# ``setEnvelope()``). |

## Runtime behavior

- Maintains committed (`_c...`) and trial (`_t...`) state for loading reversals and energy dissipation.
- Selects positive and negative envelope functions from curve-type enums.

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
